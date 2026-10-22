import json

from WillisLabelLib import topcow_infer


def _model(tmp_path, folds=(0, 1), labels=None):
    labels = labels or {"background": 0, "BA": 1, "Acom": 10, "3rd-A2": 13}
    (tmp_path / "dataset.json").write_text(json.dumps({"labels": labels}))
    (tmp_path / "plans.json").write_text("{}")
    for f in folds:
        d = tmp_path / f"fold_{f}"
        d.mkdir()
        (d / "checkpoint_final.pth").write_bytes(b"")
    return str(tmp_path)


def test_valid_model_folder(tmp_path):
    m = _model(tmp_path, folds=(0, 1, 2, 3, 4))
    assert topcow_infer.check_model_dir(m) == []
    assert topcow_infer.available_folds(m) == [0, 1, 2, 3, 4]


def test_missing_files_reported(tmp_path):
    assert topcow_infer.check_model_dir(str(tmp_path / "nope")) == ["model folder not found"]
    (tmp_path / "plans.json").write_text("{}")
    problems = topcow_infer.check_model_dir(str(tmp_path))
    assert "dataset.json missing" in problems
    assert any("checkpoint_final.pth" in p for p in problems)


def test_wrong_labels_rejected(tmp_path):
    m = _model(tmp_path, labels={"background": 0, "liver": 1})
    assert any("TopCoW labels" in p for p in topcow_infer.check_model_dir(m))


def test_fold_without_checkpoint_ignored(tmp_path):
    m = _model(tmp_path, folds=(0,))
    (tmp_path / "fold_3").mkdir()
    assert topcow_infer.available_folds(m) == [0]


def test_3rd_a2_mapping():
    assert topcow_infer.DKFZ_TOPCOW_3RD_A2 == (13, 15)
