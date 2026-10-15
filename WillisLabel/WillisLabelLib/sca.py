"""Superior cerebellar artery from the unseeded branches of the basilar artery.

TopCoW has no SCA class, so after labelling the SCAs are left as unnamed basilar branches
("BA rami"). Rule (from the anatomist): the SCA arises just below the posterior cerebral
artery, i.e. from the top of the basilar artery just below its bifurcation into the P1s.

A "BA rami" piece is named SCA R / SCA L if
  * it leaves the BA at most SCA_MAX_BELOW_MM below the P1 junction,
  * it runs laterally (>= SCA_MIN_LATERAL_MM from the BA axis), and
  * it does not run in front of the BA (reaches at least the level of the BA backwards), which
    excludes bright tissue in front of the BA (e.g. the dorsum sellae).
The side is the side the piece runs to. If several pieces qualify on one side, the largest is
named SCA and the report mentions the others (possible duplicated SCA).
Branches lower on the BA (AICA level) are not named.
"""

import numpy as np
from scipy import ndimage as ndi

from . import core

SCA_MAX_BELOW_MM = 10.0
SCA_MIN_LATERAL_MM = 6.0
SCA_MIN_POSTERIOR_MM = 0.0   # not running in front of the BA (TOF often shows only the first mm)
TOP_OF_BA = ("P1 R", "P1 L", "PCA R", "PCA L")


def name_sca(lab, names, spacing, post_vec, sup_vec, left_vec):
    """Rename qualifying BA side branches to SCA R / SCA L. Returns (lab, names, report_lines)."""
    names = list(names)
    lines = []
    if "BA" not in names or "BA rami" not in names:
        return lab, names, lines
    spacing = np.asarray(spacing, float)
    ba = lab == names.index("BA") + 1
    top_vals = [names.index(n) + 1 for n in TOP_OF_BA if n in names]
    if not top_vals:
        return lab, names, lines
    top = ba & ndi.binary_dilation(np.isin(lab, top_vals), core.STRUCT26)
    if not top.any():
        return lab, names, lines
    X = lambda m: np.argwhere(m) * spacing  # noqa: E731
    t = X(top).mean(0)
    rami = lab == names.index("BA rami") + 1
    comp, n = ndi.label(rami, structure=core.STRUCT26)
    ba_near = ndi.binary_dilation(ba, core.STRUCT26)
    found = {"R": [], "L": []}
    for k in range(1, n + 1):
        c = comp == k
        att = c & ba_near
        if not att.any():
            continue
        a = X(att).mean(0)
        P = X(c) - t
        below = float((t - a) @ sup_vec)
        lat = P @ left_vec
        post = P @ post_vec
        side = "L" if np.median(lat) > 0 else "R"
        lateral = float(np.abs(lat).max())
        posterior = float(post.max())
        vol = float(c.sum() * np.prod(spacing))
        ok = below <= SCA_MAX_BELOW_MM and lateral >= SCA_MIN_LATERAL_MM and posterior >= SCA_MIN_POSTERIOR_MM
        if ok:
            found[side].append((vol, k, below))
    for side, cands in found.items():
        if f"SCA {side}" in names:
            continue  # seeded by the user
        if not cands:
            lines.append(f"  SCA {side}: not identified among the basilar branches (place a seed if visible)")
            continue
        cands.sort(reverse=True)
        vol, k, below = cands[0]
        ab = f"SCA {side}"
        if ab not in names:
            names.append(ab)
        lab[comp == k] = names.index(ab) + 1
        lines.append(f"  SCA {side}: leaves the BA {max(below, 0):.0f} mm below the P1 junction, {vol:.0f} mm³")
        if len(cands) > 1:
            lines.append(f"    {len(cands) - 1} further branch(es) with the same course left as BA rami "
                         "(duplicated SCA?)")
    if lines:
        lines.insert(0, "Superior cerebellar arteries (branches of the BA just below the P1s, "
                        "running laterally and backwards):")
    return lab, names, lines
