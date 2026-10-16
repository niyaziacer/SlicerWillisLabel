"""Split a vessel mask into branches (segments between bifurcations), without naming them.

Method (voxel coding, no skeleton library needed):
  1. Roots: the thick vessels entering at the bottom of the slab (ICA, VA/BA).
  2. Geodesic distance from the roots; the vessel is cut into 1 mm thick "shells".
  3. Each connected piece of a shell is a node; nodes in consecutive shells that touch are linked.
     A vessel is a chain of nodes; a bifurcation is a node with two or more continuing children.
  4. Children whose subtree is shorter than `min_branch_mm` are bumps, not branches, and stay
     with their parent.
  5. Each chain between bifurcations becomes one branch with its own number.
Loops (the circle of Willis) are handled because each node keeps only one parent; where two
fronts meet inside the loop a branch simply ends.
Pieces not connected to a root are treated the same way, from their own lowest thick point.
"""

import numpy as np
from scipy import ndimage as ndi
from scipy.sparse import coo_matrix, csgraph

from . import core


def split_branches(mask, spacing, si_axis=0, step_mm=1.0, min_branch_mm=4.0, min_size_mm3=5.0):
    """Return (branch labelmap int32 with 0 = background, number of branches)."""
    spacing = np.asarray(spacing, float)
    out = np.zeros(mask.shape, np.int32)
    comp, n = ndi.label(mask, structure=core.STRUCT26)
    if n == 0:
        return out, 0
    vox = float(np.prod(spacing))
    sizes = np.bincount(comp.ravel())
    next_id = 1
    for c, sl in enumerate(ndi.find_objects(comp), start=1):
        if sizes[c] * vox < min_size_mm3:
            continue
        piece = comp[sl] == c
        lab, k = _split_piece(piece, spacing, si_axis, step_mm, min_branch_mm)
        sub = out[sl]
        sub[piece] = lab[piece] + next_id - 1
        next_id += k
    return out, next_id - 1


def _split_piece(piece, spacing, si_axis, step_mm, min_branch_mm):
    g = core.VoxelGraph(piece, spacing)
    C = g.coords
    edt = ndi.distance_transform_edt(piece, sampling=spacing)[tuple(C.T)]
    band = max(1, int(round(3.0 / spacing[si_axis])))
    low = C[:, si_axis] < C[:, si_axis].min() + band
    roots = np.nonzero(low & (edt >= 0.45 * edt[low].max()))[0]
    d = g.distances(roots)
    d[~np.isfinite(d)] = 0
    shell = np.floor(d / step_mm).astype(np.int64)

    # nodes = connected pieces of each shell
    G = g.graph.tocoo()
    same = shell[G.row] == shell[G.col]
    n = len(C)
    A = coo_matrix((np.ones(same.sum()), (G.row[same], G.col[same])), shape=(n, n))
    nn, node = csgraph.connected_components(A, directed=False)
    node_shell = np.zeros(nn, np.int64)
    node_shell[node] = shell

    # links between consecutive shells (lower -> higher), weighted by contact size
    up = shell[G.col] == shell[G.row] + 1
    dn = shell[G.row] == shell[G.col] + 1
    lo = np.concatenate([node[G.row[up]], node[G.col[dn]]])
    hi = np.concatenate([node[G.col[up]], node[G.row[dn]]])
    parent = -np.ones(nn, np.int64)
    if len(lo):
        L = coo_matrix((np.ones(len(lo)), (hi, lo)), shape=(nn, nn)).tocsr()  # row: child, col: parent
        L.sum_duplicates()
        Lc = L.tocoo()
        order = np.lexsort((-Lc.data, Lc.row))          # per child, strongest contact first
        r, cpar = Lc.row[order], Lc.col[order]
        first = np.ones(len(r), bool); first[1:] = r[1:] != r[:-1]
        parent[r[first]] = cpar[first]                    # strongest contact = parent
    children = [[] for _ in range(nn)]
    for ch in np.argsort(node_shell):
        if parent[ch] >= 0:
            children[parent[ch]].append(ch)

    # subtree length (in shells) for pruning bumps
    depth = node_shell.copy()
    for v in np.argsort(-node_shell):
        if parent[v] >= 0:
            depth[parent[v]] = max(depth[parent[v]], depth[v])
    sublen = (depth - node_shell) * step_mm

    seg = -np.ones(nn, np.int64)
    k = 0
    for v in np.argsort(node_shell):
        if seg[v] < 0:           # root node (or a node whose parent was not linked)
            seg[v] = k; k += 1
        sig = [c for c in children[v] if sublen[c] + step_mm >= min_branch_mm]
        for c in children[v]:
            if len(sig) >= 2 and c in sig:
                seg[c] = k; k += 1
            else:
                seg[c] = seg[v]
    lab = np.zeros(piece.shape, np.int32)
    lab[tuple(C.T)] = seg[node] + 1
    return lab, k


UNNAMED = "(unnamed)"


def branch_id(b):
    return f"Branch {b}"


def colour(b):
    """Distinct, reproducible colour for branch number b."""
    import colorsys
    h = (b * 0.618033988749895) % 1.0
    s = 0.55 + 0.35 * ((b * 7) % 3) / 2.0
    return colorsys.hsv_to_rgb(h, s, 0.92)


def branch_at(lab, point, spacing, snap_mm=3.0):
    """Branch number at (or within snap_mm of) a voxel, or None."""
    point = np.asarray(point, int)
    v = int(lab[tuple(point)])
    if v > 0:
        return v
    spacing = np.asarray(spacing, float)
    r = np.maximum(1, np.round(snap_mm / spacing)).astype(int)
    lo = np.maximum(point - r, 0); hi = np.minimum(point + r + 1, lab.shape)
    sub = lab[lo[0]:hi[0], lo[1]:hi[1], lo[2]:hi[2]]
    P = np.argwhere(sub > 0)
    if not len(P):
        return None
    P = P + lo
    q = P[np.argmin(np.linalg.norm((P - point) * spacing, axis=1))]
    return int(lab[tuple(q)])
