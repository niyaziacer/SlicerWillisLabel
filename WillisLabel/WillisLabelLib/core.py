"""Core algorithms for WillisLabel (numpy + scipy only; no Slicer dependency).

All arrays are indexed [i, j, k] with voxel spacing ``spacing`` (mm) along the
same axes. Seeds are given in voxel (i, j, k) coordinates.
"""

import numpy as np
from scipy import ndimage as ndi
from scipy import sparse
from scipy.sparse import csgraph

STRUCT26 = np.ones((3, 3, 3), bool)


# ---------------------------------------------------------------------------
# 1. Vessel extraction
# ---------------------------------------------------------------------------
def suggest_thresholds(image, brain_fraction_mask=None):
    """Suggest (low, high) hysteresis thresholds from intensity percentiles.

    TOF arteries occupy roughly the top 0.5-1 % of voxels inside the head.
    """
    vals = image[image > np.percentile(image, 50)] if brain_fraction_mask is None else image[brain_fraction_mask]
    low = float(np.percentile(vals, 98.0))
    high = float(np.percentile(vals, 99.6))
    return low, high


def extract_vessels(image, spacing, low, high, sigma_mm=0.5, min_size_mm3=30.0, remove_flat=True):
    """Hysteresis threshold + connected components.

    Returns a boolean mask of arterial voxels.
    """
    spacing = np.asarray(spacing, float)
    img = ndi.gaussian_filter(image.astype(np.float32), sigma=sigma_mm / spacing) if sigma_mm > 0 else image
    weak = img >= low
    strong = img >= high
    lab, n = ndi.label(weak, structure=STRUCT26)
    if n == 0:
        return np.zeros(image.shape, bool)
    keep = np.zeros(n + 1, bool)
    keep[np.unique(lab[strong])] = True
    keep[0] = False
    mask = keep[lab]

    # drop small components and flat sheets (subcutaneous fat, which is bright on TOF)
    lab, n = ndi.label(mask, structure=STRUCT26)
    vox_mm3 = float(np.prod(spacing))
    sizes = ndi.sum(mask, lab, index=np.arange(1, n + 1)) * vox_mm3
    keep = np.zeros(n + 1, bool)
    objs = ndi.find_objects(lab)
    for c in range(1, n + 1):
        if sizes[c - 1] < min_size_mm3:
            continue
        if remove_flat:
            sl = objs[c - 1]
            comp = lab[sl] == c
            pts = np.argwhere(comp) * spacing
            if len(pts) > 50:
                ev = np.linalg.eigvalsh(np.cov(pts.T))
                # sheet: smallest extent tiny compared to the other two
                if ev[0] < 0.02 * ev[1] and ev[1] > 0.1 * ev[2]:
                    continue
        keep[c] = True
    return keep[lab]


# ---------------------------------------------------------------------------
# 2. Graph utilities (voxel graph inside the mask)
# ---------------------------------------------------------------------------
class VoxelGraph:
    """26-connected graph on the voxels of a mask, with edge length in mm."""

    def __init__(self, mask, spacing, node_weight=None):
        self.mask = mask
        self.spacing = np.asarray(spacing, float)
        self.coords = np.argwhere(mask)
        self.index = -np.ones(mask.shape, np.int64)
        self.index[tuple(self.coords.T)] = np.arange(len(self.coords))
        rows, cols, w = [], [], []
        shape = np.array(mask.shape)
        for d in np.array(np.meshgrid([-1, 0, 1], [-1, 0, 1], [-1, 0, 1], indexing="ij")).reshape(3, -1).T:
            if not np.any(d) or tuple(d) < (0, 0, 0):
                continue  # each undirected edge once
            nb = self.coords + d
            ok = np.all((nb >= 0) & (nb < shape), axis=1)
            src = np.nonzero(ok)[0]
            dst = self.index[tuple(nb[ok].T)]
            good = dst >= 0
            src, dst = src[good], dst[good]
            length = float(np.linalg.norm(d * self.spacing))
            if node_weight is None:
                ww = np.full(len(src), length)
            else:
                ww = length * 0.5 * (node_weight[src] + node_weight[dst])
            rows.append(src); cols.append(dst); w.append(ww)
        rows = np.concatenate(rows); cols = np.concatenate(cols); w = np.concatenate(w)
        n = len(self.coords)
        self.graph = sparse.coo_matrix((w, (rows, cols)), shape=(n, n)).tocsr()

    def nodes(self, ijk_list):
        out = []
        for p in ijk_list:
            k = self.index[tuple(p)]
            if k >= 0:
                out.append(int(k))
        return out

    def distances(self, sources):
        return csgraph.dijkstra(self.graph, directed=False, indices=sources, min_only=True)

    def path(self, a, b):
        _, pred = csgraph.dijkstra(self.graph, directed=False, indices=[a], return_predecessors=True)
        pred = pred[0]
        p = [b]
        while p[-1] != a and p[-1] >= 0:
            p.append(pred[p[-1]])
        if p[-1] != a:
            return None
        return np.array(p[::-1])


def snap_to_mask(mask, image, ijk, radius_vox=(4, 4, 4)):
    """Move a seed to the brightest mask voxel nearby (or None)."""
    ijk = np.round(np.asarray(ijk)).astype(int)
    if np.all(ijk >= 0) and np.all(ijk < mask.shape) and mask[tuple(ijk)]:
        return tuple(int(x) for x in ijk)
    lo = np.maximum(ijk - radius_vox, 0)
    hi = np.minimum(ijk + np.asarray(radius_vox) + 1, mask.shape)
    sl = tuple(slice(a, b) for a, b in zip(lo, hi))
    sub = np.where(mask[sl], image[sl], -np.inf)
    if not np.isfinite(sub.max()):
        return None
    a = np.unravel_index(np.argmax(sub), sub.shape)
    return tuple(int(lo[d] + a[d]) for d in range(3))


# ---------------------------------------------------------------------------
# 3. Seed-based geodesic labelling
# ---------------------------------------------------------------------------
def label_from_seeds(mask, seeds, spacing, graph=None):
    """Assign every mask voxel to the label whose seeds are geodesically closest.

    seeds: dict {label_name: [ijk, ...]} (already snapped into the mask)
    Returns (labelmap uint8, names list, graph). Voxels not connected to any
    seed get value len(names)+1 (``unconnected``) if any exist, else 0.
    """
    g = graph or VoxelGraph(mask, spacing)
    names = [n for n in seeds if g.nodes(seeds[n])]
    D = np.full((len(names), len(g.coords)), np.inf, np.float32)
    for li, n in enumerate(names):
        D[li] = g.distances(g.nodes(seeds[n]))
    best = np.argmin(D, axis=0)
    unconnected = ~np.isfinite(D.min(axis=0))
    lab = np.zeros(mask.shape, np.uint8)
    vals = (best + 1).astype(np.uint8)
    if unconnected.any():
        vals[unconnected] = len(names) + 1
    lab[tuple(g.coords.T)] = vals
    return lab, names, g


# ---------------------------------------------------------------------------
# 4. Branch-origin correction ("stub fix")
# ---------------------------------------------------------------------------
def fix_branch_origins(lab, mask, names, parents, spacing, margin_mm=0.5, si_axis=2):
    """Give the first millimetres of each branch to the branch, not the parent.

    For each parent artery a centreline is traced between its lowest and highest
    points (cost favours the vessel centre). Parent voxels farther from that
    centreline than the parent radius are side-branch stubs; each stub is
    re-assigned to the neighbouring branch label it touches most.
    """
    spacing = np.asarray(spacing, float)
    edt = ndi.distance_transform_edt(mask, sampling=spacing)
    report = {}
    for p in parents:
        if p not in names:
            continue
        pv = names.index(p) + 1
        P = lab == pv
        if P.sum() < 20:
            continue
        I = np.argwhere(P)
        lo = I.min(0); hi = I.max(0) + 1
        cr = tuple(slice(a, b) for a, b in zip(lo, hi))
        Pc = P[cr]; Ec = edt[cr]
        J = np.argwhere(Pc)
        w = 1.0 / (Ec[tuple(J.T)] + 0.15) ** 2
        g = VoxelGraph(Pc, spacing, node_weight=w)

        def endpoint(kk):
            S = J[J[:, si_axis] == kk]
            return int(g.index[tuple(S[np.argmax(Ec[tuple(S.T)])])])

        a = endpoint(J[:, si_axis].min()); b = endpoint(J[:, si_axis].max())
        path = g.path(a, b)
        if path is None:
            continue
        cl = np.zeros(Pc.shape, bool)
        cl[tuple(g.coords[path].T)] = True
        R = float(np.percentile(Ec[cl], 75))
        zone = ndi.distance_transform_edt(~cl, sampling=spacing) <= R + margin_mm
        stub = np.zeros_like(P); stub[cr] = Pc & ~zone
        lc, n = ndi.label(stub, structure=STRUCT26)
        moved = 0
        for k, sl in enumerate(ndi.find_objects(lc), start=1):
            sl2 = tuple(slice(max(s.start - 1, 0), s.stop + 1) for s in sl)
            comp = lc[sl2] == k
            ring = ndi.binary_dilation(comp, structure=STRUCT26) & ~comp
            nb = lab[sl2][ring]
            nb = nb[(nb != 0) & (nb != pv)]
            if len(nb) == 0:
                continue
            sub = lab[sl2]
            sub[comp] = np.bincount(nb).argmax()
            moved += int(comp.sum())
        report[p] = dict(centreline_vox=int(len(path)), radius_mm=round(R, 2), stubs=int(n), moved_vox=moved)
    return lab, report
