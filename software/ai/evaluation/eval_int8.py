"""Evaluate the INT8 integer model (M3).

Run from project root:
  .venv/bin/python software/ai/evaluation/eval_int8.py --sweep   # choose quantization settings on the 12 VALIDATION images only
  .venv/bin/python software/ai/evaluation/eval_int8.py           # final numbers on Set5/Set14/BSD100 with quantization/qparams.npz
Outputs: results/quality/m3_ptq_sweep.md   (sweep)
         results/quality/model_int8_x2.{md,csv}  (final; rows: bicubic, fp32, int8)
"""
import argparse
import csv
import sys
from pathlib import Path

import numpy as np

ROOT = Path(__file__).resolve().parents[3]
sys.path.insert(0, str(ROOT / "software" / "ai"))
from dataset.pairs import list_images, load_rgb, make_pair, upscale_pil  # noqa: E402
from evaluation.metrics import psnr_rgb, psnr_y, ssim_rgb, ssim_y  # noqa: E402
from models.srnet import predict_full  # noqa: E402
from quantization.integer_reference import QNet, upscale  # noqa: E402
from quantization.quantize import N_TRAIN, calibration_crops, load_fp32, quantize  # noqa: E402

SETS = ["Set5", "Set14", "BSD100"]
QPARAMS = ROOT / "software/ai/quantization/qparams.npz"


def qnet_from_arrays(arrays):
    from quantization.integer_reference import LAYER_SPEC
    layers = [dict(name=n, w=arrays[f"{n}_w"], b=arrays[f"{n}_b"], m=arrays[f"{n}_m"].astype(np.int64),
                   shift=int(arrays[f"{n}_shift"]), depthwise=dw) for n, _ci, _co, _k, dw in LAYER_SPEC]
    return QNet(layers)


def sweep():
    model = load_fp32()
    val = [make_pair(load_rgb(p), 2) for p in list_images(ROOT / "data" / "train" / "HR")[N_TRAIN:]]
    assert len(val) == 12
    crops = calibration_crops(100)
    fp = np.mean([psnr_y(hr, predict_full(model, lr), 2) for lr, hr in val])
    lines = ["# M3 PTQ sweep (12 validation images, PSNR-Y, calibration = 100 training crops)", "",
             f"FP32 reference on the same images: {fp:.3f} dB", "",
             "| percentile | weights | PSNR-Y int8 | drop vs FP32 (dB) |", "|---|---|---|---|"]
    for per_channel in (False, True):
        for pct in (99.0, 99.9, 99.99, 100.0):
            arrays, _ = quantize(model, crops, pct, per_channel)
            net = qnet_from_arrays(arrays)
            q = np.mean([psnr_y(hr, upscale(net, lr), 2) for lr, hr in val])
            lines.append(f"| {pct} | {'per-channel' if per_channel else 'per-layer'} | {q:.3f} | {fp - q:.3f} |")
            print(lines[-1], flush=True)
    text = "\n".join(lines) + "\n"
    (ROOT / "results" / "quality" / "m3_ptq_sweep.md").write_text(text)


def final():
    net, model = QNet.load(QPARAMS), load_fp32()
    rows = []
    for s in SETS:
        for p in list_images(ROOT / "data" / "test" / "HR" / s):
            lr, hr = make_pair(load_rgb(p), 2)
            outs = {"bicubic": upscale_pil(lr, 2), "fp32": predict_full(model, lr), "int8": upscale(net, lr)}
            for name, sr in outs.items():
                assert sr.shape == hr.shape and sr.dtype == np.uint8
                rows.append({"set": s, "image": p.stem, "method": name, "psnr_rgb": psnr_rgb(hr, sr), "ssim_rgb": ssim_rgb(hr, sr),
                             "psnr_y": psnr_y(hr, sr, 2), "ssim_y": ssim_y(hr, sr, 2)})
            print(s, p.stem, flush=True)
    out = ROOT / "results" / "quality"
    with open(out / "model_int8_x2.csv", "w", newline="") as f:
        w = csv.DictWriter(f, fieldnames=list(rows[0]))
        w.writeheader()
        w.writerows(rows)
    lines = ["# INT8 integer model vs FP32 vs bicubic, x2", "",
             "| Set | Method | PSNR RGB | SSIM RGB | PSNR Y | SSIM Y | images better than bicubic (PSNR Y) |", "|---|---|---|---|---|---|---|"]
    for s in SETS:
        bic = {r["image"]: float(r["psnr_y"]) for r in rows if r["set"] == s and r["method"] == "bicubic"}
        for m in ("bicubic", "fp32", "int8"):
            sel = [r for r in rows if r["set"] == s and r["method"] == m]
            mean = lambda k: float(np.mean([float(r[k]) for r in sel]))  # noqa: E731
            wins = sum(float(r["psnr_y"]) > bic[r["image"]] for r in sel) if m != "bicubic" else "-"
            lines.append(f"| {s} ({len(sel)}) | {m} | {mean('psnr_rgb'):.2f} | {mean('ssim_rgb'):.4f} | {mean('psnr_y'):.2f} | {mean('ssim_y'):.4f} | {wins} |")
    lines += ["", "Per-image drop int8 vs fp32 (PSNR Y, dB):", ""]
    for s in SETS:
        f32 = {r["image"]: float(r["psnr_y"]) for r in rows if r["set"] == s and r["method"] == "fp32"}
        d = np.array([f32[r["image"]] - float(r["psnr_y"]) for r in rows if r["set"] == s and r["method"] == "int8"])
        lines.append(f"* {s}: mean {d.mean():.3f}, worst {d.max():.3f}, best {d.min():.3f}")
    text = "\n".join(lines) + "\n"
    (out / "model_int8_x2.md").write_text(text)
    print(text)


if __name__ == "__main__":
    ap = argparse.ArgumentParser()
    ap.add_argument("--sweep", action="store_true")
    a = ap.parse_args()
    sweep() if a.sweep else final()
