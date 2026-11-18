"""Butterfly (Set5) x2 comparison figure for the paper, built from BOARD outputs only.

Inputs (all byte-exact against their integer models, checked here again):
  HR:      data/test/HR/Set5/butterfly.png
  LR:      the LR raw the board was fed (data/board/testsets/Set5/butterfly_lr.raw)
  R0:      board output of the tiled design R0, 2026-10-12 (data/board/testsets/Set5/butterfly_board.raw, main tree)
  v4:      board output of pipeline v4, 2026-11-18 (<pipe4 tree>/data/board/testsets/Set5/butterfly_board.raw)
Bicubic = Pillow bicubic upscale of the same LR (the project's baseline). PSNR-Y / SSIM-Y: BT.601 luma, 2-px shave (project metrics).
Usage: .venv/bin/python software/analysis/make_butterfly_fig.py [pipe4_tree]
Writes results/figures/butterfly_x2.{png,pdf} and butterfly_x2.csv.
"""
import sys
from pathlib import Path
import numpy as np
import matplotlib
matplotlib.use("Agg")
import matplotlib.pyplot as plt

ROOT = Path(__file__).resolve().parents[2]
sys.path[:0] = [str(ROOT / "software/host_tools"), str(ROOT / "software/ai/dataset"), str(ROOT / "software/ai/evaluation")]
from srim import read_srim                      # noqa: E402
from pairs import load_rgb, make_pair, upscale_pil  # noqa: E402
from metrics import psnr_y, ssim_y              # noqa: E402

pipe4 = Path(sys.argv[1]) if len(sys.argv) > 1 else ROOT.parent / "sandbox_pipe4"
d0 = ROOT / "data/board/testsets/Set5"
d4 = pipe4 / "data/board/testsets/Set5"
for d in (d0, d4):
    assert (d / "butterfly_board.raw").read_bytes() == (d / "butterfly_exp.raw").read_bytes(), f"{d}: board != expected"
lr_ref, hr = make_pair(load_rgb(ROOT / "data/test/HR/Set5/butterfly.png"))
lr = read_srim(d4 / "butterfly_lr.raw")
assert np.array_equal(lr, read_srim(d0 / "butterfly_lr.raw")) and np.array_equal(lr, lr_ref), "LR inputs differ"
imgs = {"HR crop": hr, "Bicubic": upscale_pil(lr), "R0 (board)": read_srim(d0 / "butterfly_board.raw"),
        "Ours, v4 (board)": read_srim(d4 / "butterfly_board.raw")}
rows = []
for k, v in imgs.items():
    assert v.shape == hr.shape, (k, v.shape)
    rows.append((k, psnr_y(hr, v, 2), ssim_y(hr, v, 2)))
y0, x0, s = 96, 88, 80                          # crop (wing pattern), 80x80 px of the 256x256 image
from matplotlib.patches import Rectangle
fig, ax = plt.subplots(1, 5, figsize=(7.16, 1.95))
ax[0].imshow(hr, interpolation="nearest")
ax[0].add_patch(Rectangle((x0 - 0.5, y0 - 0.5), s, s, fill=False, ec="red", lw=1.2))
ax[0].set_xlabel("HR, 256$\\times$256", fontsize=7.5)
for a, (k, p, q) in zip(ax[1:], rows):
    a.imshow(imgs[k][y0:y0 + s, x0:x0 + s], interpolation="nearest")
    a.set_xlabel(k if k.startswith("HR") else f"{k}\n{p:.2f} dB / {q:.4f}", fontsize=7.5)
for a in ax:
    a.set_xticks([]); a.set_yticks([])
fig.tight_layout(pad=0.3)
out = ROOT / "results/figures"; out.mkdir(parents=True, exist_ok=True)
fig.savefig(out / "butterfly_x2.png", dpi=300, bbox_inches="tight", pad_inches=0.02); fig.savefig(out / "butterfly_x2.pdf", bbox_inches="tight", pad_inches=0.02)
with open(out / "butterfly_x2.csv", "w") as f:
    f.write("image,psnr_y_db,ssim_y\n")
    for k, p, q in rows[1:]:
        f.write(f"{k},{p:.4f},{q:.5f}\n")
for k, p, q in rows[1:]:
    print(f"{k:20s} PSNR-Y {p:.2f} dB  SSIM-Y {q:.4f}")
