"""M1: nearest / bicubic x2 baseline on Set5, Set14, BSD100.

Run from the project root:   .venv/bin/python software/ai/evaluation/eval_baseline.py
Outputs:
  data/test/LR/<set>/<name>.png            low-res inputs (Pillow bicubic of the even-cropped HR)
  results/quality/baseline_x2.{md,csv}     tables
  results/images/baseline_<set>_<name>.png side-by-side (nearest | bicubic | HR) for Set5 and Set14
  results/images/zoom_<set>_<name>.png     4x-zoomed edge-rich crop for Set5 and Set14
"""
import csv
import sys
from pathlib import Path

import cv2
import numpy as np

ROOT = Path(__file__).resolve().parents[3]
sys.path.insert(0, str(ROOT / "software" / "ai"))
from dataset.pairs import list_images, load_rgb, make_pair, save_rgb, upscale_cv2, upscale_pil  # noqa: E402
from evaluation.metrics import psnr_rgb, psnr_y, rgb_to_y, ssim_rgb, ssim_rgb_default, ssim_y  # noqa: E402

SCALE = 2
SETS = ["Set5", "Set14", "BSD100"]
FIGURE_SETS = {"Set5", "Set14"}
HR_DIR = ROOT / "data" / "test" / "HR"
LR_DIR = ROOT / "data" / "test" / "LR"
OUT_DIR = ROOT / "results" / "quality"
IMG_OUT = ROOT / "results" / "images"
METHODS = {  # name -> function(lr) -> sr
    "nearest": lambda lr: upscale_cv2(lr, SCALE, cv2.INTER_NEAREST),
    "bicubic": lambda lr: upscale_pil(lr, SCALE),          # project baseline (same kernel family as the LR protocol)
    "bicubic_cv2": lambda lr: upscale_cv2(lr, SCALE),       # OpenCV a=-0.75, for comparison only
}


def edge_rich_crop(hr: np.ndarray, size: int = 64):
    """Top-left (y, x) of the size x size HR window with the largest gradient energy (even-aligned)."""
    g = rgb_to_y(hr)
    gy, gx = np.gradient(g)
    e = np.cumsum(np.cumsum(gx**2 + gy**2, axis=0), axis=1)
    e = np.pad(e, ((1, 0), (1, 0)))
    h, w = g.shape
    best, pos = -1.0, (0, 0)
    for y in range(0, h - size + 1, 2):
        for x in range(0, w - size + 1, 2):
            v = e[y + size, x + size] - e[y, x + size] - e[y + size, x] + e[y, x]
            if v > best:
                best, pos = v, (y, x)
    return pos


def evaluate_set(set_name: str):
    rows = []
    for hr_path in list_images(HR_DIR / set_name):
        lr, hr = make_pair(load_rgb(hr_path), SCALE)
        save_rgb(LR_DIR / set_name / hr_path.name, lr)
        srs = {}
        for name, fn in METHODS.items():
            sr = fn(lr)
            assert sr.shape == hr.shape and sr.dtype == np.uint8
            srs[name] = sr
            rows.append({
                "set": set_name, "image": hr_path.stem, "method": name,
                "psnr_rgb": psnr_rgb(hr, sr), "ssim_rgb": ssim_rgb(hr, sr),
                "psnr_y": psnr_y(hr, sr, SCALE), "ssim_y": ssim_y(hr, sr, SCALE),
                "ssim_rgb_skimage_default": ssim_rgb_default(hr, sr),
            })
        if set_name in FIGURE_SETS:
            save_rgb(IMG_OUT / f"baseline_{set_name}_{hr_path.stem}.png",
                     np.concatenate([srs["nearest"], srs["bicubic"], hr], axis=1))
            y, x = edge_rich_crop(hr)
            crops = [c[y:y + 64, x:x + 64] for c in (srs["nearest"], srs["bicubic"], hr)]
            zoom = np.concatenate([cv2.resize(c, None, fx=4, fy=4, interpolation=cv2.INTER_NEAREST) for c in crops], axis=1)
            save_rgb(IMG_OUT / f"zoom_{set_name}_{hr_path.stem}.png", zoom)
    return rows


def main():
    rows = [r for s in SETS for r in evaluate_set(s)]

    OUT_DIR.mkdir(parents=True, exist_ok=True)
    with open(OUT_DIR / "baseline_x2.csv", "w", newline="") as f:
        w = csv.DictWriter(f, fieldnames=list(rows[0]))
        w.writeheader()
        w.writerows(rows)

    lines = ["# Baseline x2", "",
             "LR = Pillow bicubic of the even-cropped HR (bit-exact with official LR for even-sized images). 'bicubic' = Pillow bicubic upscale; 'bicubic_cv2' = OpenCV, comparison only.",
             "SSIM = Gaussian 11x11 (sigma 1.5). Y columns: BT.601 luma, 2-px border shaved. Means over all images in the set.", "",
             "| Set | Method | PSNR RGB (dB) | SSIM RGB | PSNR Y (dB) | SSIM Y |", "|---|---|---|---|---|---|"]
    for s in SETS:
        for m in METHODS:
            sel = [r for r in rows if r["set"] == s and r["method"] == m]
            mean = lambda k: float(np.mean([r[k] for r in sel]))  # noqa: E731
            lines.append(f"| {s} ({len(sel)}) | {m} | {mean('psnr_rgb'):.2f} | {mean('ssim_rgb'):.4f} | {mean('psnr_y'):.2f} | {mean('ssim_y'):.4f} |")
    text = "\n".join(lines) + "\n"
    (OUT_DIR / "baseline_x2.md").write_text(text)
    print(text)


if __name__ == "__main__":
    main()
