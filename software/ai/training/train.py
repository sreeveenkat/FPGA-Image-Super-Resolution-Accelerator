"""M2: train SRNet (FP32) on the DIV2K training images.

Run from project root:  .venv/bin/python software/ai/training/train.py [--epochs 60] [--out software/ai/checkpoints/srnet_fp32.pt]
Validation images = last 5 training images (never used for training and never part of Set5/Set14/BSD100).
"""
import argparse
import json
import sys
import time
from pathlib import Path

import numpy as np
import torch
import torch.nn.functional as F

ROOT = Path(__file__).resolve().parents[3]
sys.path.insert(0, str(ROOT / "software" / "ai"))
from dataset.pairs import list_images, load_rgb, make_pair, upscale_pil  # noqa: E402
from evaluation.metrics import psnr_y  # noqa: E402
from models.srnet import HALO, SRNet, count_params, macs_per_input_pixel, predict_full  # noqa: E402

SCALE = 2


def gaussian_window(size=11, sigma=1.5):
    g = torch.arange(size, dtype=torch.float32) - size // 2
    g = torch.exp(-(g**2) / (2 * sigma**2))
    g = g / g.sum()
    return (g[:, None] * g[None, :]).expand(3, 1, size, size).contiguous()


def ssim_loss(a, b, win):
    """1 - mean SSIM (Gaussian 11x11, sigma 1.5, data_range 1). Differentiable; used ONLY as a training loss."""
    c1, c2 = 0.01**2, 0.03**2
    f = lambda t: F.conv2d(t, win, groups=3)  # noqa: E731
    ma, mb = f(a), f(b)
    saa, sbb, sab = f(a * a) - ma * ma, f(b * b) - mb * mb, f(a * b) - ma * mb
    s = ((2 * ma * mb + c1) * (2 * sab + c2)) / ((ma * ma + mb * mb + c1) * (saa + sbb + c2))
    return 1 - s.mean()


def load_pairs(paths):
    out = []
    for p in paths:
        lr, hr = make_pair(load_rgb(p), SCALE)
        out.append((lr, hr))
    return out


def sample_batch(pairs, rng, batch, lr_patch, edge_aug=False):
    """LR window (patch+2*HALO) and matching HR patch (2*patch). Flips/rot90 augmentation.

    edge_aug=False: window lies fully inside the image (real neighbours everywhere).
    edge_aug=True : LR is replicate-padded by HALO first, so cores that touch the image edge are also sampled
                    (exactly the padding used at inference for full images).
    """
    win = lr_patch + 2 * HALO
    xs, ys = [], []
    for _ in range(batch):
        lr, hr = pairs[rng.integers(len(pairs))]
        h, w = lr.shape[:2]
        if edge_aug:
            lrp = np.pad(lr, ((HALO, HALO), (HALO, HALO), (0, 0)), mode="edge")
            y0, x0 = rng.integers(0, h - lr_patch + 1), rng.integers(0, w - lr_patch + 1)  # core start in image coords
            a = lrp[y0:y0 + win, x0:x0 + win]
            b = hr[y0 * SCALE:(y0 + lr_patch) * SCALE, x0 * SCALE:(x0 + lr_patch) * SCALE]
        else:
            y0, x0 = rng.integers(0, h - win + 1), rng.integers(0, w - win + 1)
            a = lr[y0:y0 + win, x0:x0 + win]
            b = hr[(y0 + HALO) * SCALE:(y0 + HALO + lr_patch) * SCALE, (x0 + HALO) * SCALE:(x0 + HALO + lr_patch) * SCALE]
        k = rng.integers(4)
        a, b = np.rot90(a, k), np.rot90(b, k)
        if rng.integers(2):
            a, b = a[:, ::-1], b[:, ::-1]
        xs.append(np.ascontiguousarray(a))
        ys.append(np.ascontiguousarray(b))
    x = torch.from_numpy(np.stack(xs)).permute(0, 3, 1, 2).float().div(255)
    y = torch.from_numpy(np.stack(ys)).permute(0, 3, 1, 2).float().div(255)
    return x, y


def validate(model, val_pairs):
    sr = [psnr_y(hr, predict_full(model, lr), SCALE) for lr, hr in val_pairs]
    bic = [psnr_y(hr, upscale_pil(lr, SCALE), SCALE) for lr, hr in val_pairs]
    return float(np.mean(sr)), float(np.mean(bic))


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--epochs", type=int, default=60)
    ap.add_argument("--steps", type=int, default=400, help="steps per epoch")
    ap.add_argument("--batch", type=int, default=32)
    ap.add_argument("--patch", type=int, default=32, help="LR patch size (output core)")
    ap.add_argument("--ch", type=int, default=16)
    ap.add_argument("--lr", type=float, default=2e-3)
    ap.add_argument("--seed", type=int, default=0)
    ap.add_argument("--images", type=int, default=60, help="use only the first N training images (60 = original recipe)")
    ap.add_argument("--val", type=int, default=5, help="last K of those images are validation")
    ap.add_argument("--ssim", type=float, default=0.0, help="weight of (1-SSIM) loss term added to L1")
    ap.add_argument("--edge-aug", action="store_true", help="also sample windows that touch the image edge (replicate pad)")
    ap.add_argument("--threads", type=int, default=0, help="torch threads (0 = default)")
    ap.add_argument("--out", default=str(ROOT / "software/ai/checkpoints/srnet_fp32.pt"))
    args = ap.parse_args()

    if args.threads:
        torch.set_num_threads(args.threads)
    torch.manual_seed(args.seed)
    rng = np.random.default_rng(args.seed)
    paths = list_images(ROOT / "data" / "train" / "HR")[: args.images]
    train_pairs, val_pairs = load_pairs(paths[: -args.val]), load_pairs(paths[-args.val:])
    win = gaussian_window()
    print(f"train {len(train_pairs)} imgs, val {len(val_pairs)} imgs; params={count_params(SRNet(ch=args.ch))} "
          f"MACs/px={macs_per_input_pixel(args.ch)}", flush=True)

    model = SRNet(SCALE, args.ch)
    opt = torch.optim.Adam(model.parameters(), lr=args.lr)
    sched = torch.optim.lr_scheduler.CosineAnnealingLR(opt, T_max=args.epochs * args.steps, eta_min=args.lr / 100)
    best, log = -1.0, []
    t0 = time.time()
    for ep in range(1, args.epochs + 1):
        model.train()
        tot = 0.0
        for _ in range(args.steps):
            x, y = sample_batch(train_pairs, rng, args.batch, args.patch, args.edge_aug)
            out = model(x)
            loss = F.l1_loss(out, y)
            if args.ssim > 0:
                loss = loss + args.ssim * ssim_loss(out, y, win)
            opt.zero_grad()
            loss.backward()
            opt.step()
            sched.step()
            tot += loss.item()
        v, vb = validate(model, val_pairs)
        log.append({"epoch": ep, "train_l1": tot / args.steps, "val_psnr_y": v, "val_bicubic_psnr_y": vb})
        if v > best:
            best = v
            Path(args.out).parent.mkdir(parents=True, exist_ok=True)
            torch.save({"state": model.state_dict(), "ch": args.ch, "scale": SCALE, "epoch": ep, "val_psnr_y": v, "args": vars(args)}, args.out)
        print(f"ep {ep:3d} l1 {tot / args.steps:.5f} val PSNR-Y {v:.3f} (bicubic {vb:.3f}) best {best:.3f} [{time.time() - t0:.0f}s]", flush=True)
    Path(args.out).with_suffix(".log.json").write_text(json.dumps(log, indent=1))


if __name__ == "__main__":
    main()
