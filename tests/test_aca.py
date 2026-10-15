import numpy as np

from WillisLabelLib import aca, core

SP = (0.5, 0.5, 0.5)            # array axes: superior, posterior, left (mm)
POST = np.array([0.0, 1.0, 0.0])
SUP = np.array([1.0, 0.0, 0.0])


def tube(shape, pts, r=0.8):
    """Binary tube along a polyline given in mm (S, P, L)."""
    m = np.zeros(shape, bool)
    grid = np.indices(shape).reshape(3, -1).T * np.array(SP)
    for a, b in zip(pts[:-1], pts[1:]):
        a, b = np.array(a, float), np.array(b, float)
        ab = b - a
        t = np.clip(((grid - a) @ ab) / (ab @ ab), 0, 1)
        d = np.linalg.norm(grid - (a + t[:, None] * ab), axis=1)
        m |= (d <= r).reshape(shape)
    return m


def build(third=None, left=True):
    shape = (60, 110, 60)  # 30 x 55 x 30 mm
    parts = {
        "A1 R": [(4, 20, 3), (4, 20, 12)],
        "AComA": [(4, 20, 12), (4, 20, 18)],
        "A1 L": [(4, 20, 18), (4, 20, 27)],
        # A2 R: up and forward to the genu, then back along the corpus callosum
        "A2 R": [(4, 20, 12), (14, 10, 10), (20, 16, 10), (22, 30, 10), (22, 50, 10)],
        # an anterior / upward branch of A2 R (frontopolar-like)
        "front R": [(14, 10, 10), (24, 3, 8)],
    }
    if left:
        parts["A2 L"] = [(4, 20, 18), (14, 10, 20), (20, 16, 20), (22, 30, 20), (22, 50, 20)]
    if third == "AComA":
        parts["third"] = [(4, 20, 15), (12, 12, 15), (18, 18, 15), (19, 45, 15)]
    if third == "A2 R":
        parts["third"] = [(9, 15, 11), (13, 14, 14.5), (18, 19, 15), (19, 45, 15)]
    masks = {k: tube(shape, v) for k, v in parts.items()}
    mask = np.any(list(masks.values()), axis=0)
    seeds = {"A1 R": [(8, 40, 10)], "A1 L": [(8, 40, 46)], "AComA": [(8, 40, 30)],
             "A2 R": [(28, 20, 20)]}
    if left:
        seeds["A2 L"] = [(28, 20, 40)]
    lab, names, _ = core.label_from_seeds(mask, seeds, SP)
    return lab, names


def run(**kw):
    lab, names = build(**kw)
    new, names, lines = aca.classify_distal_aca(lab, names, SP, POST, SUP)
    vols = {n: int((new == i + 1).sum()) for i, n in enumerate(names)}
    return vols, "\n".join(lines)


def test_two_pericallosal_arteries():
    vols, rep = run()
    assert vols["Pericall R"] > 50 and vols["Pericall L"] > 50
    assert vols.get("A2 R rami", 0) > 10        # the anterior branch
    assert "VARYASYON" not in rep and "Tek perikallozal" not in rep


def test_median_callosal_artery_from_acoma():
    vols, rep = run(third="AComA")
    assert vols.get("CallMed", 0) > 50, rep
    assert vols["Pericall R"] > 50 and vols["Pericall L"] > 50
    assert "VARYASYON" in rep and "origin AComA" in rep


def test_variation_branch_from_a2():
    vols, rep = run(third="A2 R")
    assert vols.get("A2 R var", 0) > 50, rep
    assert "VARYASYON" in rep


def test_single_pericallosal_artery():
    vols, rep = run(left=False)
    assert vols["Pericall R"] > 50
    assert "Tek perikallozal arter" in rep and "VARYASYON" in rep
