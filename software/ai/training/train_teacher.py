"""Train the distillation TEACHER (models/teacher.py, ~300k parameters, not deployable) on the same crop store as train_rep.py (2026-11-10).

Run from the project root:
  .venv/bin/python software/ai/training/train_teacher.py --steps 200000 --out software/ai/checkpoints/q/teacher_s0.pt
Recipe as train_rep.py (L1, Adam, warm-up + cosine, flips/rotations, same store); windows carry an 11 px halo so the teacher's 10 px
receptive field never sees padding inside the core. Selection on the 42 clean validation images only (whole images, replicate padding
of TEACHER_HALO px, centre crop) - never on the test sets.
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
sys.path.insert(0, str(ROOT / "software" / "ai" / "training"))
from evaluation.metrics import psnr_y  # noqa: E402
from models.teacher import TEACHER_HALO, Teacher, count_params  # noqa: E402
from train_rep import SCALE, STORE, Loader, load_val  # noqa: E402


@torch.no_grad()
def predict(net, lr, dev):
    x = torch.from_numpy(np.array(lr)).permute(2, 0, 1).float().div(255).unsqueeze(0).to(dev)
    h, w = x.shape[2:]
    x = F.pad(x, (TEACHER_HALO,) * 4, mode="replicate")
    o = TEACHER_HALO * SCALE
    y = net(x)[:, :, o:o + h * SCALE, o:o + w * SCALE].clamp(0, 1).mul(255).round().byte()
    return y[0].permute(1, 2, 0).cpu().numpy()


def validate(net, val, dev):
    net.eval()
    return float(np.mean([psnr_y(hr, predict(net, lr, dev), SCALE) for lr, hr in val]))


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--ch", type=int, default=64)
    ap.add_argument("--body", type=int, default=8, help="body convolutions (radius = body + 2 must stay <= TEACHER_HALO)")
    ap.add_argument("--steps", type=int, default=200000)
    ap.add_argument("--batch", type=int, default=32)
    ap.add_argument("--patch", type=int, default=32)
    ap.add_argument("--lr", type=float, default=5e-4)
    ap.add_argument("--lr-min", type=float, default=1e-6)
    ap.add_argument("--warmup", type=int, default=2000)
    ap.add_argument("--val-every", type=int, default=10000)
    ap.add_argument("--seed", type=int, default=0)
    ap.add_argument("--store", default=str(STORE))
    ap.add_argument("--out", required=True)
    a = ap.parse_args()
    assert a.body + 2 <= TEACHER_HALO, "receptive field larger than the window halo"

    dev = torch.device("cuda" if torch.cuda.is_available() else "cpu")
    torch.manual_seed(a.seed)
    lr = np.load(Path(a.store) / "lr.npy", mmap_mode="r")
    hr = np.load(Path(a.store) / "hr.npy", mmap_mode="r")
    val = load_val()
    net = Teacher(SCALE, a.ch, a.body).to(dev)
    print(f"store {len(lr)} crops; val {len(val)}; teacher parameters {count_params(net)}; device {dev}", flush=True)
    opt = torch.optim.Adam(net.parameters(), lr=a.lr)

    def lr_at(s):
        if s < a.warmup:
            return a.lr * (s + 1) / a.warmup
        t = (s - a.warmup) / max(1, a.steps - a.warmup)
        return a.lr_min + 0.5 * (a.lr - a.lr_min) * (1 + np.cos(np.pi * t))

    loader = Loader(lr, hr, a.batch, a.patch, a.seed, halo=TEACHER_HALO)
    loader.start()
    out = Path(a.out)
    out.parent.mkdir(parents=True, exist_ok=True)
    best, log, tot, t0 = -1.0, [], 0.0, time.time()
    for step in range(1, a.steps + 1):
        for g in opt.param_groups:
            g["lr"] = lr_at(step - 1)
        net.train()
        x, y = loader.get(dev)
        loss = F.l1_loss(net.core(x, TEACHER_HALO, a.patch), y)
        opt.zero_grad(set_to_none=True)
        loss.backward()
        opt.step()
        tot += loss.item() if step % 50 == 0 else 0.0
        if step % a.val_every == 0 or step == a.steps:
            v = validate(net, val, dev)
            log.append({"step": step, "train_l1": tot / (a.val_every / 50), "val_psnr_y": v})
            tot = 0.0
            if v > best:
                best = v
                torch.save({"state": net.state_dict(), "ch": a.ch, "body": a.body, "scale": SCALE, "step": step, "val_psnr_y": v, "args": vars(a)}, out)
            print(f"step {step:7d} l1 {log[-1]['train_l1']:.5f} val PSNR-Y {v:.3f} best {best:.3f} lr {lr_at(step - 1):.2e} [{time.time() - t0:.0f}s]", flush=True)
    out.with_suffix(".log.json").write_text(json.dumps(log, indent=1))


if __name__ == "__main__":
    main()
