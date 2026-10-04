"""Seam test for the tile core (M5): tiled RTL output must equal the whole-image integer-model output, bit for bit.

Run from project root:
  .venv/bin/python software/ai/quantization/seam_test.py gen   --hc 8  --h 37 --w 29     # writes data/golden/seam/hc8_*  (tile inputs + expected)
  (simulate every tile with tb_sr_tile +IN=... +OUT=... +DUMP=...  -> hc8_t<ty>_<tx>_rtl.hex; see hardware/verification/run_tests.sh)
  .venv/bin/python software/ai/quantization/seam_test.py check --hc 8                   # assembles the RTL dumps and compares

gen  : takes a real LR region (h x w, deliberately NOT a multiple of the core size), runs the WHOLE image through the integer model,
       cuts the replicate-padded image into (hc+6)x(hc+6) tiles (3 px halo, border tiles included) and writes per tile
       hc<HC>_t<ty>_<tx>_in.hex (bytes [y][x][c]) and _out.hex (per-tile expected, from run_tile); plus hc<HC>_whole.hex (the whole result).
check: reads the RTL dumps, pastes the 2hc x 2hc tiles together, crops to 2h x 2w and requires equality with the whole-image result.
"""
import argparse
import sys
from pathlib import Path

import numpy as np

ROOT = Path(__file__).resolve().parents[3]
sys.path.insert(0, str(ROOT / "software" / "ai"))
from dataset.pairs import list_images, load_rgb, make_pair  # noqa: E402
from quantization.integer_reference import HALO, QNet, run_tile, upscale  # noqa: E402

OUT = ROOT / "data" / "golden" / "seam"


def hexs(arr):
    return "\n".join(f"{int(v):02x}" for v in np.asarray(arr, dtype=np.uint8).flatten()) + "\n"


def read_hex(path, n):
    vals = [int(t, 16) for t in Path(path).read_text().split()]
    assert len(vals) == n, f"{path}: {len(vals)} bytes, expected {n}"
    return np.array(vals, dtype=np.uint8)


def region(h, w):
    p = list_images(ROOT / "data" / "train" / "HR")[7]
    lr, _ = make_pair(load_rgb(p), 2)
    y0, x0 = 120, 200
    return lr[y0:y0 + h, x0:x0 + w].copy()


def tiles_of(lr, hc):
    h, w = lr.shape[:2]
    ph, pw = -h % hc, -w % hc
    padded = np.pad(lr, ((HALO, HALO + ph), (HALO, HALO + pw), (0, 0)), mode="edge")
    for ty in range((h + ph) // hc):
        for tx in range((w + pw) // hc):
            yield ty, tx, padded[ty * hc:ty * hc + hc + 2 * HALO, tx * hc:tx * hc + hc + 2 * HALO]


def gen(hc, h, w):
    OUT.mkdir(parents=True, exist_ok=True)
    net = QNet.load(ROOT / "software/ai/quantization/qparams.npz")
    lr = region(h, w)
    whole = upscale(net, lr)
    (OUT / f"hc{hc}_whole.hex").write_text(hexs(whole))
    (OUT / f"hc{hc}_shape.txt").write_text(f"{h} {w}\n")
    n = 0
    for ty, tx, tile in tiles_of(lr, hc):
        out = run_tile(net, tile)
        assert out.shape == (2 * hc, 2 * hc, 3)
        (OUT / f"hc{hc}_t{ty}_{tx}_in.hex").write_text(hexs(tile))
        (OUT / f"hc{hc}_t{ty}_{tx}_out.hex").write_text(hexs(out))
        n += 1
    print(f"seam gen: hc={hc}, LR region {h}x{w} -> {n} tiles, whole output {whole.shape}; seams cross real image content "
          f"(output std {whole.std():.1f})")


def check(hc):
    h, w = map(int, (OUT / f"hc{hc}_shape.txt").read_text().split())
    whole = read_hex(OUT / f"hc{hc}_whole.hex", 2 * h * 2 * w * 3).reshape(2 * h, 2 * w, 3)
    ph, pw = -h % hc, -w % hc
    canvas = np.zeros((2 * (h + ph), 2 * (w + pw), 3), dtype=np.uint8)
    n = 0
    for ty in range((h + ph) // hc):
        for tx in range((w + pw) // hc):
            t = read_hex(OUT / f"hc{hc}_t{ty}_{tx}_rtl.hex", (2 * hc) ** 2 * 3).reshape(2 * hc, 2 * hc, 3)
            canvas[2 * ty * hc:2 * (ty + 1) * hc, 2 * tx * hc:2 * (tx + 1) * hc] = t
            n += 1
    got = canvas[:2 * h, :2 * w]
    bad = int((got != whole).any(axis=2).sum())
    if bad:
        ys, xs = np.nonzero((got != whole).any(axis=2))
        print(f"FAIL seam hc={hc}: {bad} wrong pixels, first at (y={ys[0]}, x={xs[0]}); seams at multiples of {2 * hc}")
        sys.exit(1)
    print(f"PASS seam hc={hc}: {n} RTL tiles assembled == whole-image integer model, {2 * h}x{2 * w} pixels bit-exact")


if __name__ == "__main__":
    ap = argparse.ArgumentParser()
    ap.add_argument("mode", choices=["gen", "check"])
    ap.add_argument("--hc", type=int, required=True)
    ap.add_argument("--h", type=int, default=0)
    ap.add_argument("--w", type=int, default=0)
    a = ap.parse_args()
    gen(a.hc, a.h, a.w) if a.mode == "gen" else check(a.hc)
