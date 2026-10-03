"""Evaluate the FP32 SRNet on Set5/Set14/BSD100 (x2) and compare with bicubic.

Run from project root:  .venv/bin/python software/ai/evaluation/eval_model.py [--ckpt ...] [--tag fp32]
Outputs: results/quality/model_<tag>_x2.{md,csv}, results/images/model_<tag>_<set>_<name>.png (bicubic | model | HR) for Set5/Set14,
         results/images/modelzoom_<tag>_<set>_<name>.png (4x zoom of the edge-rich crop)
"""
import argparse
import csv
import sys
from pathlib import Path

import cv2
import numpy as np
import torch

ROOT = Path(__file__).resolve().parents[3]
sys.path.insert(0, str(ROOT / "software" / "ai"))
from dataset.pairs import list_images, load_rgb, make_pair, save_rgb, upscale_pil  # noqa: E402
from evaluation.eval_baseline import edge_rich_crop  # noqa: E402
from evaluation.metrics import psnr_rgb, psnr_y, ssim_rgb, ssim_y  # noqa: E402
from models.srnet import SRNet, predict_full  # noqa: E402

SETS = ["Set5", "Set14", "BSD100"]


def load_model(path):
    ck = torch.load(path, map_location="cpu")
    m = SRNet(ck["scale"], ck["ch"])
    m.load_state_dict(ck["state"])
    return m.eval(), ck


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--ckpt", default=str(ROOT / "software/ai/checkpoints/srnet_fp32.pt"))
    ap.add_argument("--tag", default="fp32")
    args = ap.parse_args()
    model, ck = load_model(args.ckpt)
    print(f"checkpoint epoch {ck['epoch']} (val PSNR-Y {ck['val_psnr_y']:.3f})")
    out_dir, img_dir = ROOT / "results" / "quality", ROOT / "results" / "images"

    rows = []
    for s in SETS:
        for p in list_images(ROOT / "data" / "test" / "HR" / s):
            lr, hr = make_pair(load_rgb(p), 2)
            outs = {"bicubic": upscale_pil(lr, 2), args.tag: predict_full(model, lr)}
            for name, sr in outs.items():
                assert sr.shape == hr.shape
                rows.append({"set": s, "image": p.stem, "method": name, "psnr_rgb": psnr_rgb(hr, sr), "ssim_rgb": ssim_rgb(hr, sr),
                             "psnr_y": psnr_y(hr, sr, 2), "ssim_y": ssim_y(hr, sr, 2)})
            if s in ("Set5", "Set14"):
                save_rgb(img_dir / f"model_{args.tag}_{s}_{p.stem}.png", np.concatenate([outs["bicubic"], outs[args.tag], hr], axis=1))
                y, x = edge_rich_crop(hr)
                z = [cv2.resize(c[y:y + 64, x:x + 64], None, fx=4, fy=4, interpolation=cv2.INTER_NEAREST) for c in (outs["bicubic"], outs[args.tag], hr)]
                save_rgb(img_dir / f"modelzoom_{args.tag}_{s}_{p.stem}.png", np.concatenate(z, axis=1))

    with open(out_dir / f"model_{args.tag}_x2.csv", "w", newline="") as f:
        w = csv.DictWriter(f, fieldnames=list(rows[0]))
        w.writeheader()
        w.writerows(rows)
    lines = [f"# Model '{args.tag}' vs bicubic, x2 (checkpoint epoch {ck['epoch']})", "",
             "| Set | Method | PSNR RGB | SSIM RGB | PSNR Y | SSIM Y | images better than bicubic (PSNR Y) |", "|---|---|---|---|---|---|---|"]
    for s in SETS:
        bic = {r["image"]: float(r["psnr_y"]) for r in rows if r["set"] == s and r["method"] == "bicubic"}
        for m in ("bicubic", args.tag):
            sel = [r for r in rows if r["set"] == s and r["method"] == m]
            mean = lambda k: float(np.mean([float(r[k]) for r in sel]))  # noqa: E731
            wins = sum(float(r["psnr_y"]) > bic[r["image"]] for r in sel) if m != "bicubic" else "-"
            lines.append(f"| {s} ({len(sel)}) | {m} | {mean('psnr_rgb'):.2f} | {mean('ssim_rgb'):.4f} | {mean('psnr_y'):.2f} | {mean('ssim_y'):.4f} | {wins} |")
    text = "\n".join(lines) + "\n"
    (out_dir / f"model_{args.tag}_x2.md").write_text(text)
    print(text)


if __name__ == "__main__":
    main()
