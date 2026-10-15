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
