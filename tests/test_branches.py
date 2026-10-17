import numpy as np

from WillisLabelLib import branches


def y_tree():
    """Trunk rising along axis 0 that splits into two branches (1 mm voxels)."""
    m = np.zeros((60, 60, 60), bool)
    kk, jj, ii = np.mgrid[0:60, 0:60, 0:60]
    m |= ((jj - 30) ** 2 + (ii - 30) ** 2 <= 9) & (kk < 35)
    m |= (((jj - 30) ** 2 + (ii - (30 - (kk - 34))) ** 2) <= 6) & (kk >= 34) & (kk < 55)
    m |= (((jj - 30) ** 2 + (ii - (30 + (kk - 34))) ** 2) <= 6) & (kk >= 34) & (kk < 55)
    return m


def test_y_tree_gives_three_branches():
    m = y_tree()
    lab, n = branches.split_branches(m, (1, 1, 1), si_axis=0)
    assert n == 3
    trunk, left, right = lab[10, 30, 30], lab[50, 30, 46], lab[50, 30, 14]
    assert len({trunk, left, right}) == 3 and 0 not in (trunk, left, right)
    assert (lab[m] > 0).all()


def test_small_bump_is_not_a_branch():
    m = y_tree()
    m[20, 30, 33:36] = True          # 2-voxel bump on the trunk
    lab, n = branches.split_branches(m, (1, 1, 1), si_axis=0)
    assert n == 3


def test_branch_at_snaps_to_nearest_branch():
    m = y_tree()
    lab, _ = branches.split_branches(m, (1, 1, 1), si_axis=0)
    assert branches.branch_at(lab, (10, 30, 34), (1, 1, 1)) == lab[10, 30, 30]   # 1 voxel off the trunk
    assert branches.branch_at(lab, (10, 5, 5), (1, 1, 1)) is None


def trunk_with_side_branch():
    """Thick trunk (r = 3 vox) along axis 0 with a thin side branch (r = 1 vox) leaving at k = 20."""
    m = np.zeros((60, 60, 60), bool)
    kk, jj, ii = np.mgrid[0:60, 0:60, 0:60]
    m |= ((jj - 30) ** 2 + (ii - 30) ** 2 <= 9) & (kk < 55)
    m |= ((kk - (20 + (ii - 30) // 2)) ** 2 + (jj - 30) ** 2 <= 1) & (ii >= 30) & (ii < 50)
    return m


def test_trunk_keeps_its_number_past_a_thin_side_branch():
    m = trunk_with_side_branch()
    lab, n = branches.split_branches(m, (1, 1, 1), si_axis=0)
    assert lab[5, 30, 30] == lab[50, 30, 30]          # one trunk label below and above the side branch
    assert lab[28, 30, 46] not in (0, lab[5, 30, 30])  # side branch is its own branch
    assert n == 2


def test_side_ratio_zero_cuts_trunk_at_every_bifurcation():
    m = trunk_with_side_branch()
    lab, n = branches.split_branches(m, (1, 1, 1), si_axis=0, side_ratio=0)
    assert lab[5, 30, 30] != lab[50, 30, 30]
