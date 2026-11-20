#!/usr/bin/env python3
"""Datapath diagram of the v4 layer pipeline (branch pipe4), textbook style.

Writes results/figures/arch_v4_datapath.png.  Structure and numbers from the pipe4 RTL:
  sr_pipe_core.v (s1..s4 pipe_stage, f1..f3 pipe_fifo W=128, u_anc anchor_fifo 4096 x 24, u_out pipe_out, PL padding),
  pipe_stage.v   (line buffer, window + snapshot, NL lanes, NG adder trees, NRQ requantizers; NS = 6, P = ceil(NCH / 6)),
  routed per-stage DSP 60 / 33 / 38 / 80 (results/utilization/m6_system_pipe4.md in branch pipe4).
Run from the project root: .venv/bin/python software/analysis/make_accel_datapath.py
"""
from pathlib import Path

import matplotlib

matplotlib.use("Agg")
import matplotlib.pyplot as plt
from matplotlib.patches import Rectangle

K = "black"
G = "#555555"
MONO = "DejaVu Sans Mono"
OUT = Path("results/figures/arch_v4_datapath.png")

fig, ax = plt.subplots(figsize=(19, 11))
fig.patch.set_facecolor("white")
ax.set_xlim(-0.3, 27.6)
ax.set_ylim(-1.5, 15.4)
ax.set_aspect("equal")
ax.axis("off")


def box(x, y, w, h, t, fs=6.9, fill="white", lw=1.25):
    ax.add_patch(Rectangle((x, y), w, h, fc=fill, ec=K, lw=lw, zorder=2))
    ax.text(x + w / 2, y + h / 2, t, ha="center", va="center", fontsize=fs, zorder=3, linespacing=1.25)


def wire(pts, arrow=True, dashed=False, lw=1.15):
    xs, ys = zip(*pts)
    ax.plot(xs, ys, color=K, lw=lw, ls=(0, (4, 2.5)) if dashed else "-", zorder=4, solid_capstyle="butt")
    if arrow:
        (x0, y0), (x1, y1) = pts[-2], pts[-1]
        dx = 0.17 if x1 > x0 else -0.17 if x1 < x0 else 0
        dy = 0.17 if y1 > y0 else -0.17 if y1 < y0 else 0
        ax.annotate("", xy=(x1, y1), xytext=(x1 - dx, y1 - dy),
                    arrowprops=dict(arrowstyle="-|>", color=K, lw=lw, mutation_scale=8, shrinkA=0, shrinkB=0), zorder=5)


def width(x, y, n, vertical=True):
    d = 0.09
    if vertical:
        ax.plot([x - d * 1.4, x + d * 1.4], [y - d, y + d], color=K, lw=1.0, zorder=5)
        ax.text(x + 0.14, y, str(n), ha="left", va="center", fontsize=6.4, family=MONO, zorder=5)
    else:
        ax.plot([x - d, x + d], [y - d * 1.4, y + d * 1.4], color=K, lw=1.0, zorder=5)
        ax.text(x, y + 0.14, str(n), ha="center", va="bottom", fontsize=6.4, family=MONO, zorder=5)


def lab(x, y, t, ha="left", va="bottom", fs=6.6, color=K, mono=True):
    ax.text(x, y, t, ha=ha, va=va, fontsize=fs, family=MONO if mono else None, color=color, zorder=6)


def dot(x, y):
    ax.plot([x], [y], "o", color=K, ms=3.0, zorder=6)


# ------------------------------------------------------------------ column frames
cols = {"IN": (0.0, 3.3), "L1": (4.3, 8.6), "L2": (9.6, 13.4), "L3": (14.4, 18.2), "L4": (19.2, 23.8), "OUT": (24.6, 27.4)}
titles = {
    "IN": ("INPUT", "sr_pipe_core"),
    "L1": ("L1  conv 3x3, 3 -> 16", "s1 : pipe_stage  (MODE 0)"),
    "L2": ("L2  depthwise 3x3", "s2 : pipe_stage  (MODE 1)"),
    "L3": ("L3  conv 1x1, 16 -> 16", "s3 : pipe_stage  (MODE 0)"),
    "L4": ("L4  conv 3x3, 16 -> 12", "s4 : pipe_stage  (MODE 0)"),
    "OUT": ("OUTPUT", "u_out : pipe_out"),
}
for k, (x0, x1) in cols.items():
    ax.add_patch(Rectangle((x0, 0.0), x1 - x0, 13.3, fc="none", ec="#9a9a9a", lw=0.9, ls=(0, (5, 3)), zorder=1))
    ax.text((x0 + x1) / 2, 14.95, titles[k][0], ha="center", va="center", fontsize=10.5, fontweight="bold")
    ax.text((x0 + x1) / 2, 14.5, titles[k][1], ha="center", va="center", fontsize=7, family=MONO, color=G)

# common rows inside a stage
Y_LB, Y_WIN, Y_MUL, Y_TREE, Y_RQ, Y_OW = 11.2, 9.55, 7.35, 5.65, 3.85, 2.3
H = 0.95


def stage(key, lb, mul, tree, rq, rom, outw, k1=False, anchor=False):
    x0, x1 = cols[key]
    xl, xr = x0 + 0.55, x1 - 0.35          # main column
    wm = xr - xl
    box(xl, Y_LB, xr - xl, H, lb, fill="#efefef" if not k1 else "white")
    box(xl, Y_WIN, xr - xl, H, "1x1 pixel register\n+ snapshot" if k1 else "3x3 window shift reg.\n+ snapshot (px_start)")
    box(xl, Y_MUL - 0.25, wm, H + 0.5, mul)
    rw = (xr - xl) * 0.6
    box(xr - rw, 8.72, rw, 0.62, rom, fs=5.9, fill="#efefef")
    box(xl, Y_TREE, xr - xl, H, tree)
    box(xl, Y_RQ, xr - xl, H, rq)
    box(xl, Y_OW, xr - xl, 0.7, outw)
    xc = xl + (xr - xl) * 0.25
    xm = (xl + xr) / 2
    wire([(xm, Y_LB), (xm, Y_WIN + H)])
    wire([(xc, Y_WIN), (xc, Y_MUL + H + 0.25)])
    wire([(xr - rw / 2, 8.72), (xr - rw / 2, Y_MUL + H + 0.25)])
    wire([(xc, Y_MUL - 0.25), (xc, Y_TREE + H)])
    wire([(xc, Y_TREE), (xc, Y_RQ + H)])
    wire([(xc, Y_RQ), (xc, Y_OW + 0.7)])
    return xl, xr, xc


x1l, x1r, x1c = stage("L1", "line buffer: 2 rows\n1024 x 24 b (BRAM)",
                      "81 multiplier lanes\n3 ch x 27 taps per slot\n27 packed DSP pairs + 27 DSP",
                      "3 trees x 27 terms (+ borrow)", "+ bias, 3 requantizers\n(acc*M + 2^(S-1)) >> S",
                      "ROM wpipe6_L1, 6 slots", "output word  16 ch x 8 b")
x2l, x2r, x2c = stage("L2", "line buffer: 2 rows\n1024 x 128 b (BRAM)",
                      "27 multiplier lanes\n3 ch x 9 taps per slot\n27 DSP (not packed)",
                      "3 trees x 9 terms", "+ bias, 3 requantizers", "ROM wpipe6_L2, 6 slots", "output word  16 ch x 8 b")
x3l, x3r, x3c = stage("L3", "no line buffer (K = 1)",
                      "48 multiplier lanes\n3 ch x 16 inputs per slot\n16 packed pairs + 16 DSP",
                      "3 trees x 16 terms (+ borrow)", "+ bias, 3 requantizers", "ROM wpipe6_L3, 6 slots",
                      "output word  16 ch x 8 b", k1=True)
x4l, x4r, x4c = stage("L4", "line buffer: 2 rows\n1024 x 128 b (BRAM)",
                      "288 lanes, 2 ch x 144 per slot\n144 packed pairs: 76 on DSP48,\n68 on 136 LUT multipliers",
                      "2 trees x 144 terms (+ borrow)", "+ bias, 2 requantizers\n+ anchor (rounding term)",
                      "ROM wpipe6_L4, 6 slots", "output word  12 ch x 8 b", anchor=True)

# ------------------------------------------------------------------ input column
xi0, xi1 = cols["IN"]
xil, xir = xi0 + 0.35, xi1 - 0.35
box(xil, Y_LB, xir - xil, H, "unpack\n32 b -> 24 b pixels")
box(xil, Y_WIN - 0.6, xir - xil, H + 1.0, "PL padding (PAD_EN)\n2-row raw buffer,\nreplicate 3 px border\n(W+6) x (H+6) out")
xim = (xil + xir) / 2
lab(xil - 0.05, 13.62, "s_axis", fs=7.4, ha="left")
wire([(xim, 13.55), (xim, Y_LB + H)])
width(xim, 13.0, 32)
wire([(xim, Y_LB), (xim, Y_WIN + H + 0.4)])
width(xim, Y_LB - 0.25, 24)
# to L1 line buffer (enters from the left)
wire([(xim, Y_WIN - 0.6), (xim, 8.0), (3.75, 8.0), (3.75, Y_LB + 0.45), (x1l, Y_LB + 0.45)])
width(3.75, 9.3, 24)
lab(xil, 7.75, "pixels, raster order", fs=6.0, va="top", mono=False)

# ------------------------------------------------------------------ FIFOs between stages and the up-routes
fifo_y = 0.55
pairs = [("f1", x1l, x1r, x1c, x2l, "L1", "L2"), ("f2", x2l, x2r, x2c, x3l, "L2", "L3"), ("f3", x3l, x3r, x3c, x4l, "L3", "L4")]
for name, pl, pr, pc, nl, a, b in pairs:
    gx0 = cols[a][1]
    gx1 = cols[b][0]
    fx = (gx0 + gx1) / 2
    box(fx - 0.42, fifo_y, 0.84, 1.05, "FIFO", fs=7, fill="#efefef")
    lab(fx, fifo_y - 0.08, f"{name} : pipe_fifo", ha="center", va="top", fs=6.2, color=G)
    wire([(pc, Y_OW), (pc, 1.07), (fx - 0.42, 1.07)])
    width(pc, 1.75, 128)
    up = nl - 0.3
    wire([(fx + 0.42, 1.07), (up, 1.07), (up, Y_LB + 0.45), (nl, Y_LB + 0.45)])
    width(up, 4.6, 128)
    # flow control: the consumer reserves room before the producer starts a pixel
    wire([(fx, fifo_y + 1.05), (fx, Y_WIN + 0.3), (pr, Y_WIN + 0.3)], dashed=True)
lab(cols["L1"][1] + 0.08, Y_WIN + 0.36, "ok", fs=6.0)
lab(cols["L2"][1] + 0.08, Y_WIN + 0.36, "ok", fs=6.0)
lab(cols["L3"][1] + 0.08, Y_WIN + 0.36, "ok", fs=6.0)

# ------------------------------------------------------------------ anchor FIFO (input pixel -> L4 requantizer) on the top lane
ya = 13.75
dot(xim, ya - 0.2)
wire([(xim, ya - 0.2), (xim + 0.0, ya - 0.2)], arrow=False)
box(10.4, ya - 0.5, 3.4, 0.6, "u_anc : anchor_fifo  4096 x 24", fs=6.8, fill="#efefef")
wire([(xir + 0.15, Y_WIN + 0.2), (xir + 0.15, ya - 0.2), (10.4, ya - 0.2)])
wire([(13.8, ya - 0.2), (x4r + 0.18, ya - 0.2), (x4r + 0.18, Y_RQ + 0.45), (x4r, Y_RQ + 0.45)])
width(19.0, ya - 0.2, 24, vertical=False)
lab(14.0, ya - 0.12, "input pixel (x+3, y+3) for output (x, y)", fs=6.2)
dot(xir + 0.15, Y_WIN + 0.2)
wire([(xir, Y_WIN + 0.2), (xir + 0.15, Y_WIN + 0.2)], arrow=False)

# ------------------------------------------------------------------ output column
xo0, xo1 = cols["OUT"]
xol, xor_ = xo0 + 0.5, xo1 - 0.3
xom = (xol + xor_) / 2
box(xol, Y_TREE - 0.3, xor_ - xol, 1.55, "2 row banks\nW x 96 b each\n(one fills,\none drains)", fill="#efefef")
box(xol, Y_RQ - 0.45, xor_ - xol, 1.0, "pixel shuffle\nk = 4c + 2dy + dx")
box(xol, Y_OW - 0.55, xor_ - xol, 0.9, "pack\n24 b -> 32 b")
wire([(x4c, Y_OW), (x4c, 1.07), (24.15, 1.07), (24.15, Y_TREE + 0.5), (xol, Y_TREE + 0.5)])
width(x4c, 1.75, 96)
wire([(xom, Y_TREE - 0.3), (xom, Y_RQ + 0.55)])
wire([(xom, Y_RQ - 0.45), (xom, Y_OW + 0.35)])
wire([(xom, Y_OW - 0.55), (xom, 0.35), (27.25, 0.35), (27.25, -0.45)])
width(xom, 1.0, 32)
lab(27.15, -0.5, "m_axis  (HR frame, raster, TLAST on last beat)", ha="right", va="top", fs=7.0)
lab(xol, Y_TREE + 1.35, "HR rows 2y, 2y+1", fs=6.0, mono=False)

# ------------------------------------------------------------------ slot counter (shared timing)
box(0.35, 4.2, 2.6, 1.2, "slot counter s = 0..5\n6 cycles per LR pixel,\nall stages concurrent", fs=6.8)
box(0.35, 2.2, 2.6, 1.3, "AXI4-Lite registers\nFRAME_W, FRAME_H,\nCONFIG.PAD_EN, START\n-> all stages", fs=6.8)
lab(0.3, 1.95, "s_axi", fs=7.4, va="top")

# ------------------------------------------------------------------ footer
ax.text(13.7, -1.25, "Branch pipe4: 142.857 MHz, 213 DSP48E1, 24,783 LUT.  960x540 -> 1920x1080: 3,156,214 cycles = 22.10 ms per frame (45.2 fps, board).  "
        "Solid = data, dashed = flow control.",
        ha="center", va="center", fontsize=7.4, color="#333333")

OUT.parent.mkdir(parents=True, exist_ok=True)
fig.savefig(OUT, dpi=160, facecolor="white", bbox_inches="tight", pad_inches=0.15)
print("wrote", OUT)
