"""Quantization-aware fine-tuning (QAT) of the merged FP32 SRNet, simulating EXACTLY the integer arithmetic of the RTL.

Run from the project root:
  .venv/bin/python software/ai/quantization/qat.py --ckpt software/ai/checkpoints/q/rep.pt --out software/ai/checkpoints/q/rep_qat.pt

Forward pass (all values are integers stored in float32; TF32 is switched off so the sums are exact below 2**24):
    x0 = pixel (0..255);  per layer:  wq = clamp(round(w / sw), -127, 127),  sw = max|w| / 127     (per-layer scale, like quantize.py)
    bq = round(b / (s_in * sw));      acc = conv(x, wq) + bq
    y  = clamp(floor(acc * Mq / 2**SHIFT + 0.5), 0, 255),  Mq = round(r * 2**SHIFT) with r = s_in*sw/s_out and the largest SHIFT with Mq < 2**16
Activation scales s_out = act_max / 255 of L1..L3 are calibrated once (99.99 percentile of the post-ReLU FP32 activations, like PTQ) and kept fixed;
the last layer has s_out = 1/255 (it IS the pixel).  round() / floor() use the straight-through estimator.
Output: a merged checkpoint (plain SRNet state dict, quantize.load_fp32 reads it) plus `act_max`, to be exported with
  quantization/quantize.py --ckpt <out> --act-max a1,a2,a3
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
from models.srnet import HALO, SRNet  # noqa: E402
from models.srnet_rep import SRNetRep  # noqa: E402
from quantization.quantize import calibration_crops, collect_activations, load_fp32  # noqa: E402
from train_rep import STORE, Loader, load_val  # noqa: E402

SCALE = 2


def ste_round(x):
    return x + (torch.round(x) - x).detach()


def ste_floor(x):
    return x + (torch.floor(x) - x).detach()


def multipliers(real):
    """Per-channel Mq/2**shift for a vector of real multipliers: the SAME rule as quantize.choose_multiplier (one shift per layer, M < 2**16)."""
    shift = 1
    while shift < 40 and np.round(real.max() * 2.0 ** (shift + 1)) < (1 << 16):
        shift += 1
    return np.round(real * 2.0 ** shift) / 2.0 ** shift


class QATNet(torch.nn.Module):
    """`net` is a plain SRNet or an SRNetRep; both provide layer_wb() = [(weight, bias, groups)] of the four deployed layers
    (for SRNetRep the weights are the differentiable MERGE of the branches, so QAT trains the branch parameters)."""

    def __init__(self, net, act_max, per_channel=False):
        super().__init__()
        self.net, self.per_channel = net, per_channel
        self.act_max = [float(a) for a in act_max]
        self.s_out = [a / 255.0 for a in self.act_max] + [1.0 / 255.0]
        self.s_in = [1.0 / 255.0] + self.s_out[:3]

    def forward(self, x01):
        """x01: (N,3,H+6,W+6) in [0,1] (= pixel/255, exactly representable as an integer pixel).  Returns (N,3,2H,2W) in [0,1]."""
        x = torch.round(x01 * 255.0)
        centre = x[:, :, HALO:-HALO, HALO:-HALO]
        for i, ((w, b, groups), s_in, s_out) in enumerate(zip(self.net.layer_wb(), self.s_in, self.s_out)):
            signed_last = self.net.anchor and i == 3
            if self.per_channel:
                sw = (w.detach().abs().flatten(1).max(1).values / 127.0).clamp_min(1e-12)  # one scale per output channel
            else:
                sw = (w.detach().abs().max() / 127.0).clamp_min(1e-12).expand(w.shape[0])
            swv = sw.view(-1, 1, 1, 1)
            wq = torch.clamp(ste_round(w / swv), -127, 127)
            bq = ste_round(b / (s_in * sw))
            acc = F.conv2d(x, wq, bq, groups=groups)
            r = torch.from_numpy(multipliers((s_in * sw / s_out).double().cpu().numpy())).to(acc.device, torch.float64).view(1, -1, 1, 1)
            y = ste_floor((acc.double() * r + 0.5).float())
            x = torch.clamp(y, -255 if signed_last else 0, 255)
        if self.net.anchor:
            x = torch.clamp(x + centre.repeat_interleave(4, dim=1), 0, 255)
        return self.net.shuffle(x) / 255.0


@torch.no_grad()
def calibrate(net, n=100, percentile=99.99):
    acts = collect_activations(net.cpu().eval(), calibration_crops(n))
    return [float(np.percentile(a, percentile)) for a in acts]


@torch.no_grad()
def predict(qnet, lr, dev):
    x = torch.from_numpy(np.array(lr)).permute(2, 0, 1).float().div(255).unsqueeze(0).to(dev)
    x = F.pad(x, (HALO,) * 4, mode="replicate")
    y = qnet(x).clamp(0, 1).mul(255).round().byte()
    return y[0].permute(1, 2, 0).cpu().numpy()


def validate(qnet, val, dev):
    qnet.eval()
    return float(np.mean([psnr_y(hr, predict(qnet, lr, dev), SCALE) for lr, hr in val]))


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--ckpt", default="", help="merged FP32 checkpoint (plain SRNet state dict): QAT then trains the plain weights")
    ap.add_argument("--rep-ckpt", default="", help="*_rep.pt checkpoint of train_rep.py: QAT trains the BRANCH parameters through the merged weights")
    ap.add_argument("--out", required=True)
    ap.add_argument("--per-channel", action="store_true", help="one weight scale per output channel (M is per channel in the RTL anyway)")
    ap.add_argument("--steps", type=int, default=30000)
    ap.add_argument("--batch", type=int, default=64)
    ap.add_argument("--patch", type=int, default=32)
    ap.add_argument("--lr", type=float, default=2e-5)
    ap.add_argument("--lr-min", type=float, default=1e-7)
    ap.add_argument("--val-every", type=int, default=2500)
    ap.add_argument("--percentile", type=float, default=99.99)
    ap.add_argument("--seed", type=int, default=0)
    ap.add_argument("--store", default=str(STORE))
    args = ap.parse_args()
    assert bool(args.ckpt) != bool(args.rep_ckpt), "give exactly one of --ckpt / --rep-ckpt"

    torch.backends.cudnn.allow_tf32 = False  # exact integer sums
    torch.backends.cuda.matmul.allow_tf32 = False
    dev = torch.device("cuda" if torch.cuda.is_available() else "cpu")
    torch.manual_seed(args.seed)
    if args.rep_ckpt:
        ck = torch.load(args.rep_ckpt, map_location="cpu")
        a = ck["args"]
        net = SRNetRep(SCALE, 16, rep=tuple(a["rep"].split(",")), expand=a["expand"], edge=not a["no_edge"], anchor=a["anchor"])
        net.load_state_dict(ck["state"])
    else:
        net = load_fp32(args.ckpt)
    plain = net.to_srnet() if args.rep_ckpt else net
    act_max = calibrate(plain, percentile=args.percentile)
    print("calibrated act_max:", [round(v, 4) for v in act_max], flush=True)
    net.to(dev).train()
    qnet = QATNet(net, act_max, args.per_channel).to(dev)
    val = load_val()
    start = validate(qnet, val, dev)
    print(f"PTQ-equivalent start ({'per-channel' if args.per_channel else 'per-layer'} weights): val PSNR-Y {start:.3f}", flush=True)

    lr_arr = np.load(Path(args.store) / "lr.npy", mmap_mode="r")
    hr_arr = np.load(Path(args.store) / "hr.npy", mmap_mode="r")
    loader = Loader(lr_arr, hr_arr, args.batch, args.patch, args.seed + 7)
    loader.start()
    opt = torch.optim.Adam(net.parameters(), lr=args.lr)
    best, log, tot, t0 = -1.0, [], 0.0, time.time()
    out = Path(args.out)
    out.parent.mkdir(parents=True, exist_ok=True)
    meta = {"ch": 16, "scale": SCALE, "anchor": net.anchor, "act_max": act_max, "per_channel": args.per_channel, "args": vars(args),
            "start_val_psnr_y_int8sim": start}
    for step in range(1, args.steps + 1):
        for g in opt.param_groups:
            g["lr"] = args.lr_min + 0.5 * (args.lr - args.lr_min) * (1 + np.cos(np.pi * (step - 1) / args.steps))
        qnet.train()
        x, y = loader.get(dev)
        loss = F.l1_loss(qnet(x), y)
        opt.zero_grad(set_to_none=True)
        loss.backward()
        opt.step()
        tot += loss.item() if step % 50 == 0 else 0.0
        if step % args.val_every == 0 or step == args.steps:
            v = validate(qnet, val, dev)
            log.append({"step": step, "train_l1": tot / (args.val_every / 50), "val_psnr_y_int8sim": v})
            tot = 0.0
            if v > best:  # selection on the validation images only
                best = v
                deployed = net.to_srnet() if args.rep_ckpt else net
                torch.save({"state": {k: t.detach().cpu() for k, t in deployed.state_dict().items()}, "step": step,
                            "val_psnr_y_int8sim": v, **meta}, out)
                if args.rep_ckpt:
                    torch.save({"state": {k: t.detach().cpu() for k, t in net.state_dict().items()}, "args": ck["args"], "step": step}, out.with_name(out.stem + "_rep.pt"))
            print(f"step {step:6d} l1 {log[-1]['train_l1']:.5f} val PSNR-Y (int8 sim) {v:.3f} best {best:.3f} [{time.time() - t0:.0f}s]", flush=True)
    out.with_suffix(".log.json").write_text(json.dumps(log, indent=1))
    print("act_max for export:", ",".join(f"{v:.6f}" for v in act_max))


if __name__ == "__main__":
    main()
