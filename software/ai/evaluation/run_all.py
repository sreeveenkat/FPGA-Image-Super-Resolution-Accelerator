"""M7 table A: nearest, bicubic, FP32, INT8 and FPGA (board) quality on Set5 / Set14 / BSD100, x2, in one table.

Run from project root:
  .venv/bin/python software/ai/evaluation/run_all.py            # needs the board outputs (software/board/run_testsets.sh)
  .venv/bin/python software/ai/evaluation/run_all.py --no-fpga  # PC rows only
Outputs: results/quality/table_a_x2.{md,csv}

Every number is RECOMPUTED here from the models / the saved board outputs (same LR protocol and metric code as M1-M3), and then checked:
  * nearest / bicubic / FP32 / INT8 per-image metrics must equal the published CSVs (baseline_x2, model_fp32_x2, model_int8_x2) to 1e-9;
  * every FPGA output must be byte-identical to the integer model (so its metrics equal the INT8 row exactly).
Exit code 1 if any check fails (nothing is written then).
"""
import argparse
import csv
import sys
from pathlib import Path

import cv2
import numpy as np

ROOT = Path(__file__).resolve().parents[3]
sys.path.insert(0, str(ROOT / "software" / "ai"))
sys.path.insert(0, str(ROOT / "software" / "host_tools"))
from dataset.pairs import list_images, load_rgb, make_pair, upscale_cv2, upscale_pil  # noqa: E402
from evaluation.metrics import psnr_rgb, psnr_y, ssim_rgb, ssim_y  # noqa: E402
from models.srnet import predict_full  # noqa: E402
from quantization.integer_reference import QNet, upscale  # noqa: E402
from quantization.quantize import load_fp32  # noqa: E402
from srim import read_srim  # noqa: E402

SETS = ["Set5", "Set14", "BSD100"]
METHODS = ["nearest", "bicubic", "fp32", "int8", "fpga"]
KEYS = ["psnr_rgb", "ssim_rgb", "psnr_y", "ssim_y"]
QDIR = ROOT / "results" / "quality"
PUBLISHED = {"nearest": "baseline_x2.csv", "bicubic": "baseline_x2.csv", "fp32": "model_fp32_x2.csv", "int8": "model_int8_x2.csv"}
BOARD = ROOT / "data" / "board" / "testsets"


def published():
    pub = {}
    for m, fn in PUBLISHED.items():
        with open(QDIR / fn) as f:
            for r in csv.DictReader(f):
                if r["method"] == m:
                    pub[(r["set"], r["image"], m)] = {k: float(r[k]) for k in KEYS}
    return pub


def main(no_fpga: bool) -> int:
    net, model, pub = QNet.load(ROOT / "software/ai/quantization/qparams.npz"), load_fp32(), published()
    rows, errors, maxdiff = [], [], 0.0
    for s in SETS:
        for p in list_images(ROOT / "data" / "test" / "HR" / s):
            lr, hr = make_pair(load_rgb(p), 2)
            q = upscale(net, lr)
            outs = {"nearest": upscale_cv2(lr, 2, cv2.INTER_NEAREST), "bicubic": upscale_pil(lr, 2), "fp32": predict_full(model, lr), "int8": q}
            if not no_fpga:
                bf = BOARD / s / f"{p.stem}_board.raw"
                if not bf.exists():
                    errors.append(f"{s}/{p.stem}: board output missing ({bf})")
                    continue
                b = read_srim(bf)
                if b.shape != q.shape or not np.array_equal(b, q):
                    errors.append(f"{s}/{p.stem}: board output NOT byte-identical to the integer model")
                    continue
                outs["fpga"] = b
            for m, sr in outs.items():
                r = {"set": s, "image": p.stem, "method": m, "psnr_rgb": psnr_rgb(hr, sr), "ssim_rgb": ssim_rgb(hr, sr),
                     "psnr_y": psnr_y(hr, sr, 2), "ssim_y": ssim_y(hr, sr, 2)}
                rows.append(r)
                ref = pub.get((s, p.stem, "int8" if m == "fpga" else m))
                if ref is None:
                    errors.append(f"{s}/{p.stem}/{m}: no published row")
                    continue
                d = max(abs(r[k] - ref[k]) for k in KEYS)
                maxdiff = max(maxdiff, d)
                if d > 1e-9:
                    errors.append(f"{s}/{p.stem}/{m}: differs from the published value by {d:.3g}")
            print(s, p.stem, flush=True)
    for e in errors:
        print("FAIL", e)
    print(f"max |recomputed - published| over all metrics: {maxdiff:.3g}")
    if errors:
        print(f"run_all: {len(errors)} checks failed; nothing written")
        return 1
    methods = [m for m in METHODS if not (no_fpga and m == "fpga")]
    with open(QDIR / "table_a_x2.csv", "w", newline="") as f:
        w = csv.DictWriter(f, fieldnames=list(rows[0]))
        w.writeheader()
        w.writerows(rows)
    lines = ["# Table A - image quality x2 (Set5 / Set14 / BSD100)", "",
             "Recomputed by `software/ai/evaluation/run_all.py`; nearest/bicubic/FP32/INT8 equal the published M1-M3 CSVs (max difference "
             f"{maxdiff:.1g}); " + ("no FPGA row (--no-fpga)." if no_fpga else
                                    "FPGA = the outputs read back from the ZedBoard (board-measured), each byte-identical to the INT8 integer model."),
             "PSNR in dB. Y = BT.601 luma, 2-px border shaved. SSIM = Gaussian 11x11, sigma 1.5. Means over all images of a set.", "",
             "| Set | Method | PSNR RGB | SSIM RGB | PSNR Y | SSIM Y | better than bicubic (PSNR Y) |", "|---|---|---|---|---|---|---|"]
    for s in SETS:
        bic = {r["image"]: r["psnr_y"] for r in rows if r["set"] == s and r["method"] == "bicubic"}
        for m in methods:
            sel = [r for r in rows if r["set"] == s and r["method"] == m]
            mean = lambda k: float(np.mean([r[k] for r in sel]))  # noqa: E731
            wins = f"{sum(r['psnr_y'] > bic[r['image']] for r in sel)}/{len(sel)}" if m not in ("nearest", "bicubic") else "-"
            lines.append(f"| {s} ({len(sel)}) | {m} | {mean('psnr_rgb'):.2f} | {mean('ssim_rgb'):.4f} | {mean('psnr_y'):.2f} | {mean('ssim_y'):.4f} | {wins} |")
    text = "\n".join(lines) + "\n"
    (QDIR / "table_a_x2.md").write_text(text)
    print(text)
    return 0


if __name__ == "__main__":
    ap = argparse.ArgumentParser()
    ap.add_argument("--no-fpga", action="store_true")
    sys.exit(main(ap.parse_args().no_fpga))
