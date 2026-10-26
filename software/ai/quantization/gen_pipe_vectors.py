#!/usr/bin/env python3
"""Test vectors for the whole-frame pipeline RTL (hardware/rtl/pipe/, docs/ARCHITECTURE_PIPELINE.md).

Run from the project root:   .venv/bin/python software/ai/quantization/gen_pipe_vectors.py [--full]

Writes data/golden/pipe/ (git-ignored):
  frames (network weights from qparams.npz, golden = integer_reference.upscale / forward_layers):
    <f>_meta.txt  "W H n_in_beats n_out_beats"
    <f>_in.hex    32-bit input beats: replicate-padded (W+6)x(H+6)x3 frame, little-endian; unused bytes of the last beat = 0xA5
    <f>_out.hex   32-bit output beats: the 2W x 2H x 3 frame of upscale()
    <f>_L1..L4.hex  each stage's output pixels in raster order (L4 = after the anchor add), one pixel word per line, channel 0 = rightmost byte
    <f>_anc.hex   anchor network only: the centre input pixel of every output pixel (24 bit, R = rightmost byte), raster
  random-weight stage tests (distinct M per channel, non-square frames, every output value 0..255 reached):
    rand/randL<n>_{wpipe,bias,mult}.mem, rand/randL<n>_{in,out,anc}.hex, rand/randL<n>_meta.txt  "IN_W IN_H SHIFT"
--full also writes the 960x540 frame `pfull` (data/board/div2k_img0193_lr_960x540.raw).
"""
from __future__ import annotations

import sys
from pathlib import Path

import numpy as np

sys.path.insert(0, str(Path(__file__).resolve().parent))
import export_pipe  # noqa: E402
from integer_reference import HALO, QNet, conv_requant, forward_layers, pad_replicate, upscale  # noqa: E402

OUT = Path("data/golden/pipe")
QP = Path("software/ai/quantization/qparams.npz")


def beats(data: bytes, fill: int = 0xA5) -> list[str]:
    data = bytes(data) + bytes([fill]) * (-len(data) % 4)
    return [f"{int.from_bytes(data[i:i + 4], 'little'):08x}" for i in range(0, len(data), 4)]


def pix_lines(chw: np.ndarray) -> list[str]:
    """(C,H,W) values 0..255 -> raster lines, channel 0 = rightmost byte."""
    c = chw.shape[0]
    flat = chw.reshape(c, -1).T.astype(np.uint8)
    return ["".join(f"{v:02x}" for v in row[::-1]) for row in flat]


def write(path: Path, lines: list[str]) -> None:
    path.write_text("\n".join(lines) + "\n")


def frame(net: QNet, name: str, lr_hwc: np.ndarray) -> None:
    h, w = lr_hwc.shape[:2]
    padded = pad_replicate(lr_hwc)
    x = np.ascontiguousarray(padded.transpose(2, 0, 1))
    outs = forward_layers(net, x)
    hr = upscale(net, lr_hwc)
    assert np.array_equal(hr.transpose(2, 0, 1), outs[-1])
    l4 = outs[3]
    if net.anchor:
        centre = x[:, HALO:-HALO, HALO:-HALO].astype(np.int32)
        l4 = np.clip(l4 + np.repeat(centre, 4, axis=0), 0, 255)
        write(OUT / f"{name}_anc.hex", pix_lines(centre))                 # anchor pixels (x+3, y+3), raster
    assert l4.min() >= 0 and l4.max() <= 255
    ib = beats(padded.tobytes())
    ob = beats(hr.tobytes())
    assert len(ob) == 3 * w * h
    write(OUT / f"{name}_in.hex", ib)
    write(OUT / f"{name}_out.hex", ob)
    for i, o in enumerate((outs[0], outs[1], outs[2], l4), start=1):
        write(OUT / f"{name}_L{i}.hex", pix_lines(o))
    (OUT / f"{name}_meta.txt").write_text(f"{w} {h} {len(ib)} {len(ob)}\n")
    print(f"{name}: {w}x{h}, {len(ib)} beats in, {len(ob)} beats out")


# ---------------------------------------------------------------- random-weight stage tests
def raw_acc(x: np.ndarray, w: np.ndarray, depthwise: bool) -> np.ndarray:
    """VALID convolution sums without bias or requantization (int64)."""
    k = w.shape[2]
    h, wd = x.shape[1] - k + 1, x.shape[2] - k + 1
    acc = np.zeros((w.shape[0], h, wd), dtype=np.int64)
    for ky in range(k):
        for kx in range(k):
            win = x[:, ky:ky + h, kx:kx + wd]
            tap = w[:, :, ky, kx]
            acc += win * tap[:, 0][:, None, None] if depthwise else np.einsum("oc,chw->ohw", tap, win)
    return acc


RAND = [  # (layer, C_in, C_out, K, mode, IN_W, IN_H, anchor)
    (1, 3, 16, 3, 0, 11, 7, False),
    (2, 16, 16, 3, 1, 9, 12, False),
    (3, 16, 16, 1, 0, 7, 5, False),
    (4, 16, 12, 3, 2, 10, 6, True),
]


def rand_stage(rng: np.random.Generator, layer, cin, cout, k, mode, iw, ih, anchor) -> None:
    d = OUT / "rand"
    d.mkdir(parents=True, exist_ok=True)
    ci_w = 1 if mode == 1 else cin
    w = rng.integers(-127, 128, size=(cout, ci_w, k, k), dtype=np.int64)
    w.flat[0], w.flat[1] = 127, -127                                    # both weight extremes appear
    b = rng.integers(-4000, 4000, size=cout, dtype=np.int64)
    x = rng.integers(0, 256, size=(cin, ih, iw), dtype=np.int64)
    x[:, 0, 0], x[:, 0, 1] = 255, 0
    acc = raw_acc(x, w, mode == 1)                                        # accumulators without bias
    shift = 20
    lo = -255 if anchor else 0
    m = np.zeros(cout, dtype=np.int64)
    for co in range(cout):                                                # distinct M per channel; each channel spans about -40..300 after requant
        span = max(1, int(acc[co].max() - acc[co].min()))
        m[co] = int(np.clip((340 << shift) // span, 1, 65535)) - co
        b[co] = int(-acc[co].min()) - (40 << shift) // int(m[co]) + int(b[co]) % 7
    y = conv_requant(x, w, b, m, shift, depthwise=(mode == 1), lo=lo)
    oh, ow = y.shape[1:]
    anc = rng.integers(0, 256, size=(3, oh, ow), dtype=np.int64) if anchor else None
    if anchor:
        y = np.clip(y + np.repeat(anc, 4, axis=0), 0, 255)
    assert y.min() == 0 and y.max() == 255, (layer, y.min(), y.max())
    assert len(set(m.tolist())) == cout
    lanes = export_pipe.slot_lanes(w.reshape(cout, ci_w, k * k), mode)
    n = f"randL{layer}"
    write(d / f"{n}_wpipe.mem", export_pipe.lines_for(lanes))
    write(d / f"{n}_bias.mem", [f"{int(v) & 0xFFFFFFFF:08x}" for v in b])
    write(d / f"{n}_mult.mem", [f"{int(v):04x}" for v in m])
    write(d / f"{n}_in.hex", pix_lines(x))
    write(d / f"{n}_out.hex", pix_lines(y))
    write(d / f"{n}_anc.hex", pix_lines(anc) if anchor else ["000000"])
    (d / f"{n}_meta.txt").write_text(f"{iw} {ih} {shift}\n")
    print(f"{n}: {iw}x{ih} -> {ow}x{oh} x {cout} ch, SHIFT {shift}, M {m.min()}..{m.max()} distinct")


def main() -> int:
    OUT.mkdir(parents=True, exist_ok=True)
    net = QNet.load(QP)
    rng = np.random.default_rng(2026)
    frame(net, "p1x1", rng.integers(0, 256, (1, 1, 3), dtype=np.uint8))
    frame(net, "p2x3", rng.integers(0, 256, (3, 2, 3), dtype=np.uint8))
    frame(net, "p5x4", rng.integers(0, 256, (4, 5, 3), dtype=np.uint8))
    frame(net, "p13x7", rng.integers(0, 256, (7, 13, 3), dtype=np.uint8))
    ramp = np.zeros((9, 16, 3), dtype=np.uint8)
    ramp[..., 0] = np.arange(16)[None, :] * 17
    ramp[..., 1] = np.arange(9)[:, None] * 31
    ramp[..., 2] = 255 - ramp[..., 0]
    frame(net, "pramp", ramp)
    sat = np.zeros((5, 6, 3), dtype=np.uint8)
    sat[::2] = 255
    frame(net, "psat", sat)
    hr_imgs = sorted(Path("data/train/HR").glob("*.png"))
    if hr_imgs:
        import cv2
        img = cv2.cvtColor(cv2.imread(str(hr_imgs[0])), cv2.COLOR_BGR2RGB)
        frame(net, "preal", np.ascontiguousarray(img[200:248, 300:364]))     # 64x48
        frame(net, "preal2", np.ascontiguousarray(img[400:429, 100:137]))    # 37x29 (odd)
    else:
        print("SKIP preal/preal2: data/train/HR is empty")
    if "--full" in sys.argv:
        raw = Path("data/board/div2k_img0193_lr_960x540.raw")
        frame(net, "pfull", np.frombuffer(raw.read_bytes(), dtype=np.uint8).reshape(540, 960, 3))
    for cfg in RAND:
        rand_stage(rng, *cfg)
    return 0


if __name__ == "__main__":
    sys.exit(main())
