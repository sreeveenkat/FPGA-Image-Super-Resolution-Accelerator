#!/usr/bin/env python3
"""Stimulus for the SAIF power simulation (Vivado estimate, not measured).  Created 2026-10-28.

  python software/analysis/power_vectors.py pipe <tree-root-of-pipe> <lr.raw> <out_dir>   whole frame as the DMA streams it (replicate-padded), 32-bit beats
  python software/analysis/power_vectors.py r0   <tree-root-of-main> <lr.raw> <out_dir> [ty tx]   one 64x64 tile (70x70 input with REAL neighbours) of the image
Writes <out_dir>/in32.hex, out32.hex (one 32-bit little-endian beat per line, unused bytes of the last beat 0xA5) and meta.txt  "W H n_in_beats n_out_beats".
The expected output comes from the integer model of that tree (the network of the bitstream), so the simulation can check itself.
"""
import sys
from pathlib import Path

import numpy as np

kind, root, lr, out = sys.argv[1], Path(sys.argv[2]).resolve(), Path(sys.argv[3]), Path(sys.argv[4])
out.mkdir(parents=True, exist_ok=True)
sys.path.insert(0, str(root / "software/ai/quantization"))
sys.path.insert(0, str(root / "software/host_tools"))
import integer_reference as ir  # noqa: E402
from srim import read_srim  # noqa: E402

net = ir.QNet.load(root / "software/ai/quantization/qparams.npz")
img = read_srim(lr)                                    # (H, W, 3) uint8


def beats(data: bytes, fill: int = 0xA5):
    data = bytes(data) + bytes([fill]) * (-len(data) % 4)
    return [f"{int.from_bytes(data[i:i + 4], 'little'):08x}" for i in range(0, len(data), 4)]


if kind == "pipe":
    padded = ir.pad_replicate(img)
    hr = ir.upscale(net, img)
    ib, ob = beats(padded.tobytes()), beats(hr.tobytes())
    w, h = img.shape[1], img.shape[0]
else:
    ty, tx = (int(sys.argv[5]), int(sys.argv[6])) if len(sys.argv) > 6 else (1, 1)
    r0, c0 = ty * 64, tx * 64                           # core tile origin in the LR image
    tile70 = img[r0 - 3:r0 + 64 + 3, c0 - 3:c0 + 64 + 3, :]
    assert tile70.shape == (70, 70, 3), tile70.shape
    hr = ir.run_tile(net, np.ascontiguousarray(tile70))
    ib, ob = beats(tile70.tobytes()), beats(np.ascontiguousarray(hr).tobytes())
    w = h = 64
(out / "in32.hex").write_text("\n".join(ib) + "\n")
(out / "out32.hex").write_text("\n".join(ob) + "\n")
(out / "meta.txt").write_text(f"{w} {h} {len(ib)} {len(ob)}\n")
print(f"{kind}: {w}x{h}, {len(ib)} input beats, {len(ob)} output beats, image {lr.name} {img.shape[1]}x{img.shape[0]}")
