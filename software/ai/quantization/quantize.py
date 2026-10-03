"""Post-training INT8 quantization of the frozen FP32 SRNet (M3).

Run from project root:
  .venv/bin/python software/ai/quantization/quantize.py [--percentile 99.99] [--per-channel] [--calib 100] [--out PATH]

Scheme (see integer_reference.py for the arithmetic):
  * input  : uint8 pixel, scale 1/255, zero point 0 (exact)
  * weights: int8 symmetric in [-127, 127], zero point 0; one scale per layer, or per output channel (--per-channel)
  * hidden activations (after ReLU): uint8, ONE scale per layer = calibrated_max / 255, calibrated_max = chosen percentile of the
    FP32 activations over the calibration images
  * last layer output: scale 1/255 (it IS the pixel), clamp [0, 255]
  * bias   : int32 = round(b / (s_in * s_w))
  * requant: M[co] / 2**SHIFT ~= s_in * s_w[co] / s_out,  M < 2**16, SHIFT one value per layer (largest that keeps M < 2**16)
Calibration uses TRAINING images only (the first N of the 180 training images); test sets are never touched here.
"""
import argparse
import hashlib
import sys
from pathlib import Path

import numpy as np
import torch
import torch.nn.functional as F

ROOT = Path(__file__).resolve().parents[3]
sys.path.insert(0, str(ROOT / "software" / "ai"))
from dataset.pairs import list_images, load_rgb, make_pair  # noqa: E402
from models.srnet import HALO, SRNet  # noqa: E402
from quantization.integer_reference import LAYER_SPEC  # noqa: E402

CKPT = ROOT / "software/ai/checkpoints/srnet_fp32.pt"
OUT = ROOT / "software/ai/quantization/qparams.npz"
N_TRAIN = 180  # same split as train.py (--images 192 --val 12): first 180 train, last 12 validation
CALIB_CROP = 256  # LR crop size used for calibration (keeps it fast; 100 crops = 6.5 M pixels)


def load_fp32(path=CKPT):
    ck = torch.load(path, map_location="cpu")
    m = SRNet(ck["scale"], ck["ch"])
    m.load_state_dict(ck["state"])
    return m.eval()


def calibration_crops(n, seed=0):
    """n LR crops (CALIB_CROP x CALIB_CROP, uint8 RGB) from the first n training images, one random crop each."""
    rng = np.random.default_rng(seed)
    paths = list_images(ROOT / "data" / "train" / "HR")[:N_TRAIN][:n]
    crops = []
    for p in paths:
        lr, _ = make_pair(load_rgb(p), 2)
        y = int(rng.integers(0, lr.shape[0] - CALIB_CROP + 1))
        x = int(rng.integers(0, lr.shape[1] - CALIB_CROP + 1))
        crops.append(lr[y:y + CALIB_CROP, x:x + CALIB_CROP])
    return crops


@torch.no_grad()
def collect_activations(model, crops):
    """Post-ReLU activations of L1, L2, L3 for all crops -> list of 3 flat float32 arrays."""
    acts = [[], [], []]
    for c in crops:
        x = torch.from_numpy(c.copy()).permute(2, 0, 1).float().div(255).unsqueeze(0)
        x = F.pad(x, (HALO,) * 4, mode="replicate")
        for i, layer in enumerate((model.conv1, model.dw, model.pw)):
            x = F.relu(layer(x))
            acts[i].append(x.flatten().numpy())
    return [np.concatenate(a) for a in acts]


def choose_multiplier(real, bits=16):
    """real: array of positive floats (per channel). Returns (M int64 array, SHIFT) with M.max() < 2**bits, SHIFT as large as possible."""
    real = np.asarray(real, dtype=np.float64)
    shift = 1
    while shift < 40 and np.round(real.max() * 2.0 ** (shift + 1)) < (1 << bits):
        shift += 1
    m = np.round(real * 2.0 ** shift).astype(np.int64)
    assert m.max() < (1 << bits)
    return m, shift


def quantize(model, crops, percentile=99.9, per_channel=False):
    """Returns (dict of arrays for np.savez, info dict)."""
    acts = collect_activations(model, crops)
    act_max = [float(np.percentile(a, percentile)) for a in acts]  # L1, L2, L3 output ranges (real units)
    s_out = [m / 255.0 for m in act_max] + [1.0 / 255.0]
    s_in = [1.0 / 255.0] + s_out[:3]
    float_layers = (model.conv1, model.dw, model.pw, model.conv4)
    arrays, info = {}, []
    for (name, _cin, _cout, _k, _dw), fl, si, so in zip(LAYER_SPEC, float_layers, s_in, s_out):
        w = fl.weight.detach().double().numpy()
        b = fl.bias.detach().double().numpy()
        if per_channel:
            sw = np.maximum(np.abs(w).reshape(w.shape[0], -1).max(axis=1), 1e-12) / 127.0
        else:
            sw = np.full(w.shape[0], max(np.abs(w).max(), 1e-12) / 127.0)
        wq = np.clip(np.round(w / sw[:, None, None, None]), -127, 127).astype(np.int8)
        bq = np.round(b / (si * sw))
        assert np.abs(bq).max() < 2 ** 31, f"{name}: bias does not fit int32"
        real = si * sw / so
        m, shift = choose_multiplier(real)
        rel_err = float(np.max(np.abs(m / 2.0 ** shift - real) / real))
        arrays.update({f"{name}_w": wq, f"{name}_b": bq.astype(np.int32), f"{name}_m": m.astype(np.uint16),
                       f"{name}_shift": np.int32(shift), f"{name}_s_in": np.float64(si), f"{name}_s_out": np.float64(so),
                       f"{name}_s_w": sw})
        info.append(dict(layer=name, act_max=(act_max + [1.0])[len(info)], shift=shift, m_min=int(m.min()), m_max=int(m.max()),
                         max_rel_err=rel_err))
    return arrays, info


def checkpoint_sha(path=CKPT):
    return hashlib.sha256(Path(path).read_bytes()).hexdigest()


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--percentile", type=float, default=99.99)
    ap.add_argument("--per-channel", action="store_true")
    ap.add_argument("--calib", type=int, default=100)
    ap.add_argument("--out", default=str(OUT))
    args = ap.parse_args()
    model = load_fp32()
    arrays, info = quantize(model, calibration_crops(args.calib), args.percentile, args.per_channel)
    arrays["meta_percentile"] = np.float64(args.percentile)
    arrays["meta_per_channel"] = np.bool_(args.per_channel)
    arrays["meta_ckpt_sha256_prefix"] = np.array(checkpoint_sha()[:16])
    np.savez(args.out, **arrays)
    print(f"wrote {args.out} (percentile {args.percentile}, {'per-channel' if args.per_channel else 'per-layer'} weights, "
          f"{args.calib} calibration crops)")
    for i in info:
        print(i)


if __name__ == "__main__":
    main()
