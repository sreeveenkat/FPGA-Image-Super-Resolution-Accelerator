#!/usr/bin/env python3
"""Architecture diagrams for the README (white background, readable in GitHub light and dark mode).

Writes results/figures/arch_system.png and results/figures/arch_datapath.png.
Facts drawn: hardware/vivado/bd/design_1_m6.tcl (GP0/HP0, addresses, HP0 64 bit),
docs/REGISTER_MAP.md, docs/ARCHITECTURE_PIPELINE.md, ARCHITECTURE_PIPELINE_V4.md (branch pipe4).
Run from the project root: .venv/bin/python software/analysis/make_arch_figs.py
"""
from pathlib import Path

import matplotlib

matplotlib.use("Agg")
import matplotlib.pyplot as plt
from matplotlib.patches import FancyArrowPatch, FancyBboxPatch

OUT = Path("results/figures")

# colour scheme (same as the B.Tech report): light fill, dark border
C = {
    "ps": ("#dbeafe", "#1e40af"),
    "pl": ("#ffedd5", "#c2410c"),
    "io": ("#e2e8f0", "#334155"),
    "mem": ("#e0e7ff", "#3730a3"),
    "L1": ("#e0f2fe", "#0369a1"),
    "L2": ("#ccfbf1", "#0f766e"),
    "L3": ("#fef3c7", "#b45309"),
    "L4": ("#fee2e2", "#b91c1c"),
    "shuf": ("#ede9fe", "#6d28d9"),
    "anc": ("#fef9c3", "#a16207"),
    "white": ("#ffffff", "#334155"),
}
TXT = "#0f172a"


def box(ax, x, y, w, h, text, kind, fs=10, bold=False, r=0.12, lw=1.6, va="center", ty=None):
    fill, edge = C[kind]
    ax.add_patch(FancyBboxPatch((x, y), w, h, boxstyle=f"round,pad=0,rounding_size={r}",
                                fc=fill, ec=edge, lw=lw, zorder=2))
    ax.text(x + w / 2, ty if ty is not None else y + h / 2, text, ha="center", va=va, fontsize=fs,
            color=TXT, fontweight="bold" if bold else "normal", zorder=3, linespacing=1.3)


def arrow(ax, p0, p1, color="#334155", both=False, ls="-", lw=1.8, rad=0.0):
    ax.add_patch(FancyArrowPatch(p0, p1, arrowstyle="<|-|>" if both else "-|>", mutation_scale=14,
                                 color=color, lw=lw, ls=ls, zorder=4,
                                 connectionstyle=f"arc3,rad={rad}", shrinkA=0, shrinkB=0))


def label(ax, x, y, text, fs=8.8, color="#334155", ha="center", va="bottom", style="normal", bg=None):
    kw = {"bbox": dict(boxstyle="round,pad=0.2", fc=bg, ec="none")} if bg else {}
    ax.text(x, y, text, ha=ha, va=va, fontsize=fs, color=color, zorder=5, style=style, linespacing=1.25, **kw)


def new_fig(w, h, xmax, ymax):
    fig, ax = plt.subplots(figsize=(w, h))
    fig.patch.set_facecolor("white")
    ax.set_facecolor("white")
    ax.set_xlim(0, xmax)
    ax.set_ylim(0, ymax)
    ax.axis("off")
    return fig, ax


def save(fig, name):
    OUT.mkdir(parents=True, exist_ok=True)
    fig.savefig(OUT / name, dpi=160, facecolor="white", bbox_inches="tight", pad_inches=0.15)
    plt.close(fig)
    print("wrote", OUT / name)


def system():
    fig, ax = new_fig(13, 6.0, 15, 7)
    # PS and PL regions
    box(ax, 0.2, 0.3, 5.0, 6.2, "", "ps", r=0.25, lw=2.2)
    label(ax, 2.7, 6.05, "Processing System (PS)", fs=12.5, color=C["ps"][1], style="normal")
    label(ax, 2.7, 5.72, "ARM Cortex-A9, 650 MHz", fs=9.5, color=C["ps"][1])
    box(ax, 6.0, 0.3, 8.8, 6.2, "", "pl", r=0.25, lw=2.2)
    label(ax, 10.4, 6.05, "Programmable Logic (PL), XC7Z020", fs=12.5, color=C["pl"][1])
    label(ax, 10.4, 5.72, "100 MHz (R0) ... 142.9 MHz (v3, v4)", fs=9.5, color=C["pl"][1])

    box(ax, 0.7, 3.9, 4.0, 1.4, "Bare-metal C driver\n(software/board/sr_app)\nconfigure, start, poll DONE",
        "white", fs=9.8)
    box(ax, 0.7, 0.8, 4.0, 1.6, "DDR3, 512 MB\nLR frame 960x540 (in)\nHR frame 1920x1080 (out)", "mem", fs=9.8)

    box(ax, 6.6, 0.8, 2.7, 2.6, "AXI DMA\n\nMM2S: DDR -> stream\nS2MM: stream -> DDR\n(simple mode)",
        "io", fs=9.6)

    # accelerator with inner blocks
    box(ax, 11.0, 0.8, 3.3, 4.5, "", "white", r=0.15, lw=2.0)
    label(ax, 12.65, 4.85, "sr_accel_top", fs=11, color=TXT)
    box(ax, 11.25, 4.0, 2.8, 0.6, "AXI4-Lite registers", "io", fs=9)
    box(ax, 11.25, 3.2, 2.8, 0.6, "unpack + pad (v3, v4)", "io", fs=9)
    w = 0.62
    for i, k in enumerate(["L1", "L2", "L3", "L4"]):
        box(ax, 11.25 + i * (w + 0.106), 2.3, w, 0.65, k, k, fs=9.5, bold=True, r=0.08)
    box(ax, 11.25, 1.05, 2.8, 0.95, "pixel shuffle (x2)\n+ pack to 32 bit", "shuf", fs=9)

    # buses
    arrow(ax, (4.7, 5.0), (11.0, 5.0))
    label(ax, 7.85, 5.07, "M_AXI_GP0  AXI4-Lite  0x4000_0000", bg="#ffedd5")
    ax.plot([4.7, 7.95], [4.25, 4.25], color="#334155", lw=1.8, zorder=4)
    arrow(ax, (7.95, 4.25), (7.95, 3.4))
    label(ax, 8.05, 3.75, "M_AXI_GP0  AXI4-Lite\n0x4040_0000", ha="left", va="center", bg="#ffedd5")
    arrow(ax, (4.7, 1.6), (6.6, 1.6), both=True, color=C["mem"][1], lw=2.4)
    label(ax, 5.65, 1.95, "S_AXI_HP0, 64 bit", color=C["mem"][1], bg="white")
    arrow(ax, (9.3, 2.75), (11.0, 2.75), color=C["pl"][1], lw=2.2)
    label(ax, 10.15, 2.82, "MM2S stream\n32 bit, LR pixels", color=C["pl"][1])
    arrow(ax, (11.0, 1.35), (9.3, 1.35), color=C["pl"][1], lw=2.2)
    label(ax, 10.15, 1.42, "S2MM stream\n32 bit, HR pixels", color=C["pl"][1])
    save(fig, "arch_system.png")


def chain(ax, y, items, h=1.05, gap=0.42, x0=0.3):
    """items: (text, kind, width). Returns list of (x, w)."""
    pos = []
    x = x0
    for i, (t, k, w) in enumerate(items):
        box(ax, x, y, w, h, t, k, fs=9.4, bold=k in ("L1", "L2", "L3", "L4"))
        pos.append((x, w))
        if i < len(items) - 1:
            arrow(ax, (x + w, y + h / 2), (x + w + gap, y + h / 2))
        x += w + gap
    return pos


def datapath():
    fig, ax = new_fig(16, 6.6, 17.6, 7.4)
    # R0
    label(ax, 0.3, 6.85, "R0 (branch main): one layer at a time on a 64x64 tile", fs=12.5, color=TXT, ha="left")
    r0 = [("load\n70x70 tile", "io", 1.25), ("ram0", "mem", 0.8), ("L1\nengine", "L1", 1.05),
          ("ram1", "mem", 0.8), ("L2\nengine", "L2", 1.05), ("ram2", "mem", 0.8), ("L3\nengine", "L3", 1.05),
          ("ram3", "mem", 0.8), ("L4\nengine", "L4", 1.05), ("ram4", "mem", 0.8),
          ("pixel shuffle\n+ output", "shuf", 1.5)]
    chain(ax, 5.25, r0)
    label(ax, 0.3, 4.75, "Only one engine works at a time and each waits for the whole tile: 17 % of the 68 DSPs busy on average.\n"
          "926,201 cycles per tile x 135 tiles; 1,311.7 ms per frame = 0.76 fps (board, 100 MHz).",
          fs=9.6, ha="left", va="top")

    ax.plot([0.3, 17.3], [3.85, 3.85], color="#cbd5e1", lw=1.2)

    # pipeline
    label(ax, 0.3, 3.35, "Layer pipeline (branches pipe ... pipe4): all four layers at once on the whole frame",
          fs=12.5, color=TXT, ha="left")
    pp = [("unpack\n(+ pad v3/v4)", "io", 1.55), ("L1 stage\nline buffer\n3x3 window", "L1", 1.55),
          ("FIFO", "mem", 0.75), ("L2 stage\ndepthwise", "L2", 1.45), ("FIFO", "mem", 0.75),
          ("L3 stage\n1x1", "L3", 1.3), ("FIFO", "mem", 0.75), ("L4 stage\n+ anchor add", "L4", 1.55),
          ("2 row banks\npixel shuffle\n+ pack", "shuf", 1.7)]
    pos = chain(ax, 1.75, pp, h=1.2, gap=0.42)
    # anchor path under the chain
    (xi, wi), (x4, w4) = pos[0], pos[7]
    ax.plot([xi + wi / 2, xi + wi / 2, x4 + w4 / 2], [1.75, 1.3, 1.3], color=C["anc"][1], lw=1.8, ls="--", zorder=4)
    arrow(ax, (x4 + w4 / 2, 1.3), (x4 + w4 / 2, 1.75), color=C["anc"][1], ls="--")
    label(ax, (xi + x4 + w4) / 2, 1.0, "anchor FIFO: input pixel (x+3, y+3), added inside the L4 requantizer",
          color=C["anc"][1], fs=9.2)
    label(ax, 0.3, 0.6, "Every stage gets enough multipliers to need the same cycles per pixel, so no stage waits.\n"
          "16 cycles/pixel (pipe), 8 (v2, v2 packed, v3), 6 (v4: 3,156,214 cycles per frame, 22.10 ms = 45.2 fps on the board).",
          fs=9.6, ha="left", va="top")
    save(fig, "arch_datapath.png")


if __name__ == "__main__":
    system()
    datapath()
