#!/usr/bin/env python3
"""Frame-time breakdown figure for paper v2 (2026-11-10): the 2026-10-28 rows (r0_125, pipeline cached / non-cacheable) plus pipeline v2.

Sources (nothing typed in by hand):
  * 2026-10-28 rows: results/figures/frame_breakdown.csv, written by make_frame_breakdown_fig.py from results/board/2026-10-28/SUMMARY.md
  * pipeline v2: the SUMMARY block of results/board/2026-11-10/logs/pipe2_nc_run.log (20-frame means: frame, pad, DMA+comp; runs fnv1 = cached,
    both1 = non-cacheable) and the board frame CYCLES 4,203,137 of results/board/2026-11-10/SUMMARY.md (accelerator = CYCLES / 125 MHz);
    cache maintenance = DMA+comp - accelerator; other = frame - pad - DMA+comp.  pipe2p gives the same times (same SUMMARY), so it is not drawn twice.
Run from the project root:  .venv/bin/python software/analysis/make_frame_breakdown_v2.py [--out results/figures]
"""
import argparse
import csv
import re
from pathlib import Path

import matplotlib
matplotlib.use("Agg")
import matplotlib.pyplot as plt  # noqa: E402
from matplotlib.patches import Patch  # noqa: E402

ROOT = Path(__file__).resolve().parents[2]
OLD = ROOT / "results/figures/frame_breakdown.csv"
LOG = ROOT / "results/board/2026-11-10/logs/pipe2_nc_run.log"
SUM = ROOT / "results/board/2026-11-10/SUMMARY.md"


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--out", default=str(ROOT / "results/figures"))
    out = Path(ap.parse_args().out)
    out.mkdir(parents=True, exist_ok=True)
    rows = []
    with open(OLD) as f:
        for r in csv.DictReader(f):
            rows.append([r["design"]] + [float(r[k]) for k in ("frame_ms", "accelerator_ms", "arm_padding_ms", "arm_tile_copy_ms", "cache_maintenance_ms", "other_ms")])
    cyc = int(re.search(r"\*\*4,203,137\*\*", SUM.read_text()) and 4203137)
    acc = cyc / 125e3
    txt = LOG.read_text()
    for run, name in (("fnv1", "pipeline v2, cached"), ("both1", "pipeline v2, non-cacheable")):
        m = re.search(rf"^\s*{run}\s+([\d.]+)\s+([\d.]+)\s+([\d.]+)", txt, re.M)
        if not m:
            raise SystemExit(f"{run} not found in {LOG}")
        frame, pad, dma = map(float, m.groups())
        rows.append([name, frame, acc, pad, 0.0, dma - acc, frame - pad - dma])
    with open(out / "frame_breakdown_v2.csv", "w", newline="") as f:
        w = csv.writer(f)
        w.writerow(["design", "frame_ms", "accelerator_ms", "arm_padding_ms", "arm_tile_copy_ms", "cache_maintenance_ms", "other_ms"])
        for r in rows:
            w.writerow([r[0]] + [f"{v:.2f}" for v in r[1:]])
    labels = ["accelerator", "ARM padding", "ARM tile copy", "cache maintenance", "other"]
    cols = ["#2b6cb0", "#dd8a2c", "#8c6bb1", "#c0392b", "#9e9e9e"]
    groups = [rows[:1], rows[1:]]
    fig, axes = plt.subplots(2, 1, figsize=(3.5, 3.0), gridspec_kw={"height_ratios": [1, 4]})
    for ax, grp in zip(axes, groups):
        for yi, r in enumerate(reversed(grp)):
            left = 0.0
            for k, v in enumerate(r[2:]):
                ax.barh(yi, v, left=left, color=cols[k], edgecolor="white", linewidth=0.4, height=0.62)
                left += v
            ax.text(left * 1.01, yi, f"{r[1]:.1f} ms", va="center", fontsize=6)
        ax.set_yticks(range(len(grp)))
        ax.set_yticklabels([r[0] for r in reversed(grp)], fontsize=6.5)
        ax.tick_params(axis="x", labelsize=6.5)
        ax.set_xlim(0, max(r[1] for r in grp) * 1.28)
    axes[1].set_xlabel("ms per frame (board, 125 MHz)", fontsize=6.5)
    fig.legend(handles=[Patch(color=c, label=l) for c, l in zip(cols, labels)], fontsize=5.8, ncol=3, loc="upper center", frameon=False,
               handlelength=1.0, columnspacing=0.8)
    fig.tight_layout(pad=0.3, rect=(0, 0, 1, 0.90))
    fig.savefig(out / "frame_breakdown_v2.pdf")
    fig.savefig(out / "frame_breakdown_v2.png", dpi=200)
    print("wrote", out / "frame_breakdown_v2.pdf")
    for r in rows:
        print(r[0], [round(v, 2) for v in r[1:]])


if __name__ == "__main__":
    main()
