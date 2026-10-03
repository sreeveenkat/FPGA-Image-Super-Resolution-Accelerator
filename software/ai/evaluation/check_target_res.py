"""Run the trained model at the TARGET size (960x540 -> 1920x1080) and prove tiled == whole-image.

Run: .venv/bin/python software/ai/evaluation/check_target_res.py
Uses a validation image (never trained on). Tiles: 64x64 LR core + 3 px halo (the FPGA plan); LR padded to 960x576 -> 15x9 = 135 tiles.
Float tiles agree with the whole image to ~1e-6; a handful of uint8 values may differ by 1 purely from float summation order
(integer arithmetic in M3+ removes this).
"""
import sys
import time
from pathlib import Path

import numpy as np
import torch
import torch.nn.functional as F

ROOT = Path(__file__).resolve().parents[3]
sys.path.insert(0, str(ROOT / "software" / "ai"))
from dataset.pairs import list_images, load_rgb, make_pair, upscale_pil  # noqa: E402
from evaluation.eval_model import load_model  # noqa: E402
from evaluation.metrics import psnr_y  # noqa: E402
from models.srnet import HALO, predict_full  # noqa: E402


def main():
    model, _ = load_model(ROOT / "software/ai/checkpoints/srnet_fp32.pt")
    p = next(q for q in list_images(ROOT / "data/train/HR")[-12:] if min(load_rgb(q).shape[:2]) >= 1080 and load_rgb(q).shape[1] >= 1920)
    lr, hr = make_pair(load_rgb(p)[:1080, :1920], 2)
    assert lr.shape == (540, 960, 3) and hr.shape == (1080, 1920, 3)
    t = time.time()
    sr = predict_full(model, lr)
    print(f"{p.name}: whole image {lr.shape[:2]} -> {sr.shape[:2]} in {time.time() - t:.2f}s (CPU)")
    print(f"PSNR-Y model {psnr_y(hr, sr, 2):.2f} dB vs bicubic {psnr_y(hr, upscale_pil(lr, 2), 2):.2f} dB")

    x = torch.from_numpy(np.array(lr)).permute(2, 0, 1).float().div(255)[None]
    with torch.no_grad():
        whole = model(F.pad(x, (HALO,) * 4, mode="replicate"))
        H, W = lr.shape[:2]
        Hp, Wp = -(-H // 64) * 64, -(-W // 64) * 64
        xp = F.pad(F.pad(x, (0, Wp - W, 0, Hp - H), mode="replicate"), (HALO,) * 4, mode="replicate")
        out = torch.zeros(1, 3, 2 * Hp, 2 * Wp)
        n = 0
        for ty in range(0, Hp, 64):
            for tx in range(0, Wp, 64):
                out[:, :, 2 * ty:2 * ty + 128, 2 * tx:2 * tx + 128] = model(xp[:, :, ty:ty + 64 + 2 * HALO, tx:tx + 64 + 2 * HALO])
                n += 1
        out = out[:, :, :2 * H, :2 * W]
    q = lambda t: t.clamp(0, 1).mul(255).round().byte()  # noqa: E731
    fd = float((out - whole).abs().max())
    nd = int((q(out) != q(whole)).sum())
    md = int((q(out).int() - q(whole).int()).abs().max())
    print(f"tiles {n} | float max diff {fd:.2e} | uint8 values differing {nd} of {q(whole).numel()} (max diff {md})")
    assert n == 135 and fd < 1e-5 and md <= 1
    print("OK")


if __name__ == "__main__":
    main()
