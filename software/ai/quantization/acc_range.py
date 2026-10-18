"""Worst-case accumulator / datapath range check of an exported parameter set against the RTL widths.  Run from the project root:
  .venv/bin/python software/ai/quantization/acc_range.py [--qparams PATH] [--images N]

Analytic worst case (every input uint8 in [0,255], independent): per output channel
    acc_max = bias + 255 * sum(positive weights),   acc_min = bias - 255 * sum(|negative weights|)
which no real image can exceed.  Checked against the RTL (hardware/rtl/common):
  * mac_unit   : acc is signed 32 bit, product register signed 17 bit (uint8 x int8 -> 16 bit magnitude)
  * requant    : acc signed 32 x M (unsigned 16 -> signed 17) -> signed 49 bit product, + rounding constant 2^(SHIFT-1); both must stay in 49 bit signed
  * M < 2^16 (mult_Ln.mem is 4 hex digits), 1 <= SHIFT <= 40 (49-bit constant), bias fits int32
Also measured on real images (validation + a few test images): the actual accumulator extremes and how often the output saturates.
Exit code 1 if any check fails.
"""
import argparse
import sys
from pathlib import Path

import numpy as np

ROOT = Path(__file__).resolve().parents[3]
sys.path.insert(0, str(ROOT / "software" / "ai"))
from dataset.pairs import list_images, load_rgb, make_pair  # noqa: E402
from quantization.integer_reference import HALO, LAYER_SPEC, QNet, pad_replicate, requant  # noqa: E402

I32 = (-(1 << 31), (1 << 31) - 1)
P49 = (-(1 << 48), (1 << 48) - 1)


def accumulate(x, w, b, depthwise):
    k = w.shape[2]
    h, wd = x.shape[1] - k + 1, x.shape[2] - k + 1
    x = x.astype(np.int64)
    acc = np.zeros((w.shape[0], h, wd), np.int64) + b.astype(np.int64)[:, None, None]
    for ky in range(k):
        for kx in range(k):
            win = x[:, ky:ky + h, kx:kx + wd]
            tap = w[:, :, ky, kx].astype(np.int64)
            acc += win * tap[:, 0][:, None, None] if depthwise else np.einsum("oc,chw->ohw", tap, win)
    return acc


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--qparams", default=str(ROOT / "software/ai/quantization/qparams.npz"))
    ap.add_argument("--images", type=int, default=6)
    a = ap.parse_args()
    net = QNet.load(a.qparams)
    ok = True
    print(f"parameter set: {a.qparams}  (anchor network: {net.anchor})")
    # ---- observed maxima first (needed for the combined table): validation images + Set5 + Set14, full size
    paths = list_images(ROOT / "data" / "train" / "HR")[:192][-12:] + list_images(ROOT / "data" / "test" / "HR" / "Set5") + list_images(ROOT / "data" / "test" / "HR" / "Set14")
    paths = paths[: a.images] if a.images else paths
    obs = {L["name"]: [1 << 62, -(1 << 62), 0, 0] for L in net.layers}  # min, max, outputs at 255, total
    for p in paths:
        lr, _ = make_pair(load_rgb(p), 2)
        cur = pad_replicate(lr).transpose(2, 0, 1)
        for i, L in enumerate(net.layers):
            acc = accumulate(cur, L["w"], L["b"], L["depthwise"])
            e = obs[L["name"]]
            e[0], e[1] = min(e[0], int(acc.min())), max(e[1], int(acc.max()))
            cur = requant(acc, L["m"], L["shift"], -255 if (net.anchor and i == len(net.layers) - 1) else 0)
            e[2] += int((cur == 255).sum()); e[3] += cur.size
    print(f"\nPER LAYER: theoretical worst case vs observed ({len(paths)} images: validation + Set5 + Set14, full size)")
    print("  theory A = max over channels of  sum|w| x 255 + |bias|      (symmetric bound, every input 255 and every sign adversarial)")
    print("  theory B = sign-aware exact worst case  [bias - 255 sum|w-|,  bias + 255 sum w+]  (inputs 0..255, independent)")
    print(f"  {'layer':<5}{'theory A':>13}{'bits':>5}{'theory B min':>14}{'theory B max':>14}{'bits':>5}{'observed min':>14}{'observed max':>14}{'bits':>5}{'headroom vs 32':>16}")
    ok = True
    prod_rows = []
    for L in net.layers:
        w = L["w"].reshape(L["w"].shape[0], -1).astype(np.int64)
        b = L["b"].astype(np.int64)
        th_a = int((255 * np.abs(w).sum(1) + np.abs(b)).max())
        hi = b + 255 * np.where(w > 0, w, 0).sum(1)
        lo = b - 255 * np.where(w < 0, -w, 0).sum(1)
        bmax, bmin = int(hi.max()), int(lo.min())
        o_min, o_max = obs[L["name"]][0], obs[L["name"]][1]
        bits = lambda v: abs(v).bit_length() + 1  # noqa: E731  signed bits needed
        prod = int(np.max(np.maximum(np.abs(hi), np.abs(lo)) * L["m"].astype(np.int64))) + (1 << (L["shift"] - 1))
        prod_th_a = int(np.max((255 * np.abs(w).sum(1) + np.abs(b)) * L["m"].astype(np.int64))) + (1 << (L["shift"] - 1))
        c = [I32[0] <= bmin and bmax <= I32[1], th_a <= I32[1], -prod_th_a >= P49[0] and prod_th_a <= P49[1], int(L["m"].max()) < (1 << 16),
             1 <= L["shift"] <= 40, int(np.abs(b).max()) <= I32[1]]
        ok &= all(c)
        prod_rows.append((L["name"], prod, prod_th_a, int(L["m"].min()), int(L["m"].max()), L["shift"], all(c), c))
        print(f"  {L['name']:<5}{th_a:>13,}{bits(th_a):>5}{bmin:>14,}{bmax:>14,}{max(bits(bmin), bits(bmax)):>5}{o_min:>14,}{o_max:>14,}{max(bits(o_min), bits(o_max)):>5}"
              f"{32 - max(bits(bmin), bits(bmax)):>12} bits")
    print(f"\nREQUANTIZER (signed 49-bit product acc x M + 2^(SHIFT-1);  limit {P49[1]:,})")
    print(f"  {'layer':<5}{'worst |acc*M|+rnd (B)':>24}{'(A)':>18}{'bits':>5}  {'M range':<14}{'SHIFT':>6}   checks")
    for n, pr, pra, mmin, mmax, sh, good, c in prod_rows:
        print(f"  {n:<5}{pr:>24,}{pra:>18,}{pra.bit_length() + 1:>5}  {mmin}..{mmax:<8}{sh:>6}   {'OK' if good else 'FAIL ' + str(c)}")
    print("  checks: bound fits int32 (A and B), A*M fits 49 bit, M < 2^16 (4 hex digits in mult_Ln.mem), 1 <= SHIFT <= 40, |bias| fits int32")
    for n, (mn, mx, sat, tot) in obs.items():
        print(f"  observed {n}: output == 255 in {100 * sat / tot:.3f} % of values")
    print("\nRESULT:", "ALL CHECKS PASS" if ok else "FAILED")
    sys.exit(0 if ok else 1)


if __name__ == "__main__":
    main()
