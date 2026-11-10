#!/usr/bin/env python3
"""Frame-time breakdown figure for the paper (stacked bars), generated from a result file.

    .venv/bin/python software/analysis/make_frame_breakdown_fig.py [--out results/figures]

Source of every number: results/board/2026-10-28/SUMMARY.md (board measurements of 2026-10-28, 125 MHz, 20-frame means).
The script parses the markdown tables of that file and stops with an error if a value is not found; nothing is typed in by hand.
Segments (ms per frame):
  accelerator       = core cycles / clock           ("core cycles / clock" row of the split table; pipeline 67.19 ms)
  ARM padding       = replicate padding by the ARM  (pad value of the model-comparison table; non-cacheable build: pad column of the flagged-run table)
  ARM tile copy     = tiled designs only            (model-comparison table)
  cache maintenance = flush input + flush output + check/invalidate rows of the split table (0 in the non-cacheable build: DMA+compute = core cycles)
  other             = frame mean minus the segments above (DMA set-up, wait-loop excess, polling)
Writes frame_breakdown.pdf/.png and frame_breakdown.csv.  Created 2026-10-29.
"""
import argparse
import csv
import re
import sys
from pathlib import Path

import matplotlib

matplotlib.use("Agg")
import matplotlib.pyplot as plt  # noqa: E402

ROOT = Path(__file__).resolve().parents[2]
SUMMARY = ROOT / "results/board/2026-10-28/SUMMARY.md"


def num(s):
    return float(s.replace(",", "").replace("*", "").strip())


def need(m, what):
    if not m:
        sys.exit(f"ERROR: {what} not found in {SUMMARY}")
    return m


def split_row(text, label):
    """Row of the 'Where the DMA-wait overhead goes' table: returns [pipe, r0_125, r3q_125] in microseconds."""
    m = need(re.search(r"^\| " + re.escape(label) + r" \| ([\d,.]+)[^|]*\| ([\d,.]+)[^|]*\| ([\d,.]+)[^|]*\|", text, re.M), f"split row '{label}'")
    return [num(m.group(i)) for i in (1, 2, 3)]


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--out", default=str(ROOT / "results/figures"))
    a = ap.parse_args()
    out = Path(a.out)
    out.mkdir(parents=True, exist_ok=True)
    t = SUMMARY.read_text()

    flush_in, flush_out, inval = (split_row(t, "flush input"), split_row(t, "flush output"), split_row(t, "check + invalidate output + CYCLES"))
    core = need(re.search(r"^\| core cycles / clock \| ([\d,.]+) \(wait[^|]*\| ([\d,.]+) \(wait", t, re.M), "core cycles row")
    core_pipe, core_r0 = num(core.group(1)) / 1000, num(core.group(2)) / 1000

    # frame means (step-2 table): r0_125 and pipe
    fr_r0 = num(need(re.search(r"^\| r0_125 \| 0x53524201 \|[^|]*\|[^|]*\| \*\*([\d,.]+) /", t, re.M), "r0_125 T3 mean").group(1))
    fr_pipe = num(need(re.search(r"^\| pipe \| 0x53525301 \|[^|]*\|[^|]*\| \*\*([\d,.]+) /", t, re.M), "pipe T3 mean").group(1))
    # padding / tile copy from the model-comparison table
    pad_r0 = num(need(re.search(r"pad ([\d.]+) \+ copy ([\d.]+) \+ DMA wait", t), "r0_125 pad/copy").group(1))
    copy_r0 = num(re.search(r"pad ([\d.]+) \+ copy ([\d.]+) \+ DMA wait", t).group(2))
    pad_pipe = num(need(re.search(r"pad ([\d.]+) \+ 22\.4 DMA/cache", t), "pipe pad").group(1))
    # non-cacheable (both buffers) run: frame, pad, DMA+compute
    nc = need(re.search(r"^\| both 1 \| \*\*([\d.]+)\*\* \([^)]*\) \| ([\d.]+) \| ([\d.]+) \|", t, re.M), "'both 1' non-cacheable row")
    fr_nc, pad_nc, dma_nc = num(nc.group(1)), num(nc.group(2)), num(nc.group(3))

    cache_pipe = (flush_in[0] + flush_out[0] + inval[0]) / 1000
    cache_r0 = (flush_in[1] + flush_out[1] + inval[1]) / 1000
    rows = [
        # name, frame, accelerator, padding, tile copy, cache maintenance
        ("r0_125 (tiled)", fr_r0, core_r0, pad_r0, copy_r0, cache_r0),
        ("pipeline, cached", fr_pipe, core_pipe, pad_pipe, 0.0, cache_pipe),
        ("pipeline, non-cacheable", fr_nc, dma_nc, pad_nc, 0.0, 0.0),
    ]
    data = []
    for name, fr, acc, pad, cp, cache in rows:
        other = fr - acc - pad - cp - cache
        data.append((name, fr, acc, pad, cp, cache, other))
        print(f"{name:26s} frame {fr:9.2f}  accelerator {acc:9.2f}  padding {pad:5.2f}  tile copy {cp:5.2f}  cache maint. {cache:6.2f}  other {other:5.2f}")
        if other < -0.5:
            sys.exit(f"ERROR: segments of {name} exceed the frame time by {-other:.2f} ms")

    with open(out / "frame_breakdown.csv", "w", newline="") as f:
        w = csv.writer(f)
        w.writerow(["design", "frame_ms", "accelerator_ms", "arm_padding_ms", "arm_tile_copy_ms", "cache_maintenance_ms", "other_ms"])
        for d in data:
            w.writerow([d[0]] + [f"{v:.2f}" for v in d[1:]])

    from matplotlib.patches import Patch
    cols = ["#4C72B0", "#DD8452", "#8172B3", "#C44E52", "#BBBBBB"]
    labels = ["accelerator", "ARM padding", "ARM tile copy", "cache maintenance", "other"]
    fig, axes = plt.subplots(2, 1, figsize=(3.5, 2.7), gridspec_kw={"height_ratios": [1, 2]})
    groups = [data[:1], data[1:]]
    for ax, grp in zip(axes, groups):
        for yi, d in enumerate(reversed(grp)):
            left = 0.0
            for k in range(5):
                v = max(d[2 + k], 0.0)
                ax.barh(yi, v, left=left, color=cols[k], edgecolor="white", linewidth=0.4, height=0.62)
                left += v
            ax.text(left + max(g[1] for g in grp) * 0.01, yi, f"{d[1]:.1f} ms", va="center", fontsize=6.5)
        ax.set_yticks(range(len(grp)))
        ax.set_yticklabels([d[0] for d in reversed(grp)], fontsize=6.5)
        ax.tick_params(axis="x", labelsize=6.5)
        ax.set_xlim(0, max(g[1] for g in grp) * 1.25)
        for sp in ("top", "right"):
            ax.spines[sp].set_visible(False)
    axes[1].set_xlabel("ms per frame (960$\\times$540, 125 MHz)", fontsize=6.5, ha="right", x=1.0)
    fig.legend(handles=[Patch(color=c, label=l) for c, l in zip(cols, labels)], fontsize=5.8, ncol=5, loc="upper center", frameon=False,
               handlelength=0.9, columnspacing=0.7, handletextpad=0.4)
    fig.tight_layout(pad=0.3, rect=(0, 0, 1, 0.93))
    fig.savefig(out / "frame_breakdown.pdf")
    fig.savefig(out / "frame_breakdown.png", dpi=200)
    print("wrote", out / "frame_breakdown.pdf")


if __name__ == "__main__":
    main()
