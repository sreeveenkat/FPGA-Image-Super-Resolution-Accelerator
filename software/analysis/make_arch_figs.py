#!/usr/bin/env python3
"""RTL block diagrams for the README, schematic style (black on white, instance : module names, bus widths).

Writes results/figures/rtl_r0.png and results/figures/rtl_pipe4.png.
Names and widths are the ones in the RTL:
  R0    (main):  sr_accel_top.v -> sr_axis_wrapper.v (wrap) -> sr_tile_core.v (core): ram0..ram4 tile_ram_split, e1..e4 conv_engine
  v4    (pipe4): sr_accel_top.v -> sr_pipe_core.v (core): s1..s4 pipe_stage, f1..f3 pipe_fifo, u_anc anchor_fifo, u_out pipe_out
Run from the project root: .venv/bin/python software/analysis/make_arch_figs.py
"""
from pathlib import Path

import matplotlib

matplotlib.use("Agg")
import matplotlib.pyplot as plt
from matplotlib.patches import Rectangle

OUT = Path("results/figures")
K = "black"
MONO = "DejaVu Sans Mono"
plt.rcParams["font.family"] = "DejaVu Sans"


def new_fig(w, h, xmax, ymax):
    fig, ax = plt.subplots(figsize=(w, h))
    fig.patch.set_facecolor("white")
    ax.set_facecolor("white")
    ax.set_xlim(0, xmax)
    ax.set_ylim(0, ymax)
    ax.set_aspect("equal")
    ax.axis("off")
    return fig, ax


def blk(ax, x, y, w, h, inst, module, body="", fill="white"):
    """Block: instance:module above the top edge (like a netlist viewer), optional body text inside."""
    ax.add_patch(Rectangle((x, y), w, h, fc=fill, ec=K, lw=1.3, zorder=2))
    ax.text(x + 0.05, y + h + 0.06, f"{inst} : {module}" if inst else module, ha="left", va="bottom",
            fontsize=7.6, family=MONO, zorder=3)
    if body:
        ax.text(x + w / 2, y + h / 2, body, ha="center", va="center", fontsize=7.5, zorder=3, linespacing=1.3)


def hier(ax, x, y, w, h, name):
    ax.add_patch(Rectangle((x, y), w, h, fc="none", ec="#555555", lw=1.0, ls=(0, (5, 3)), zorder=1))
    ax.text(x + 0.08, y + h - 0.08, name, ha="left", va="top", fontsize=8.2, family=MONO, color="#333333", zorder=3)


def bus(ax, pts, width=None, wpos=0.5, arrow=True, lw=1.3):
    """Polyline with an arrowhead at the end and a bus-width slash on the segment at fraction wpos of the first segment."""
    xs, ys = zip(*pts)
    ax.plot(xs, ys, color=K, lw=lw, zorder=4, solid_capstyle="butt")
    if arrow:
        (x0, y0), (x1, y1) = pts[-2], pts[-1]
        ax.annotate("", xy=(x1, y1), xytext=(x0 + 0.85 * (x1 - x0), y0 + 0.85 * (y1 - y0)),
                    arrowprops=dict(arrowstyle="-|>", color=K, lw=lw, mutation_scale=9, shrinkA=0, shrinkB=0), zorder=5)
    if width is not None:
        (x0, y0), (x1, y1) = pts[0], pts[1]
        mx, my = x0 + wpos * (x1 - x0), y0 + wpos * (y1 - y0)
        d = 0.09
        ax.plot([mx - d, mx + d], [my - d * 1.6, my + d * 1.6], color=K, lw=1.0, zorder=5)
        horiz = abs(y1 - y0) < 1e-9
        ax.text(mx + (0 if horiz else 0.12), my + (0.13 if horiz else 0), str(width), ha="center" if horiz else "left",
                va="bottom" if horiz else "center", fontsize=7.2, family=MONO, zorder=5)


def port(ax, x, y, name, side="left"):
    ax.text(x - 0.08 if side == "left" else x + 0.08, y, name, ha="right" if side == "left" else "left", va="center",
            fontsize=7.8, family=MONO, zorder=5)


def save(fig, name):
    OUT.mkdir(parents=True, exist_ok=True)
    fig.savefig(OUT / name, dpi=170, facecolor="white", bbox_inches="tight", pad_inches=0.12)
    plt.close(fig)
    print("wrote", OUT / name)


def r0():
    fig, ax = new_fig(15, 3.9, 21.0, 5.0)
    hier(ax, 0.9, 0.3, 19.4, 4.4, "sr_accel_top  (VERSION 0x53520602, 100 MHz)")
    hier(ax, 1.2, 0.55, 18.8, 3.6, "wrap : sr_axis_wrapper   32-bit AXI-Stream <-> byte stream")
    hier(ax, 3.0, 0.8, 15.4, 2.9, "core : sr_tile_core   HC = 64 (70x70 in, 128x128 out per tile)")

    yc = 1.9   # centre line of the data path
    h = 0.9
    # unpack / pack in the wrapper
    blk(ax, 1.5, yc - h / 2, 1.1, h, "", "unpack", "32 -> 8")
    blk(ax, 18.7, yc - h / 2, 1.1, h, "", "pack", "8 -> 32")
    port(ax, 0.9, yc, "s_axis")
    bus(ax, [(0.9, yc), (1.5, yc)], 32)
    bus(ax, [(19.8, yc), (20.3, yc)], 32)
    port(ax, 20.3, yc, "m_axis", side="right")

    # loader -> ram0 -> e1 -> ram1 ... -> ram4 -> shuffle
    x = 3.3
    items = [("loader", "loader", 0.8, None), ("ram0", "tile_ram_split", 1.05, 24), ("e1", "conv_engine", 0.95, None),
             ("ram1", "tile_ram_split", 1.05, 128), ("e2", "conv_engine", 0.95, None), ("ram2", "tile_ram_split", 1.05, 128),
             ("e3", "conv_engine", 0.95, None), ("ram3", "tile_ram_split", 1.05, 128), ("e4", "conv_engine", 0.95, None),
             ("ram4", "tile_ram_split", 1.05, 96), ("shuf", "pixel_shuffle", 1.0, None)]
    bodies = {"loader": "load\nFSM", "e1": "L1\n3x3\n3->16", "e2": "L2\ndw 3x3", "e3": "L3\n1x1", "e4": "L4\n3x3\n16->12",
              "ram0": "4900\nx 24", "ram1": "4624\nx 128", "ram2": "4356\nx 128", "ram3": "4356\nx 128", "ram4": "4096\nx 96",
              "shuf": "k=4c+\n2dy+dx"}
    gap = 0.22
    prev_right, prev_w = 2.6, 8
    for i, (inst, mod, w, width) in enumerate(items):
        top = False
        yy = yc - h / 2
        blk(ax, x, yy, w, h, "", "", bodies[inst], fill="#efefef" if mod == "tile_ram_split" else "white")
        ax.text(x + w / 2, yy + h + 0.06 if not top else yy - 0.06, f"{inst}", ha="center",
                va="bottom" if not top else "top", fontsize=7.6, family=MONO)
        bus(ax, [(prev_right, yc), (x, yc)], prev_w if prev_w else None)
        prev_right, prev_w = x + w, width
        x += w + gap + (0.18 if width else 0)
    bus(ax, [(prev_right, yc), (18.7, yc)], 8)

    ax.text(10.7, 0.98, "ram* = tile_ram_split (block RAM), e* = conv_engine (folded MACs, one requant).  Sequencer FSM runs e1, e2, e3, e4 one after another.",
            ha="center", va="center", fontsize=7.6, color="#333333")
    ax.text(1.6, 3.15, "AXI4-Lite\nregisters", ha="center", va="center", fontsize=7.6, family=MONO, zorder=3)
    ax.add_patch(Rectangle((1.05, 2.82), 1.1, 0.66, fc="white", ec=K, lw=1.1, zorder=2))
    port(ax, 0.9, 3.15, "s_axi")
    bus(ax, [(0.9, 3.15), (1.05, 3.15)])
    save(fig, "rtl_r0.png")


def pipe4():
    fig, ax = new_fig(15, 4.7, 23.0, 6.8)
    hier(ax, 0.9, 0.3, 21.4, 6.2, "sr_accel_top  (VERSION 0x53529301, 142.857 MHz)")
    hier(ax, 2.6, 0.75, 17.9, 5.1, "core : sr_pipe_core   NS = 6 slots per pixel, PACK = 1")

    yc = 3.3
    h = 1.15
    # registers
    ax.add_patch(Rectangle((1.05, 5.0), 1.25, 0.8, fc="white", ec=K, lw=1.1, zorder=2))
    ax.text(1.675, 5.4, "AXI4-Lite\nregisters", ha="center", va="center", fontsize=7.6, family=MONO)
    port(ax, 0.9, 5.4, "s_axi")
    bus(ax, [(0.9, 5.4), (1.05, 5.4)])
    ax.text(1.675, 4.75, "FRAME_W/H\nCONFIG", ha="center", va="top", fontsize=6.8, family=MONO, color="#333333")

    port(ax, 0.9, yc, "s_axis")
    bus(ax, [(0.9, yc), (3.0, yc)], 32, wpos=0.3)

    stages = [
        ("unpk", "unpack + pad logic", 1.6, "32 -> 24\nreplicate\npad (PL)", 24),
        ("s1", "pipe_stage", 1.9, "L1  conv 3x3\n3 -> 16\n60 DSP", 128),
        ("f1", "pipe_fifo", 0.75, "FIFO", 128),
        ("s2", "pipe_stage", 1.9, "L2  depthwise\n3x3\n33 DSP", 128),
        ("f2", "pipe_fifo", 0.75, "FIFO", 128),
        ("s3", "pipe_stage", 1.5, "L3  conv 1x1\n16 -> 16\n38 DSP", 128),
        ("f3", "pipe_fifo", 0.75, "FIFO", 128),
        ("s4", "pipe_stage", 2.2, "L4  conv 3x3\n16 -> 12, + anchor\n80 DSP + LUT mult.", 96),
        ("u_out", "pipe_out", 1.7, "2 row banks\npixel shuffle\n24 -> 32", None),
    ]
    x = 3.0
    gap = 0.5
    pos = {}
    for i, (inst, mod, w, body, wout) in enumerate(stages):
        blk(ax, x, yc - h / 2, w, h, "", "", body, fill="#efefef" if mod == "pipe_fifo" else "white")
        lab = mod if inst == "unpk" else (inst if mod == "pipe_fifo" else f"{inst} : {mod}")
        ax.text(x + w / 2, yc + h / 2 + 0.06, lab, ha="center", va="bottom", fontsize=7.4, family=MONO)
        pos[inst] = (x, w)
        if wout is not None:
            bus(ax, [(x + w, yc), (x + w + gap, yc)], wout)
        x += w + gap
    xo, wo = pos["u_out"]
    bus(ax, [(xo + wo, yc), (22.3, yc)], 32, wpos=0.5)
    port(ax, 22.3, yc, "m_axis", side="right")

    # anchor FIFO under the chain
    xa = 10.6
    blk(ax, xa, 1.25, 1.9, 0.75, "", "", "4096 x 24", fill="#efefef")
    ax.text(xa + 0.95, 1.25 - 0.06, "u_anc : anchor_fifo", ha="center", va="top", fontsize=7.4, family=MONO)
    xu, wu = pos["unpk"]
    x4, w4 = pos["s4"]
    bus(ax, [(xu + wu * 0.5, yc - h / 2), (xu + wu * 0.5, 1.625), (xa, 1.625)], 24, wpos=0.45)
    bus(ax, [(xa + 1.9, 1.625), (x4 + w4 * 0.5, 1.625), (x4 + w4 * 0.5, yc - h / 2)], 24, wpos=0.5)

    ax.text(11.6, 0.5, "Each pipe_stage: 2-row line buffer, 3x3 window, packed MACs, adder trees, requant (acc*M + 2^(S-1)) >> S.  "
            "All four run at the same time, 6 cycles per LR pixel.",
            ha="center", va="center", fontsize=7.6, color="#333333")
    save(fig, "rtl_pipe4.png")


if __name__ == "__main__":
    r0()
    pipe4()
