"""Unit-test vectors for the RTL building blocks (M4), generated with the golden integer model.

Run from project root:  .venv/bin/python software/ai/quantization/gen_unit_vectors.py
Writes data/golden/unit/requant_s<SHIFT>.hex : one vector per line, 14 hex digits = {acc[31:0], M[15:0], expected[7:0]}
  (readable with $readmemh into a 56-bit word).  Covers random values, exact rounding ties, saturation both ways, extremes.
Shifts: the four real layer shifts plus tiny ones (ties are easy to hit there).
Also writes randomized single-layer tests (randL1..randL4: own weights/bias/mult files, input and expected output, 12x10 / 10x8 / ...
non-square tiles) with DIFFERENT M per output channel, extreme weights and large biases: the real network has identical M in every
channel of a layer, so these are the only tests that would catch a per-channel indexing bug in the RTL.  Shift is fixed at 20.
"""
import sys
from pathlib import Path

import numpy as np

ROOT = Path(__file__).resolve().parents[3]
sys.path.insert(0, str(ROOT / "software" / "ai"))
from quantization.export_rtl import wrom_text  # noqa: E402
from quantization.integer_reference import LAYER_SPEC, QNet, conv_requant, requant  # noqa: E402

OUT = ROOT / "data" / "golden" / "unit"
N_RANDOM = 3000


def vectors(shift, rng):
    acc, m = [], []
    lim = 2 ** 31 - 1
    # random accumulators at several magnitudes, random M
    for mag in (2 ** 8, 2 ** 14, 2 ** 20, 2 ** 24, lim):
        acc += rng.integers(-mag, mag, N_RANDOM // 5, endpoint=True).tolist()
        m += rng.integers(0, 65535, N_RANDOM // 5, endpoint=True).tolist()
    # extremes
    for a in (0, 1, -1, lim, -lim - 1, 255, 256, -255):
        for mm in (0, 1, 65535, 32768):
            acc.append(a)
            m.append(mm)
    # exact ties: choose y, M and an acc with acc*M == y*2^s - 2^(s-1)  (value exactly halfway) when divisible
    for _ in range(400):
        mm = int(rng.integers(1, 65535, endpoint=True))
        y = int(rng.integers(0, 300))
        target = y * 2 ** shift - 2 ** (shift - 1) if y > 0 else 2 ** (shift - 1)
        a = target // mm
        for cand in (a - 1, a, a + 1):  # exact tie when cand*M == target, neighbours straddle it
            if abs(cand) <= lim:
                acc.append(cand)
                m.append(mm)
    # dense sweeps through the in-range region (outputs 0..255) for several multipliers: every rounding tie of that region is hit
    for mm in (1, 2, 3, 5, 7, 100, 255, 1000, 40008, 62656):
        top = (260 * 2 ** shift) // mm
        pts = np.unique(np.concatenate([np.linspace(-2, top, 500).astype(np.int64), np.arange(0, min(top, 400))]))
        acc += pts[np.abs(pts) <= lim].tolist()
        m += [mm] * int((np.abs(pts) <= lim).sum())
    # the saturation boundary: values just below / at / above 255 and 0.5
    for mm in (1, 3, 65535):
        base = (255 * 2 ** shift) // mm
        for d in range(-3, 4):
            if abs(base + d) <= lim:  # only accumulators the 32-bit hardware can hold
                acc.append(base + d)
                m.append(mm)
    return np.array(acc, dtype=np.int64), np.array(m, dtype=np.int64)


RAND_SHIFT = 20
RAND_W, RAND_H = 6, 4  # output core size of the random tiles (non-square on purpose)


def hexw(arr, digits):
    mask = (1 << (4 * digits)) - 1
    return "\n".join(f"{int(v) & mask:0{digits}x}" for v in np.asarray(arr).flatten()) + "\n"


def random_layers():
    for idx, (name, cin, cout, k, dw) in enumerate(LAYER_SPEC, 1):
        rng = np.random.default_rng(5000 + idx)
        # input size so that the chain 12x10 -> L1 -> ... uses plain geometry: in = core + 2*(sum of later (k-1))
        pad = {1: 6, 2: 4, 3: 2, 4: 2}[idx]
        h, w = RAND_H + pad, RAND_W + pad
        x = rng.integers(0, 256, (cin, h, w)).astype(np.uint8)
        x[:, ::5, ::3] = 255  # saturated pixels
        x[:, 1::7, :] = 0
        wt = rng.integers(-128, 128, (cout, 1 if dw else cin, k, k)).astype(np.int8)
        wt[0].flat[::2] = 127  # extremes
        wt[-1].flat[::3] = -128
        b = rng.integers(-200000, 200000, cout).astype(np.int32)
        b[0], b[-1] = 2 ** 31 - 1 - 255 * 128 * 9 * cin, -(2 ** 31 - 1) // 2  # near the int32 limit, but sums stay in range
        acc_scale = np.array([np.std(wt[c].astype(np.int64)) * 255 * np.sqrt(wt[c].size) * 0.5 + 1 for c in range(cout)])
        m = np.clip(np.round(2.0 ** RAND_SHIFT * 100 / acc_scale), 1, 65535).astype(np.int64)
        m = np.where(np.arange(cout) % 5 == 4, rng.integers(1, 65535, cout), m)  # some channels with arbitrary M
        assert len(set(m.tolist())) > 1, "M must differ between channels"
        y = conv_requant(x, wt, b, m, RAND_SHIFT, dw)
        nm = f"randL{idx}"
        (OUT / f"{nm}_weights.mem").write_text(hexw(wt, 2))
        (OUT / f"{nm}_wrom.mem").write_text(wrom_text(wt, dw))
        (OUT / f"{nm}_bias.mem").write_text(hexw(b, 8))
        (OUT / f"{nm}_mult.mem").write_text(hexw(m, 4))
        (OUT / f"{nm}_in.hex").write_text(hexw(x.transpose(1, 2, 0), 2))      # [y][x][c]
        (OUT / f"{nm}_out.hex").write_text(hexw(y.transpose(1, 2, 0), 2))
        print(f"{nm}: in {x.shape} -> out {y.shape}, distinct M {len(set(m.tolist()))}, outputs 0:{(y == 0).mean():.2f} 255:{(y == 255).mean():.2f}")


def main():
    OUT.mkdir(parents=True, exist_ok=True)
    net = QNet.load(ROOT / "software/ai/quantization/qparams.npz")
    shifts = sorted({L["shift"] for L in net.layers} | {1, 2, 3, 8})
    for s in shifts:
        rng = np.random.default_rng(1000 + s)
        acc, m = vectors(s, rng)
        # requant() is per-channel (axis 0 = channel): evaluate each vector as its own channel of a (N,1,1) array
        exp = requant(acc.reshape(-1, 1, 1), m, s).reshape(-1)
        assert exp.min() >= 0 and exp.max() <= 255
        assert acc.min() >= -2 ** 31 and acc.max() <= 2 ** 31 - 1 and m.min() >= 0 and m.max() <= 65535  # representable in hardware
        lines = [f"{int(a) & 0xFFFFFFFF:08x}{int(mm):04x}{int(e):02x}" for a, mm, e in zip(acc, m, exp)]
        (OUT / f"requant_s{s}.hex").write_text("\n".join(lines) + "\n")
        print(f"requant_s{s}.hex: {len(lines)} vectors, outputs 0:{int((exp == 0).sum())} 255:{int((exp == 255).sum())} other:{int(((exp > 0) & (exp < 255)).sum())}")
    random_layers()


if __name__ == "__main__":
    main()
