"""Run the TopCoW 2024 DKFZ circle-of-Willis model without Docker.

The checkpoints were trained with ``nnUNetTrainerSkeletonRecallNoMirroring``, a trainer that is
not part of the standard nnU-Net v2 package, so ``initialize_from_trained_model_folder`` cannot
load them. The skeleton-recall trainer only changes the training loss; the network itself is the
standard nnU-Net architecture described in ``plans.json``. The network is therefore built with
the standard ``nnUNetTrainer.build_network_architecture`` and the weights are loaded with
``nnUNetPredictor.manual_initialization``. With nnunetv2 2.5.1 the result was checked to be
voxel-identical to the output of the official TopCoW Docker image (IXI002, 5-fold ensemble).

The model folder is the ``_trained_model`` folder of the TopCoW DKFZ image (Zenodo 15665435):
``dataset.json``, ``plans.json`` and ``fold_0`` ... ``fold_4`` with ``checkpoint_final.pth``.
Please cite the TopCoW challenge paper (arXiv:2312.17670) when using it.
"""

import json
import os

NNUNET_REQUIREMENT = "nnunetv2==2.5.1"   # 2.6+ needs other dependency versions (blosc2, ...)
DKFZ_TOPCOW_3RD_A2 = (13, 15)            # the DKFZ model writes 3rd-A2 as 13; TopCoW uses 15
REQUIRED_FILES = ("dataset.json", "plans.json")


def available_folds(model_dir):
    """Fold numbers in model_dir that have a checkpoint_final.pth."""
    folds = []
    if not model_dir or not os.path.isdir(model_dir):
        return folds
    for name in sorted(os.listdir(model_dir)):
        if name.startswith("fold_") and name[5:].isdigit():
            if os.path.isfile(os.path.join(model_dir, name, "checkpoint_final.pth")):
                folds.append(int(name[5:]))
    return folds


def check_model_dir(model_dir):
    """Return a list of problems (empty if the folder looks like a TopCoW nnU-Net model)."""
    problems = []
    if not model_dir or not os.path.isdir(model_dir):
        return ["model folder not found"]
    for f in REQUIRED_FILES:
        if not os.path.isfile(os.path.join(model_dir, f)):
            problems.append(f"{f} missing")
    if not available_folds(model_dir):
        problems.append("no fold_N/checkpoint_final.pth found")
    if not problems:
        labels = json.load(open(os.path.join(model_dir, "dataset.json"), encoding="utf-8")).get("labels", {})
        if "Acom" not in labels or "BA" not in labels:
            problems.append("dataset.json does not have the TopCoW labels")
    return problems


def build_predictor(model_dir, folds=None, device=None):
    """nnUNetPredictor with the TopCoW weights loaded, without needing the custom trainer class."""
    import torch
    from nnunetv2.inference.predict_from_raw_data import nnUNetPredictor
    from nnunetv2.training.nnUNetTrainer.nnUNetTrainer import nnUNetTrainer
    from nnunetv2.utilities.label_handling.label_handling import determine_num_input_channels
    from nnunetv2.utilities.plans_handling.plans_handler import PlansManager

    problems = check_model_dir(model_dir)
    if problems:
        raise RuntimeError("Not a TopCoW model folder: " + "; ".join(problems))
    folds = list(folds) if folds else available_folds(model_dir)
    if device is None:
        device = torch.device("cuda" if torch.cuda.is_available() else "cpu")
    dataset_json = json.load(open(os.path.join(model_dir, "dataset.json"), encoding="utf-8"))
    plans = PlansManager(os.path.join(model_dir, "plans.json"))

    params, trainer_name, config, mirror = [], None, None, None
    for f in folds:
        ck = torch.load(os.path.join(model_dir, f"fold_{f}", "checkpoint_final.pth"),
                        map_location="cpu", weights_only=False)
        params.append(ck["network_weights"])
        trainer_name = ck["trainer_name"]
        config = ck["init_args"]["configuration"]
        mirror = ck.get("inference_allowed_mirroring_axes")
    cm = plans.get_configuration(config)
    n_in = determine_num_input_channels(plans, cm, dataset_json)
    n_out = plans.get_label_manager(dataset_json).num_segmentation_heads
    net = nnUNetTrainer.build_network_architecture(
        cm.network_arch_class_name, cm.network_arch_init_kwargs, cm.network_arch_init_kwargs_req_import,
        n_in, n_out, enable_deep_supervision=False)
    predictor = nnUNetPredictor(tile_step_size=0.5, use_gaussian=True, use_mirroring=True,
                                perform_everything_on_device=device.type == "cuda", device=device,
                                verbose=False, verbose_preprocessing=False, allow_tqdm=False)
    predictor.manual_initialization(net, plans, cm, params, dataset_json, trainer_name, mirror)
    return predictor


def predict_file(predictor, in_file, out_file):
    """Segment one image file (must be LPS-oriented) and write the TopCoW label map to out_file."""
    from nnunetv2.imageio.simpleitk_reader_writer import SimpleITKIO
    rw = SimpleITKIO()
    img, props = rw.read_images([in_file])
    seg = predictor.predict_single_npy_array(img, props, None)
    seg[seg == DKFZ_TOPCOW_3RD_A2[0]] = DKFZ_TOPCOW_3RD_A2[1]
    rw.write_seg(seg, out_file, props)
    return out_file
