"""Does replicate padding at the image edge hurt? Compare model gain over bicubic in the outer band vs the interior.

Run: .venv/bin/python software/ai/evaluation/border_effect.py [--ckpt ...]
Pools squared error (Y channel) over all Set5+Set14+BSD100 images; band = outer BAND HR pixels (BAND = 2*HALO + 2 = 8).
"""
import argparse
import sys
from pathlib import Path

import numpy as np

ROOT = Path(__file__).resolve().parents[3]
sys.path.insert(0, str(ROOT / "software" / "ai"))
from dataset.pairs import list_images, load_rgb, make_pair, upscale_pil  # noqa: E402
from evaluation.eval_model import load_model  # noqa: E402
from evaluation.metrics import rgb_to_y  # noqa: E402
from models.srnet import predict_full  # noqa: E402

BAND = 8


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--ckpt", default=str(ROOT / "software/ai/checkpoints/srnet_fp32.pt"))
    args = ap.parse_args()
    model, _ = load_model(args.ckpt)
    acc = {k: [0.0, 0] for k in ("bic_band", "mod_band", "bic_in", "mod_in")}
    for s in ("Set5", "Set14", "BSD100"):
        for p in list_images(ROOT / "data" / "test" / "HR" / s):
            lr, hr = make_pair(load_rgb(p), 2)
            y = rgb_to_y(hr)
            eb = (rgb_to_y(upscale_pil(lr, 2)) - y) ** 2
            em = (rgb_to_y(predict_full(model, lr)) - y) ** 2
            mask = np.zeros(y.shape, bool)
            mask[BAND:-BAND, BAND:-BAND] = True
            for tag, e in (("bic", eb), ("mod", em)):
                acc[f"{tag}_in"][0] += e[mask].sum(); acc[f"{tag}_in"][1] += mask.sum()
                acc[f"{tag}_band"][0] += e[~mask].sum(); acc[f"{tag}_band"][1] += (~mask).sum()
    psnr = lambda k: 10 * np.log10(255**2 / (acc[k][0] / acc[k][1]))  # noqa: E731
    for region in ("in", "band"):
        b, m = psnr(f"bic_{region}"), psnr(f"mod_{region}")
        print(f"{'interior' if region == 'in' else f'outer {BAND}px band':16} bicubic {b:.2f} dB   model {m:.2f} dB   gain {m - b:+.2f} dB")


if __name__ == "__main__":
    main()
