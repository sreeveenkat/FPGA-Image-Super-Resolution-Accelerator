"""Build the image-quality ladder report from results/quality/q_<name>.json (written by eval_candidate.py).

Run from the project root:  .venv/bin/python software/ai/evaluation/ladder_report.py  ->  results/quality/image_quality_ladder.md

Rungs (every one has 2 seeds):  R0 baseline recipe (2-seed mean: the deployed checkpoint + baseline_s1, a retrain) | R1 plain SRNet, new recipe | R2 re-parameterized (rep) | R3 plain + anchor | R4 rep + anchor,
each as FP32, as INT8 by post-training quantization (PTQ) and as INT8 after quantization-aware training (QAT, per-layer weight scales = the RTL scheme).
INT8 always means the NumPy integer model, i.e. what the RTL computes.  "mean +- h" is the mean over seeds and h the half-range (max-min)/2.
Gain rows that involve R0 are "vs R0 2-seed mean": R0 is the mean of the deployed checkpoint and one retrain (baseline_s1), NOT the deployed checkpoint alone (see table_a_x2.md).
A gain is marked "(within noise)" when it is smaller than the larger of the two half-ranges.  Selection used the 42 clean validation images only.
"""
import json
from pathlib import Path

import numpy as np

ROOT = Path(__file__).resolve().parents[3]
Q = ROOT / "results" / "quality"
SETS = ["Set5", "Set14", "BSD100"]
COLS = [(s, m) for s in SETS for m in ("psnr_y", "ssim_y")] + [("val", "psnr_y")]

# key -> (label, json names)
R = {
    "R0": ("R0 (2-seed mean: deployed + baseline_s1; 180 imgs, 50k steps)", ["baseline", "baseline_s1"]),
    "R1": ("R1 plain, DIV2K-800+Flickr2K, 8-fold aug, cosine, 300k steps", ["plain_s0", "plain_s1"]),
    "R2": ("R2 rep (re-parameterized training blocks, merged)", ["rep_s0", "rep_s1"]),
    "R3": ("R3 plain + NN anchor", ["plainA_s0", "plainA_s1"]),
    "R4": ("R4 rep + NN anchor", ["repA_s0", "repA_s1"]),
    "R1q": ("R1 + QAT", ["plain_qat_s0", "plain_qat_s1"]),
    "R2q": ("R2 + QAT", ["rep_qat_s0", "rep_qat_s1"]),
    "R3q": ("R3 + QAT", ["plainA_qat_s0", "plainA_qat_s1"]),
    "R4q": ("R4 + QAT", ["repA_qat_s0", "repA_qat_s1"]),
}
FP32_ROWS = ["R0", "R1", "R2", "R3", "R4"]
INT8_PTQ_ROWS = ["R0", "R1", "R2", "R3", "R4"]
INT8_QAT_ROWS = ["R1q", "R2q", "R3q", "R4q"]
# (label, a, b, kind): gain of b over a
FP32_GAINS = [("data+recipe: R1 - R0 (vs R0 2-seed mean)", "R0", "R1"), ("rep blocks: R2 - R1", "R1", "R2"), ("anchor on plain: R3 - R1", "R1", "R3"),
              ("anchor on rep: R4 - R2", "R2", "R4"), ("rep on anchor: R4 - R3", "R3", "R4")]
INT8_GAINS = [("PTQ -> QAT, plain: R1q - R1", "R1", "R1q"), ("PTQ -> QAT, rep: R2q - R2", "R2", "R2q"),
              ("new plain+QAT: R1q - R0 (vs R0 2-seed mean)", "R0", "R1q"), ("rep blocks (INT8): R2q - R1q", "R1q", "R2q"),
              ("anchor on plain (INT8): R3q - R1q", "R1q", "R3q"), ("anchor on rep (INT8): R4q - R2q", "R2q", "R4q"),
              ("rep on anchor (INT8): R4q - R3q", "R3q", "R4q"),
              ("rep+QAT: R2q - R0 (vs R0 2-seed mean)", "R0", "R2q"), ("anchor+QAT vs rep+QAT: R3q - R2q", "R2q", "R3q"),
              ("plain+anchor+QAT: R3q - R0 (vs R0 2-seed mean)", "R0", "R3q"), ("everything: R4q - R0 (vs R0 2-seed mean)", "R0", "R4q")]


def load(name):
    p = Q / f"q_{name}.json"
    return json.loads(p.read_text()) if p.exists() else None


def vals(key, kind):
    """array (seeds, columns) of the chosen method ('fp32' or 'int8'), or None."""
    runs = [load(n) for n in R[key][1]]
    rows = [[r["sets"][s][kind][m] for s, m in COLS] for r in runs if r and kind in r["sets"]["Set5"]]
    return np.array(rows) if rows else None


def fmt(v, i):
    return f"{v:.3f}" if COLS[i][1] == "psnr_y" else f"{v:.4f}"


def table(title, rows, kind, gains, extra=()):
    out = [f"## {title}", "", "| Row | " + " | ".join(f"{s} {'PSNR' if m == 'psnr_y' else 'SSIM'}" if s != "val" else "val42 PSNR" for s, m in COLS) + " |",
           "|---|" + "---|" * len(COLS)]
    data = {}
    for k in list(rows) + list(extra):  # `extra` rows only feed the gain table (e.g. the PTQ rows for "PTQ -> QAT")
        v = vals(k, kind)
        if v is None:
            continue
        data[k] = v
        if k in extra:
            continue
        out.append(f"| **{R[k][0]}** (n={len(v)}) | " + " | ".join(f"{fmt(v[:, i].mean(), i)} ± {fmt((v[:, i].max() - v[:, i].min()) / 2, i)}" for i in range(len(COLS))) + " |")
        if len(v) > 1:
            for j, n in enumerate(R[k][1][:len(v)]):
                out.append(f"| &nbsp;&nbsp;seed `{n}` | " + " | ".join(fmt(v[j, i], i) for i in range(len(COLS))) + " |")
    out += ["", "| Gain (mean over seeds) | " + " | ".join(f"{s} {'PSNR' if m == 'psnr_y' else 'SSIM'}" if s != "val" else "val42 PSNR" for s, m in COLS) + " |", "|---|" + "---|" * len(COLS)]
    for label, a, b in gains:
        if a in data and b in data:
            d = data[b].mean(0) - data[a].mean(0)
            noise = np.maximum((data[a].max(0) - data[a].min(0)) / 2, (data[b].max(0) - data[b].min(0)) / 2)
            cells = []
            for i in range(len(COLS)):
                tag = "" if abs(d[i]) >= noise[i] else " (within noise)"
                cells.append((f"{d[i]:+.3f}" if COLS[i][1] == "psnr_y" else f"{d[i]:+.4f}") + tag)
            out.append(f"| {label} | " + " | ".join(cells) + " |")
    out.append("")
    return out, data


def main():
    out = ["# Image-quality ladder (x2; PSNR-Y / SSIM-Y, Y = BT.601, 2-px shave, Gaussian SSIM)", "",
           "Mean ± half-range over seeds. Every choice (checkpoint, QAT step) was made on the 42 clean DIV2K validation images; Set5/Set14/BSD100 are reporting only.",
           "INT8 = the NumPy integer model (bit-exact with the RTL).  QAT checkpoints are only meaningful quantized, so they have no FP32 row.", ""]
    o, _ = table("FP32", FP32_ROWS, "fp32", FP32_GAINS)
    out += o
    o, _ = table("INT8 by post-training quantization (PTQ, 99.99 percentile, per-layer weight scales)", INT8_PTQ_ROWS, "int8", FP32_GAINS)
    out += o
    o, _ = table("INT8 after quantization-aware training (QAT, per-layer weight scales)", ["R0"] + INT8_QAT_ROWS, "int8", INT8_GAINS, extra=INT8_PTQ_ROWS[1:])
    out += o
    b = load("baseline")
    if b:
        out += ["## Reference points", "", "| | Set5 | Set14 | BSD100 / BSD200 |", "|---|---|---|---|",
                "| bicubic (this project, PSNR-Y / SSIM-Y) | " + " | ".join(f"{b['sets'][s]['bicubic']['psnr_y']:.2f} / {b['sets'][s]['bicubic']['ssim_y']:.4f}" for s in SETS) + " |",
                "| FSRCNN paper, bicubic row (PSNR) | 33.66 | 30.23 | 29.70 (BSD200) |",
                "| FSRCNN-s (PSNR / SSIM; 91+General-100) | 36.58 / 0.9532 | 32.28 / 0.9052 | 31.48 / 0.9027 (BSD200) |",
                "| FSRCNN (PSNR / SSIM; 91+General-100) | 37.00 / 0.9558 | 32.63 / 0.9088 | 31.80 / 0.9074 (BSD200) |", "",
                "FSRCNN numbers: arXiv 1608.00367, Tables 4 and 6 (read from the paper). FSRCNN used BSD200, not BSD100, so that column is not comparable image for image."]
    (Q / "image_quality_ladder.md").write_text("\n".join(out) + "\n")
    print("\n".join(out))


if __name__ == "__main__":
    main()
