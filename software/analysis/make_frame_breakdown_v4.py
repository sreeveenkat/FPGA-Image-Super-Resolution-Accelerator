"""Measured frame-time breakdown of the pipeline designs (board, 20-frame means) for the paper.

accelerator = frame CYCLES / clock (equals the measured DMA wait within 0.01 ms); pad = measured ARM padding;
cache maintenance = frame - accelerator - pad (cached buffers only).  Sources:
  pipeline, v2:  results/figures/frame_breakdown_v2.csv (from results/board/2026-10-28 and 2026-11-10/SUMMARY.md)
  v3, v4:        results/board/2026-11-18/SUMMARY.md sections 1 and 1b (fnv / both means, T2 frame CYCLES, 142.857 MHz)
Usage: .venv/bin/python software/analysis/make_frame_breakdown_v4.py  -> results/figures/frame_breakdown_v4.{pdf,png,csv}
"""
from pathlib import Path
import matplotlib
matplotlib.use("Agg")
import matplotlib.pyplot as plt

F3, F4 = 4_205_065 / 142.857e3, 3_156_225 / 142.857e3          # ms
rows = [  # label, frame, accelerator, pad
    ("Pipeline, 125 MHz, cached", 95.36, 67.19, 5.79),
    ("Pipeline, 125 MHz, NC", 70.52, 67.19, 3.32),
    ("v2, 125 MHz, cached", 61.64, 33.63, 5.71),
    ("v2, 125 MHz, NC", 36.95, 33.63, 3.32),
    ("v3, 142.9 MHz, cached", 51.45, F3, 0.0),
    ("v3, 142.9 MHz, NC", 29.44, F3, 0.0),
    ("v4, 142.9 MHz, cached", 44.11, F4, 0.0),
    ("v4, 142.9 MHz, NC", 22.10, F4, 0.0),
]
out = Path(__file__).resolve().parents[2] / "results/figures"
out.mkdir(parents=True, exist_ok=True)
with open(out / "frame_breakdown_v4.csv", "w") as f:
    f.write("design,frame_ms,accelerator_ms,arm_padding_ms,cache_maintenance_ms\n")
    for l, t, a, p in rows:
        f.write(f"{l},{t:.2f},{a:.2f},{p:.2f},{max(t - a - p, 0):.2f}\n")
fig, ax = plt.subplots(figsize=(3.5, 2.5))
cols = {"accelerator": "#2b6cb0", "ARM padding": "#dd8452", "cache maintenance": "#8c8c8c"}
for i, (l, t, a, p) in enumerate(rows):
    y = len(rows) - 1 - i
    c = max(t - a - p, 0) if "cached" in l else 0.0
    ax.barh(y, a, color=cols["accelerator"], height=0.7)
    ax.barh(y, p, left=a, color=cols["ARM padding"], height=0.7)
    ax.barh(y, c, left=a + p, color=cols["cache maintenance"], height=0.7)
    ax.text(t + 1, y, f"{t:.2f}", va="center", fontsize=6.5)
ax.set_yticks(range(len(rows)))
ax.set_yticklabels([r[0] for r in reversed(rows)], fontsize=6.5)
ax.set_xlabel("ms per 960$\\times$540 frame (board)", fontsize=7)
ax.tick_params(axis="x", labelsize=6.5)
ax.set_xlim(0, 108)
ax.legend([plt.Rectangle((0, 0), 1, 1, color=v) for v in cols.values()], list(cols), fontsize=6.3,
          loc="lower center", bbox_to_anchor=(0.30, 1.0), ncol=3, frameon=False, handlelength=1.2, columnspacing=0.8)
for s in ("top", "right"):
    ax.spines[s].set_visible(False)
fig.tight_layout(pad=0.2)
fig.savefig(out / "frame_breakdown_v4.pdf"); fig.savefig(out / "frame_breakdown_v4.png", dpi=300)
print(open(out / "frame_breakdown_v4.csv").read())
