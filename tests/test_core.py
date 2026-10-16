import numpy as np

from WillisLabelLib import core, anatomy


def synthetic_y(noise=20.0):
    """Trunk along k (axis 0) splitting into two branches."""
    arr = np.zeros((60, 60, 60), np.float32)
    kk, jj, ii = np.mgrid[0:60, 0:60, 0:60]
    trunk = ((jj - 30) ** 2 + (ii - 30) ** 2 <= 9) & (kk < 35)
    right = (((jj - 30) ** 2 + (ii - (30 - (kk - 34))) ** 2) <= 6) & (kk >= 34) & (kk < 55)
    left = (((jj - 30) ** 2 + (ii - (30 + (kk - 34))) ** 2) <= 6) & (kk >= 34) & (kk < 55)
    arr[trunk | right | left] = 1000
    arr += np.random.RandomState(0).normal(0, noise, arr.shape).astype(np.float32)
    return arr, trunk | right | left


def test_extract_vessels_recovers_tube():
    arr, truth = synthetic_y()
    m = core.extract_vessels(arr, (1, 1, 1), 500, 800, sigma_mm=0, min_size_mm3=1)
    dice = 2 * (m & truth).sum() / (m.sum() + truth.sum())
    assert dice > 0.95


def test_label_from_seeds_three_branches():
    arr, truth = synthetic_y()
    seeds = {"BA": [(10, 30, 30)], "P1 R": [(50, 30, 14)], "P1 L": [(50, 30, 46)]}
    lab, names, _ = core.label_from_seeds(truth, seeds, (1, 1, 1))
    assert names == ["BA", "P1 R", "P1 L"]
    assert lab[5, 30, 30] == 1
    assert lab[52, 30, 12] == 2
    assert lab[52, 30, 48] == 3
    assert set(np.unique(lab[truth])) == {1, 2, 3}


def test_unconnected_component_gets_own_label():
    arr, truth = synthetic_y()
    truth = truth.copy()
    truth[5:10, 5:10, 5:10] = True  # isolated blob
    lab, names, _ = core.label_from_seeds(truth, {"BA": [(10, 30, 30)]}, (1, 1, 1))
    assert lab[7, 7, 7] == core.UNCONNECTED


def test_snap_to_mask():
    _, truth = synthetic_y()
    assert core.snap_to_mask(truth, truth.astype(float), (10, 34, 30), (4, 4, 4)) is not None
    assert core.snap_to_mask(truth, truth.astype(float), (10, 5, 5), (2, 2, 2)) is None


def test_anatomy_catalogue_unique():
    abbrs = [a[0] for a in anatomy.ARTERIES]
    assert len(abbrs) == len(set(abbrs))
    assert {"A1 R", "A1 L", "AComA", "P1 R", "P1 L", "PComA R", "PComA L"} <= set(abbrs)


def test_topcow_split_p1_p2():
    from WillisLabelLib import topcow
    lab = np.zeros((40, 10, 10), np.uint8)
    lab[0:5, 5, 5] = 1      # BA
    lab[5:35, 5, 5] = 2     # R-PCA
    lab[20, 6:9, 5] = 8     # R-PComA joining PCA at index 20
    seeds, region, notes = topcow.seeds_from_topcow(lab, (1, 1, 1))
    assert not notes
    assert region["P1 R"][10, 5, 5] and region["P2 R"][30, 5, 5]
    assert not region["P1 R"][30, 5, 5]


def test_topcow_no_pcom_no_split():
    from WillisLabelLib import topcow
    lab = np.zeros((40, 10, 10), np.uint8)
    lab[0:5, 5, 5] = 1
    lab[5:35, 5, 5] = 2
    seeds, region, notes = topcow.seeds_from_topcow(lab, (1, 1, 1))
    assert "PCA R" in region and notes


def test_variant_states():
    from WillisLabelLib import topcow
    lab = np.zeros((40, 12, 12), np.uint8)
    lab[0:5, 5, 5] = 1
    lab[5:35, 5, 5] = 2          # R-PCA touching BA
    lab[20, 7:9, 5] = 8          # R-Pcom fragment, NOT touching PCA or ICA
    v = topcow.variant_summary(lab)
    assert v["P1 R"] == topcow.VISUALISED
    assert v["PComA R"] == topcow.PARTIAL
    assert v["AComA"] == topcow.ABSENT


def test_bridge_fragments_joins_faint_thin_branch_not_blob():
    img = np.full((40, 40, 80), 20.0, np.float32)
    trunk = np.zeros(img.shape, bool); trunk[19:22, 19:22, 0:30] = True
    faint = np.zeros(img.shape, bool); faint[20, 20, 30:40] = True        # faint gap
    branch = np.zeros(img.shape, bool); branch[19:21, 19:21, 40:60] = True  # thin distal piece
    blob = np.zeros(img.shape, bool); blob[2:10, 2:10, 60:68] = True       # thick isolated blob
    bridge_to_blob = np.zeros(img.shape, bool); bridge_to_blob[5, 5:20, 30] = True
    img[trunk | branch | blob] = 100.0
    img[faint | bridge_to_blob] = 80.0   # below the mask but above 0.75 x its low intensity
    mask = trunk | branch | blob
    new, rep = core.bridge_fragments(img, mask, [(20, 20, 5)], (1, 1, 1), sigma_mm=0)
    lab, n = __import__("scipy.ndimage", fromlist=["label"]).label(new, structure=np.ones((3, 3, 3)))
    assert lab[20, 20, 5] == lab[20, 20, 50]          # branch joined
    assert lab[5, 5, 64] != lab[20, 20, 5]            # blob not joined
    assert rep["joined"] == 1 and rep["rejected_thick"] == 1


def test_relabel_branch_renames_only_downstream_same_label():
    arr, truth = synthetic_y()
    # trunk BA (k<35), branches P1 R / P1 L; the right branch is wrongly labelled BA (1)
    kk, jj, ii = np.mgrid[0:60, 0:60, 0:60]
    lab = np.where(truth, 1, 0).astype(np.uint8)
    lab[truth & (kk >= 36) & (ii > 30)] = 2           # left branch correct: P1 L (2)
    names, ba = ["BA", "P1 L"], 1
    assert lab[52, 30, 12] == ba
    lab, info = core.relabel_branch(lab, (45, 30, 19), 9, (1, 1, 1), si_axis=0)
    assert info["old"] == ba and info["n"] > 20
    assert lab[52, 30, 12] == 9                      # distal right branch renamed
    assert lab[10, 30, 30] == ba                     # trunk untouched
    assert lab[52, 30, 48] == 2                      # other branch untouched


def test_relabel_path_only_between_clicks_in_a_loop():
    # a ring (like the circle of Willis): renaming one arc must not spread around the loop
    lab = np.zeros((10, 60, 60), np.uint8)
    jj, ii = np.mgrid[0:60, 0:60]
    r = np.hypot(jj - 30, ii - 30)
    lab[3:7][:, (r >= 18) & (r <= 21)] = 1
    lab, info = core.relabel_path(lab, (5, 30, 49), (5, 49, 30), 7, (1, 1, 1))
    assert info["n"] > 50
    assert lab[5, 44, 44] == 7          # on the arc between the clicks
    assert lab[5, 30, 11] == 1          # opposite side of the ring untouched
    assert lab[5, 11, 30] == 1
