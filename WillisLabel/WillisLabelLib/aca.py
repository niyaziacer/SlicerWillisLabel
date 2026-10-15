"""Distal anterior cerebral artery: pericallosal course and median (third) vessels.

After the geodesic labelling, the A2 territory (A2 R, A2 L, A2 3rd) is examined for vessels
that run posteriorly above the circle of Willis, i.e. along the corpus callosum.
The corpus callosum is not visible on TOF-MRA, so the course is approximated by how far
a vessel reaches *posterior* and *superior* to the AComA (thresholds below).

Rules (agreed with the anatomist, see Docs):
  * The posterior-coursing vessel of each A2 is the A. pericallosa of that side.
    The A2 segment up to its most anterior point (genu) keeps the A2 name;
    the other A2 branches (anterior / upward) become "A2 <side> rami".
  * A further posterior-coursing vessel
      - from the AComA   -> "A. callosa mediana"            (variation)
      - from an A2       -> "A2 <side> perikallozal varyasyon dalı" (variation)
  * Exactly one posterior-coursing vessel -> possible azygos / bihemispheric ACA.
All variation findings are flagged for review by an anatomist.
"""

import numpy as np
from scipy import ndimage as ndi
from scipy.sparse import csgraph

from . import core

POST_MIN_MM = 10.0       # reach behind the AComA needed to call a course "pericallosal"
SUP_MIN_MM = 8.0         # ... and height above the AComA (excludes basal perforators)
MIN_VOL_MM3 = 3.0        # ignore smaller posterior fragments
NEAR_ACOMA_MM = 3.0
ROOT_MAX_SUP_MM = 4.0    # A1 / AComA voxels higher than this are treated as distal vessel      # origin this close to the AComA is reported as ambiguous
FLAG = "VARYASYON – anatomist onayı gerekli (VARIATION – anatomist review required)"

DISTAL = ("A2 R", "A2 L", "A2 3rd", "ACA R", "ACA L")
ROOTS = ("A1 R", "A1 L", "AComA")
SIDE_OF = {"A2 R": "R", "ACA R": "R", "A1 R": "R", "A2 L": "L", "ACA L": "L", "A1 L": "L"}


def _path_to_root(pred, node):
    p = [node]
    while pred[p[-1]] >= 0:
        p.append(pred[p[-1]])
    return np.array(p[::-1])  # root -> node


def find_pericallosal_vessels(lab, names, spacing, post_vec, sup_vec):
    """Detect posterior-coursing (pericallosal) vessels in the distal ACA territory.

    post_vec / sup_vec: unit vectors (in array-axis mm space) pointing posterior / superior.
    Returns (vessels, context). Each vessel is a dict with its path (graph nodes, root->tip),
    origin ('R', 'L' or 'AComA'), departure index on the path, reach and notes.
    """
    names = list(names)
    val = {n: names.index(n) + 1 for n in DISTAL + ROOTS if n in names}
    if not any(n in val for n in DISTAL) or not any(n in val for n in ROOTS):
        return [], None
    U = np.isin(lab, list(val.values()))
    g = core.VoxelGraph(U, spacing)
    X = g.coords * np.asarray(spacing, float)
    lv = lab[tuple(g.coords.T)]
    rootvals = [val[n] for n in ROOTS if n in val]
    is_root = np.isin(lv, rootvals)
    ref = lv == val["AComA"] if "AComA" in val else is_root
    s_raw = X @ sup_vec
    ref = ref & (s_raw <= np.percentile(s_raw[ref], 5) + 3.0)  # low part only (see below)
    rp = X @ post_vec - (X[ref] @ post_vec).mean()
    rs = X @ sup_vec - (X[ref] @ sup_vec).mean()
    # Without TopCoW a median vessel from the AComA may carry the AComA label all the way up;
    # only the low part of A1/AComA counts as the root.
    is_root = is_root & (rs < ROOT_MAX_SUP_MM)
    roots_idx = np.nonzero(is_root)[0]
    dist = g.distances(roots_idx)
    # paths are traced on a graph that favours the vessel centre, so that the tube around
    # a path covers the whole vessel lumen
    edt = ndi.distance_transform_edt(U, sampling=spacing)[tuple(g.coords.T)]
    gc = core.VoxelGraph(U, spacing, node_weight=1.0 / (edt + 0.15) ** 2)
    _, pred, _ = csgraph.dijkstra(gc.graph, directed=False, indices=roots_idx,
                                  min_only=True, return_predecessors=True)
    d_acom = None
    if "AComA" in val:
        d_acom = g.distances(np.nonzero(lv == val["AComA"])[0])

    cand = (rp >= POST_MIN_MM) & (rs >= SUP_MIN_MM) & np.isfinite(dist)
    cm = np.zeros(lab.shape, bool)
    cm[tuple(g.coords[cand].T)] = True
    cl, n = ndi.label(cm, structure=core.STRUCT26)
    comp_of = cl[tuple(g.coords.T)]
    voxmm3 = float(np.prod(spacing))
    inv = {v: k for k, v in val.items()}
    vessels = []
    for k in range(1, n + 1):
        idx = np.nonzero(comp_of == k)[0]
        if len(idx) * voxmm3 < MIN_VOL_MM3:
            continue
        tip = idx[np.argmax(rp[idx])]
        path = _path_to_root(pred, tip)
        names_on = [inv[v] for v in lv[path]]
        tc_third = "A2 3rd" in names_on
        on_root = is_root[path]
        first = next((i for i, nm in enumerate(names_on) if nm not in ROOTS), None)
        if first is None:  # labelled AComA/A1 all the way: it leaves the root zone here
            first = int(np.argmin(on_root)) if not on_root.all() else len(path) - 1
            names_on[first:] = ["A2 3rd"] * (len(path) - first)
        root_name = names_on[first - 1] if first > 0 else names_on[0]
        start_name = names_on[first]
        # length of the run of the first distal label (e.g. 2.4 mm of A2 R before a third vessel)
        run = first
        while run < len(path) and names_on[run] == start_name:
            run += 1
        run_mm = float(dist[path[run - 1]] - dist[path[first]]) if run > first else 0.0
        notes = []
        if start_name in SIDE_OF:
            origin = SIDE_OF[start_name]
            depart = run if (run < len(path) and names_on[run] == "A2 3rd") else first
        elif root_name == "AComA" or names_on[first - 1] == "AComA":
            origin, depart = "AComA", first
        else:  # third vessel directly at the A1/A2 junction
            origin, depart = SIDE_OF.get(root_name, "?"), first
        if d_acom is not None and origin != "AComA" and depart > first:
            dd = float(d_acom[path[depart]])
            if dd <= NEAR_ACOMA_MM:
                notes.append(f"origin {dd:.1f} mm from the AComA – an AComA origin cannot be excluded")
        vessels.append(dict(path=path, origin=origin, depart=depart, tip=tip,
                            reach_post_mm=float(rp[tip]), reach_sup_mm=float(rs[idx].max()),
                            first_label=start_name, first_run_mm=run_mm, notes=notes,
                            third=tc_third))
    rs_all = rs
    for v in vessels:
        p = v["path"]; seg = p[v["depart"]:]
        v["genu"] = v["depart"] + int(np.argmin(rp[seg]))   # most anterior point = genu
        v["branches"] = []
    # Paths from one origin that separate only after the genu are branches of one vessel
    # (e.g. pericallosa + a higher posterior branch); the branch is shown but not named.
    # The lower one (closer to the corpus callosum) is kept as the vessel.
    vessels.sort(key=lambda v: v["reach_sup_mm"])
    kept = []
    for v in vessels:
        host = None
        for u in kept:
            if u["origin"] != v["origin"]:
                continue
            a, b = u["path"], v["path"]
            c = 0
            while c < min(len(a), len(b)) and a[c] == b[c]:
                c += 1
            if c - 1 > u["genu"]:
                host = u
                v["split_mm"] = float(dist[a[c - 1]])
                v["split_post_mm"] = float(rp[a[c - 1]]); v["split_sup_mm"] = float(rs_all[a[c - 1]])
                break
        if host is None:
            kept.append(v)
        else:
            host["branches"].append(v)
    vessels = kept
    ctx = dict(graph=g, lv=lv, rp=rp, dist=dist, val=val, inv=inv, is_root=is_root, d_acom=d_acom)
    return vessels, ctx


def _tube(g, nodes, mask_nodes, margin_mm=0.5):
    """Graph nodes within (vessel radius + margin) of `nodes`, restricted to mask_nodes."""
    sel = np.zeros(len(g.coords), bool)
    if not len(nodes):
        return sel
    edt = ndi.distance_transform_edt(g.mask, sampling=g.spacing)
    R = float(np.percentile(edt[tuple(g.coords[nodes].T)], 75))
    d = g.distances(nodes)
    return (d <= R + margin_mm) & mask_nodes


def classify_distal_aca(lab, names, spacing, post_vec, sup_vec):
    """Rename distal ACA voxels by course and origin. Returns (lab, names, report_lines)."""
    names = list(names)
    vessels, ctx = find_pericallosal_vessels(lab, names, spacing, post_vec, sup_vec)
    lines = []
    if ctx is None:
        return lab, names, lines
    g, lv, rp, dist, val, inv = (ctx[k] for k in ("graph", "lv", "rp", "dist", "val", "inv"))
    distal_nodes = np.isin(lv, [val[n] for n in DISTAL if n in val]) | (
        np.isin(lv, [val[n] for n in ROOTS if n in val]) & ~ctx["is_root"])

    # per origin: the largest vessel is the pericallosa of that side, further ones are variations
    by_side = {}
    for v in vessels:
        by_side.setdefault(v["origin"], []).append(v)
    for side, vs in by_side.items():
        vs.sort(key=lambda v: -(len(v["path"]) - v["depart"]))
        for i, v in enumerate(vs):
            if side == "AComA":
                v["abbr"], v["variation"], v["rami"] = "CallMed", True, "CallMed rami"
            elif side in ("R", "L"):
                v["abbr"] = f"Pericall {side}" if i == 0 else f"A2 {side} var"
                v["variation"] = i > 0
                v["rami"] = f"A2 {side} rami"
            else:
                v["abbr"], v["variation"], v["rami"] = "ACA var", True, "ACA var"
        # a further vessel from the same A2 starts where it leaves the main vessel's path
        if side in ("R", "L"):
            main = vs[0]["path"]
            for v in vs[1:]:
                p = v["path"]
                c = 0
                while c < min(len(p), len(main)) and p[c] == main[c]:
                    c += 1
                v["depart"] = max(v["depart"], c)
                v["notes"] = [f"leaves A2 {side} {dist[p[c]] - dist[p[0]]:.1f} mm from the A1/A2 junction"]
                if ctx["d_acom"] is not None and ctx["d_acom"][p[c]] <= NEAR_ACOMA_MM:
                    v["notes"].append("origin close to the AComA – an AComA origin cannot be excluded")

    new = lab.copy()

    def code(abbr):
        if abbr not in names:
            names.append(abbr)
        return names.index(abbr) + 1

    # each vessel: own part (tube around its path) and the trunk before it (A2 of its side)
    groups, gname = [], []
    claimed = np.zeros(len(g.coords), bool)
    for v in sorted(vessels, key=lambda v: v["variation"]):
        p = v["path"]
        start = v["depart"] if v["variation"] else v["genu"]   # A2 keeps its name up to the genu
        own = p[start:]
        trunk = [t for t in p[:start] if inv[lv[t]] not in ROOTS]
        t_own = _tube(g, own, distal_nodes & ~claimed)
        claimed |= t_own
        new[tuple(g.coords[t_own].T)] = code(v["abbr"])
        v["vol_mm3"] = float(t_own.sum() * np.prod(spacing))
        groups.append(g.distances(np.nonzero(t_own)[0])); gname.append(v["rami"])
        if trunk and v["origin"] in ("R", "L"):
            t_tr = _tube(g, np.array(trunk), distal_nodes & ~claimed)
            claimed |= t_tr
            new[tuple(g.coords[t_tr].T)] = code(f"A2 {v['origin']}")
            groups.append(g.distances(np.nonzero(t_tr)[0])); gname.append(f"A2 {v['origin']}")

    # remaining voxels of the sides that have a vessel (and of TopCoW's 3rd A2):
    # nearest to a pericallosal vessel -> its rami ("A2'nin diğer dalları"), nearest to a trunk -> A2
    sides = {v["origin"] for v in vessels}
    redo = [val[n] for n in ("A2 3rd",) if n in val]
    redo += [val[f"A2 {s}"] for s in ("R", "L") if s in sides and f"A2 {s}" in val]
    rest = np.isin(lv, redo) & ~claimed
    if groups and rest.any():
        D = np.vstack(groups)[:, rest]
        best = np.argmin(D, axis=0)
        ok = np.isfinite(D[best, np.arange(D.shape[1])])
        ri = np.nonzero(rest)[0]
        for gi in np.unique(best[ok]):
            sel = ri[ok & (best == gi)]
            new[tuple(g.coords[sel].T)] = code(gname[gi])
    # nothing should stay labelled 3rd A2 once it has been analysed
    if "A2 3rd" in val and vessels:
        left = (new == val["A2 3rd"])
        if left.any():
            new[left] = code("A2 3rd")

    # report
    lines.append("Distal ACA (pericallosal course = reaches "
                 f">= {POST_MIN_MM:.0f} mm posterior and >= {SUP_MIN_MM:.0f} mm superior to the AComA; "
                 "the corpus callosum itself is not visible on TOF, so this is an approximation):")
    if not vessels:
        lines.append("  no vessel with a pericallosal course was found (distal ACA may be outside the slab)")
    for v in vessels:
        org = {"R": "A2 R", "L": "A2 L"}.get(v["origin"], v["origin"])
        txt = (f"  {v['abbr']}: origin {org}, reaches {v['reach_post_mm']:.0f} mm posterior / "
               f"{v['reach_sup_mm']:.0f} mm superior to the AComA, {v['vol_mm3']:.0f} mm³")
        if v["third"]:
            txt += f"; TopCoW labelled it '3rd A2' (it leaves {v['first_label']} after {v['first_run_mm']:.1f} mm)"
        lines.append(txt)
        for nt in v["notes"]:
            lines.append(f"    {nt}")
        for b in v["branches"]:
            lines.append(f"    higher posterior branch from it at {b['split_post_mm']:.0f} mm posterior / "
                         f"{b['split_sup_mm']:.0f} mm superior, shown as {v['rami']} (not named)")
        if v["variation"]:
            lines.append(f"    {FLAG}")
    for side in ("R", "L"):
        if f"A2 {side}" in val and side not in sides:
            lines.append(f"  A2 {side}: no pericallosal course identified (only anterior / upward branches visualised)")
    if len(vessels) == 1:
        lines.append("  Tek perikallozal arter: azigos ya da bihemisferik ACA olasılığı, kontrol ediniz "
                     "(single pericallosal artery: possible azygos or bihemispheric ACA, please check)")
        lines.append(f"    {FLAG}")
    if len(vessels) >= 3:
        lines.append(f"  {len(vessels)} pericallosal-course vessels (triplicated distal ACA?)")
    return new, names, lines
