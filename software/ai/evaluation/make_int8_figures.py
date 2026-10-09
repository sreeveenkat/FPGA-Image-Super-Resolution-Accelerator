"""Comparison figures for the INT8 integer model (Set5 + Set14 + BSD100).

Run from project root:  .venv/bin/python software/ai/evaluation/make_int8_figures.py
Writes results/images/model_int8_<set>_<name>.png  (panels left to right: LR (nearest-neighbour enlarged) | bicubic | FP32 CNN | INT8 CNN | HR)
and results/images/modelzoom_int8_<set>_<name>.png (same panels, 4x nearest-neighbour zoom of the sharpest-edge crop).
Does not touch results/quality.
"""
import sys
from pathlib import Path

import cv2
import numpy as np

ROOT = Path(__file__).resolve().parents[3]
sys.path.insert(0, str(ROOT / "software" / "ai"))
from dataset.pairs import list_images, load_rgb, make_pair, save_rgb, upscale_pil  # noqa: E402
from models.srnet import predict_full  # noqa: E402
from quantization.integer_reference import QNet, upscale  # noqa: E402
from quantization.quantize import load_fp32  # noqa: E402

net, model = QNet.load(ROOT / "software/ai/quantization/qparams.npz"), load_fp32()
img_dir = ROOT / "results" / "images"
CROP = 48
for s in ("Set5", "Set14", "BSD100"):
    for p in list_images(ROOT / "data" / "test" / "HR" / s):
        lr, hr = make_pair(load_rgb(p), 2)
        lr_big = cv2.resize(lr, None, fx=2, fy=2, interpolation=cv2.INTER_NEAREST)  # LR shown at HR size (pixel-replicated)
        panels = [lr_big, upscale_pil(lr, 2), predict_full(model, lr), upscale(net, lr), hr]
        save_rgb(img_dir / f"model_int8_{s}_{p.stem}.png", np.concatenate(panels, axis=1))
        # crop = window of the HR with the largest gradient energy (same for all panels)
        g = cv2.Laplacian(cv2.cvtColor(hr, cv2.COLOR_RGB2GRAY).astype(np.float32), cv2.CV_32F) ** 2
        ii = cv2.integral(g)
        h, w = g.shape
        best, pos = -1.0, (0, 0)
        for y in range(0, h - CROP, 8):
            for x in range(0, w - CROP, 8):
                v = ii[y + CROP, x + CROP] - ii[y, x + CROP] - ii[y + CROP, x] + ii[y, x]
                if v > best:
                    best, pos = v, (y, x)
        y, x = pos
        z = [cv2.resize(q[y:y + CROP, x:x + CROP], None, fx=4, fy=4, interpolation=cv2.INTER_NEAREST) for q in panels]
        save_rgb(img_dir / f"modelzoom_int8_{s}_{p.stem}.png", np.concatenate(z, axis=1))
        print(s, p.stem, flush=True)
