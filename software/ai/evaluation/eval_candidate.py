"""Evaluate one candidate checkpoint (merged plain SRNet) with the project's protocol: Set5 / Set14 / BSD100, LR = modcrop + Pillow bicubic,
PSNR/SSIM on Y (BT.601) with a 2-px shave, Gaussian-window SSIM.  Writes results/quality/q_<name>.json (per-image values included).

Run from the project root:
  .venv/bin/python software/ai/evaluation/eval_candidate.py --name rep --ckpt software/ai/checkpoints/q/rep.pt          # FP32 + INT8 (PTQ, 99.99 %)
  .venv/bin/python software/ai/evaluation/eval_candidate.py --name rep_qat --ckpt software/ai/checkpoints/q/rep_qat.pt  # QAT checkpoint: INT8 with its act_max

For a checkpoint that carries `act_max` (QAT) the INT8 row uses exactly those ranges; otherwise the ranges are calibrated like M3 (99.99 percentile,
100 training crops).  The INT8 numbers always come from the NumPy integer model (the RTL golden reference), never from a simulation.
Selection of anything is done on the 42 clean validation images (`val` entry); the test sets are only reported.
"""
import argparse
import json
import sys
from pathlib import Path

import numpy as np
import torch

ROOT = Path(__file__).resolve().parents[3]
sys.path.insert(0, str(ROOT / "software" / "ai"))
from dataset.pairs import list_images, load_rgb, make_pair, upscale_pil  # noqa: E402
from evaluation.eval_int8 import qnet_from_arrays  # noqa: E402
from evaluation.metrics import psnr_y, ssim_y  # noqa: E402
from models.srnet import predict_full  # noqa: E402
from quantization.integer_reference import upscale  # noqa: E402
from quantization.quantize import calibration_crops, load_fp32, quantize  # noqa: E402

SETS = ["Set5", "Set14", "BSD100"]


def images():
    out = {s: [(p.stem, *make_pair(load_rgb(p), 2)) for p in list_images(ROOT / "data" / "test" / "HR" / s)] for s in SETS}
    from dataset.valsplit import VALID_DIR, SPLIT
    names = json.loads(SPLIT.read_text())["val42"]  # clean validation split, the only data any choice was made on
    out["val"] = [(Path(n).stem, *make_pair(load_rgb(VALID_DIR / n), 2)) for n in names]
    return out


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--name", required=True)
    ap.add_argument("--ckpt", required=True)
    ap.add_argument("--no-int8", action="store_true")
    ap.add_argument("--per-channel", action="store_true", help="PTQ with per-channel weight scales (a QAT checkpoint carries its own setting)")
    ap.add_argument("--no-bicubic", action="store_true")
    ap.add_argument("--no-fp32", action="store_true", help="skip the float run (QAT weights only make sense quantized)")
    a = ap.parse_args()
    torch.set_num_threads(4)
    ck = torch.load(a.ckpt, map_location="cpu")
    model = load_fp32(a.ckpt)
    qnet = None
    if not a.no_int8:
        arrays, _ = quantize(model, calibration_crops(100), 99.99, bool(ck.get("per_channel", a.per_channel)), ck.get("act_max"))
        qnet = qnet_from_arrays(arrays)
    res = {"name": a.name, "ckpt": a.ckpt, "act_max": ck.get("act_max"), "sets": {}}
    for s, imgs in images().items():
        methods = {} if a.no_fp32 else {"fp32": lambda lr: predict_full(model, lr)}
        if qnet is not None:
            methods["int8"] = lambda lr: upscale(qnet, lr)
        if not a.no_bicubic:
            methods["bicubic"] = lambda lr: upscale_pil(lr, 2)
        res["sets"][s] = {}
        for m, f in methods.items():
            rows = []
            for stem, lr, hr in imgs:
                sr = f(lr)
                rows.append({"image": stem, "psnr_y": psnr_y(hr, sr, 2), "ssim_y": ssim_y(hr, sr, 2)})
            res["sets"][s][m] = {"psnr_y": float(np.mean([r["psnr_y"] for r in rows])), "ssim_y": float(np.mean([r["ssim_y"] for r in rows])),
                                 "per_image": rows}
            print(f"{a.name:<14} {s:<7} {m:<8} PSNR-Y {res['sets'][s][m]['psnr_y']:.3f}  SSIM-Y {res['sets'][s][m]['ssim_y']:.4f}", flush=True)
    out = ROOT / "results" / "quality" / f"q_{a.name}.json"
    out.write_text(json.dumps(res, indent=1))
    print("wrote", out)


if __name__ == "__main__":
    main()
