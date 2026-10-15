"""Use a TopCoW multiclass circle-of-Willis segmentation as automatic seeds.

TopCoW label convention (TopCoW 2023/2024 challenge):
  1 BA, 2 R-PCA, 3 L-PCA, 4 R-ICA, 5 R-MCA, 6 L-ICA, 7 L-MCA,
  8 R-Pcom, 9 L-Pcom, 10 Acom, 11 R-ACA, 12 L-ACA, 15 3rd-A2

TopCoW's PCA contains P1 and the start of P2, and its ACA contains A1 and the start of A2.
They are split here by anatomical definition:
  P1 = PCA from the basilar bifurcation to the PComA junction
  A1 = ACA from the ICA terminus to the AComA junction
If the junction vessel is absent, the split is not possible and the whole segment is reported
as such (P2 / A2 seeds are not created and a note is added).
"""

import numpy as np
from scipy import ndimage as ndi

from . import core

TOPCOW = {
    1: "BA", 2: "PCA R", 3: "PCA L", 4: "ICA R", 5: "MCA R", 6: "ICA L", 7: "MCA L",
    8: "PComA R", 9: "PComA L", 10: "AComA", 11: "ACA R", 12: "ACA L", 15: "A2 3rd",
}

STRUCT26 = np.ones((3, 3, 3), bool)

# segment value, proximal neighbour values, junction neighbour value, (proximal name, distal name)
SPLITS = [
    (2, (1,), 8, ("P1 R", "P2 R")),
    (3, (1,), 9, ("P1 L", "P2 L")),
    (11, (4,), 10, ("A1 R", "A2 R")),
    (12, (6,), 10, ("A1 L", "A2 L")),
]


def _contact(lab, seg_mask, values):
    """Voxels of seg_mask that touch any voxel with a label in `values`."""
    other = np.isin(lab, values)
    return seg_mask & ndi.binary_dilation(other, STRUCT26)


def _split_segment(lab, seg_val, prox_vals, junc_val, spacing):
    """Return (proximal_mask, distal_mask) or None if the split is not defined."""
    seg = lab == seg_val
    if not seg.any():
        return None
    prox = _contact(lab, seg, prox_vals)
    junc = _contact(lab, seg, (junc_val,))
    if not prox.any() or not junc.any():
        return None
    g = core.VoxelGraph(seg, spacing)
    d = g.distances(g.nodes(np.argwhere(prox)))
    jd = d[g.nodes(np.argwhere(junc))]
    jd = jd[np.isfinite(jd)]
    if not len(jd):
        return None
    cut = float(np.median(jd))
    proximal = np.zeros(seg.shape, bool)
    proximal[tuple(g.coords[d <= cut].T)] = True
    distal = seg & ~proximal
    return proximal, distal


VISUALISED = "visualised"
PARTIAL = "partially visualised (not connected at both ends)"
ABSENT = "NOT visualised"


def _edge_state(lab, val, ends):
    """State of a circle-of-Willis edge: does segment `val` exist and touch every end in `ends`?"""
    m = lab == val
    if not m.any():
        return ABSENT
    if all(_contact(lab, m, (e,)).any() for e in ends):
        return VISUALISED
    return PARTIAL


def variant_summary(lab):
    """Circle of Willis edges as seen in the TopCoW segmentation (TopCoW variant-graph edges).

    Each value is VISUALISED, PARTIAL or ABSENT. 'Not visualised' on TOF is not proof of absence.
    """
    return {
        "A1 R": _edge_state(lab, 11, (4,)),
        "A1 L": _edge_state(lab, 12, (6,)),
        "AComA": _edge_state(lab, 10, (11, 12)),
        "3rd A2": VISUALISED if (lab == 15).any() else ABSENT,
        "PComA R": _edge_state(lab, 8, (4, 2)),
        "PComA L": _edge_state(lab, 9, (6, 3)),
        "P1 R": _edge_state(lab, 2, (1,)),
        "P1 L": _edge_state(lab, 3, (1,)),
    }


def seeds_from_topcow(lab, spacing, step=1):
    """Convert a TopCoW labelmap to WillisLabel seeds.

    Returns (seeds dict {abbr: [ijk,...]}, region dict {abbr: bool mask}, notes list)
    """
    seeds, region, notes = {}, {}, []
    handled = set()
    for seg_val, prox, junc, (pname, dname) in SPLITS:
        res = _split_segment(lab, seg_val, prox, junc, spacing)
        if res is None:
            if (lab == seg_val).any():
                name = TOPCOW[seg_val]
                region[name] = lab == seg_val
                notes.append(f"{name}: {pname}/{dname} not separable (junction vessel not visualised)")
            continue
        region[pname], region[dname] = res
        handled.add(seg_val)
    for v, name in TOPCOW.items():
        if v in handled or name in region:
            continue
        m = lab == v
        if m.any():
            region[name] = m
    for name, m in region.items():
        pts = np.argwhere(m)[::step]
        if len(pts):
            seeds[name] = [tuple(int(c) for c in p) for p in pts]
    return seeds, region, notes
