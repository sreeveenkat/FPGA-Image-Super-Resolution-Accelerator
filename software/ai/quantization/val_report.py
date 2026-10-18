"""FP32 and INT8 (integer model) PSNR-Y / SSIM-Y on the 42 clean validation images for a list of checkpoints.  Run from the project root:
  .venv/bin/python software/ai/quantization/val_report.py label=path [label=path ...]
A QAT checkpoint is exported with its own act_max / per_channel setting; any other checkpoint uses PTQ (99.99 percentile, per-layer).
Validation images only: nothing here touches the test sets.  (label=path:pc forces per-channel PTQ)"""
import sys
from pathlib import Path

import numpy as np
import torch

ROOT = Path(__file__).resolve().parents[3]
sys.path.insert(0, str(ROOT / "software" / "ai")); sys.path.insert(0, str(ROOT / "software" / "ai" / "training"))
from evaluation.eval_int8 import qnet_from_arrays  # noqa: E402
from evaluation.metrics import psnr_y, ssim_y  # noqa: E402
from models.srnet import predict_full  # noqa: E402
from quantization.integer_reference import upscale  # noqa: E402
from quantization.quantize import calibration_crops, load_fp32, quantize  # noqa: E402
from train_rep import load_val  # noqa: E402

val = load_val()
crops = calibration_crops(100)
print(f"{'config':<34}{'FP32 PSNR':>10}{'INT8 PSNR':>10}{'drop':>7}{'INT8 SSIM':>10}   weights")
for item in sys.argv[1:]:
    label, path = item.split("=", 1)
    force_pc = path.endswith(":pc")  # label=ckpt.pt:pc  -> PTQ with per-channel weight scales
    path = path[:-3] if force_pc else path
    ck = torch.load(path, map_location="cpu")
    m = load_fp32(path)
    pc = bool(ck.get("per_channel", force_pc))
    arr, _ = quantize(m, crops, 99.99, pc, ck.get("act_max"))
    q = qnet_from_arrays(arr)
    f = np.mean([psnr_y(hr, predict_full(m, lr), 2) for lr, hr in val])
    outs = [upscale(q, np.array(lr)) for lr, hr in val]
    i = np.mean([psnr_y(hr, o, 2) for (lr, hr), o in zip(val, outs)])
    s = np.mean([ssim_y(hr, o, 2) for (lr, hr), o in zip(val, outs)])
    print(f"{label:<34}{f:>10.3f}{i:>10.3f}{f - i:>7.3f}{s:>10.4f}   {'per-channel' if pc else 'per-layer'}{' (QAT)' if 'act_max' in ck else ' (PTQ)'}", flush=True)
