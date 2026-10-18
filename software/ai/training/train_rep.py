"""Image-quality retraining of the SAME SRNet architecture (GPU), reading the crop store made by dataset/prepare_extra.py.

Run from the project root, e.g.
  .venv/bin/python software/ai/training/train_rep.py --model rep --steps 200000 --out software/ai/checkpoints/q/rep.pt
  .venv/bin/python software/ai/training/train_rep.py --model plain --steps 200000 --out software/ai/checkpoints/q/plain.pt

--model plain : the original SRNet (what the hardware has).
--model rep   : SRNetRep (ECBSR/RepVGG-style training blocks); the saved checkpoint is the MERGED plain SRNet
                (state dict readable by quantization/quantize.load_fp32); the multi-branch weights are saved next to it as *_rep.pt.
Recipe: L1 loss, Adam, cosine schedule, random flips + 90-degree rotations, 32x32 LR core + 3 px real halo (valid convs, like hardware).
Model selection uses ONLY the 42 clean validation images (never the test sets, never trained on).
"""
import argparse
import json
import queue
import sys
import threading
import time
from pathlib import Path

import numpy as np
import torch
import torch.nn.functional as F

ROOT = Path(__file__).resolve().parents[3]
sys.path.insert(0, str(ROOT / "software" / "ai"))
from dataset.pairs import list_images, load_rgb, make_pair  # noqa: E402
from evaluation.metrics import psnr_y  # noqa: E402
from models.srnet import HALO, SRNet, count_params  # noqa: E402
from models.srnet_rep import SRNetRep  # noqa: E402

SCALE = 2
STORE = ROOT / "data" / "train_extra" / "store"


def load_val():
    """Validation split for ALL selection: 42 clean DIV2K valid images (dataset/valsplit.py), seen by no model of the project."""
    from dataset.valsplit import load_val_pairs
    return load_val_pairs("val42")


@torch.no_grad()
def predict_gpu(net, lr, dev):
    x = torch.from_numpy(np.array(lr)).permute(2, 0, 1).float().div(255).unsqueeze(0).to(dev)
    x = F.pad(x, (HALO,) * 4, mode="replicate")
    y = net(x).clamp(0, 1).mul(255).round().byte()
    return y[0].permute(1, 2, 0).cpu().numpy()


def validate(net, val, dev):
    net.eval()
    return float(np.mean([psnr_y(hr, predict_gpu(net, lr, dev), SCALE) for lr, hr in val]))


class Loader(threading.Thread):
    """Background thread that cuts random (LR window, HR core) pairs out of the memory-mapped crop store."""

    def __init__(self, lr, hr, batch, patch, seed, depth=6):
        super().__init__(daemon=True)
        self.lr, self.hr, self.batch, self.patch = lr, hr, batch, patch
        self.rng = np.random.default_rng(seed)
        self.q = queue.Queue(depth)

    def run(self):
        n, (ch, cw) = len(self.lr), self.lr.shape[1:3]
        win, p = self.patch + 2 * HALO, self.patch
        while True:
            xs = np.empty((self.batch, win, win, 3), np.uint8)
            ys = np.empty((self.batch, p * SCALE, p * SCALE, 3), np.uint8)
            for i in range(self.batch):
                k = int(self.rng.integers(n))
                y0, x0 = int(self.rng.integers(0, ch - win + 1)), int(self.rng.integers(0, cw - win + 1))
                a = self.lr[k, y0:y0 + win, x0:x0 + win]
                b = self.hr[k, (y0 + HALO) * SCALE:(y0 + HALO + p) * SCALE, (x0 + HALO) * SCALE:(x0 + HALO + p) * SCALE]
                r = int(self.rng.integers(4))  # 8 dihedral variants: rot90 x {no flip, flip}
                a, b = np.rot90(a, r), np.rot90(b, r)
                if self.rng.integers(2):
                    a, b = a[:, ::-1], b[:, ::-1]
                xs[i], ys[i] = a, b
            self.q.put((torch.from_numpy(xs), torch.from_numpy(ys)))

    def get(self, dev):
        x, y = self.q.get()
        return (x.to(dev, non_blocking=True).permute(0, 3, 1, 2).float().div_(255),
                y.to(dev, non_blocking=True).permute(0, 3, 1, 2).float().div_(255))


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--model", choices=["plain", "rep"], default="rep")
    ap.add_argument("--rep", default="l1,l2,l3,l4", help="which layers use training blocks (model rep)")
    ap.add_argument("--no-edge", action="store_true", help="ECB without the Sobel/Laplacian branches")
    ap.add_argument("--expand", type=float, default=2.0)
    ap.add_argument("--anchor", action="store_true", help="ABPN-style nearest-neighbour anchor added before PixelShuffle")
    ap.add_argument("--steps", type=int, default=200000)
    ap.add_argument("--batch", type=int, default=64)
    ap.add_argument("--patch", type=int, default=32)
    ap.add_argument("--lr", type=float, default=1e-3)
    ap.add_argument("--lr-min", type=float, default=1e-6)
    ap.add_argument("--warmup", type=int, default=1000)
    ap.add_argument("--val-every", type=int, default=5000)
    ap.add_argument("--seed", type=int, default=0)
    ap.add_argument("--store", default=str(STORE))
    ap.add_argument("--max-crops", type=int, default=0, help="use only the first N crops (0 = all)")
    ap.add_argument("--init", default="", help="start from a merged plain checkpoint (model plain only)")
    ap.add_argument("--out", required=True)
    args = ap.parse_args()

    dev = torch.device("cuda" if torch.cuda.is_available() else "cpu")
    torch.manual_seed(args.seed)
    store = Path(args.store)
    lr = np.load(store / "lr.npy", mmap_mode="r")
    hr = np.load(store / "hr.npy", mmap_mode="r")
    if args.max_crops:
        lr, hr = lr[:args.max_crops], hr[:args.max_crops]
    val = load_val()
    print(f"store: {len(lr)} crops LR {lr.shape[1:]} HR {hr.shape[1:]}; val {len(val)} images; device {dev}", flush=True)

    if args.model == "rep":
        net = SRNetRep(SCALE, 16, rep=tuple(args.rep.split(",")), expand=args.expand, edge=not args.no_edge, anchor=args.anchor)
    else:
        net = SRNet(SCALE, 16, args.anchor)
        if args.init:
            net.load_state_dict(torch.load(args.init, map_location="cpu")["state"])
    net.to(dev)
    print(f"training parameters: {count_params(net)}; deployed parameters: 2620", flush=True)
    opt = torch.optim.Adam(net.parameters(), lr=args.lr)

    def lr_at(s):  # linear warm-up, then cosine to lr_min
        if s < args.warmup:
            return args.lr * (s + 1) / args.warmup
        t = (s - args.warmup) / max(1, args.steps - args.warmup)
        return args.lr_min + 0.5 * (args.lr - args.lr_min) * (1 + np.cos(np.pi * t))

    def deploy(m):
        return m.to_srnet().to(dev) if args.model == "rep" else m

    loader = Loader(lr, hr, args.batch, args.patch, args.seed)
    loader.start()
    out = Path(args.out)
    out.parent.mkdir(parents=True, exist_ok=True)
    best, log, tot, t0 = -1.0, [], 0.0, time.time()
    for step in range(1, args.steps + 1):
        for g in opt.param_groups:
            g["lr"] = lr_at(step - 1)
        net.train()
        x, y = loader.get(dev)
        loss = F.l1_loss(net.forward_merged(x) if args.model == "rep" else net(x), y)
        opt.zero_grad(set_to_none=True)
        loss.backward()
        opt.step()
        tot += loss.item() if step % 50 == 0 else 0.0
        if step % args.val_every == 0 or step == args.steps:
            v = validate(deploy(net), val, dev)
            log.append({"step": step, "train_l1": tot / (args.val_every / 50), "val_psnr_y": v})
            tot = 0.0
            if v > best:
                best = v
                plain = deploy(net).cpu()
                torch.save({"state": plain.state_dict(), "ch": 16, "scale": SCALE, "anchor": args.anchor, "step": step, "val_psnr_y": v, "args": vars(args)}, out)
                if args.model == "rep":
                    torch.save({"state": net.state_dict(), "step": step, "val_psnr_y": v, "args": vars(args)}, out.with_name(out.stem + "_rep.pt"))
                plain.to(dev)
            print(f"step {step:7d} l1 {log[-1]['train_l1']:.5f} val PSNR-Y {v:.3f} best {best:.3f} lr {lr_at(step - 1):.2e} [{time.time() - t0:.0f}s]", flush=True)
    out.with_suffix(".log.json").write_text(json.dumps(log, indent=1))


if __name__ == "__main__":
    main()
