"""Side-by-side crops: bicubic | deployed INT8 | R2q INT8 | R3q INT8 | HR, from the NumPy integer model (what the RTL computes).

Images are NOT hand-picked.  From the per-image PSNR-Y in results/quality/q_*.json (Set5/Set14/BSD100 only) the script takes four images by rule:
  gain   = the largest gain of R2q over the deployed model,
  median = the median gain of R2q over the deployed model,
  worst  = the smallest gain (or largest loss) of R2q over the deployed model,
  anchor = the largest gain of R3q over R2q.
The crop (96x96 HR pixels, shown 4x) is the window where |R3q - R2q| + |R2q - deployed| is largest, so it shows where the models differ.
Per seed the checkpoint with the better validation score is used (`--seed-r2/--seed-r3` override).

Run from the project root:
  .venv/bin/python software/ai/evaluation/make_ladder_crops.py  -> results/images/ladder_crops_*.png (git-ignored) and results/quality/ladder_crops.md
"""
import argparse
import json
import sys
from pathlib import Path

import cv2
import numpy as np
import torch

ROOT = Path(__file__).resolve().parents[3]
sys.path.insert(0, str(ROOT / "software" / "ai"))
from dataset.pairs import list_images, load_rgb, make_pair, upscale_pil  # noqa: E402
from evaluation.eval_int8 import QPARAMS, qnet_from_arrays  # noqa: E402
from quantization.integer_reference import QNet, upscale  # noqa: E402
from quantization.quantize import calibration_crops, load_fp32, quantize  # noqa: E402

Q = ROOT / "results" / "quality"
CK = ROOT / "software" / "ai" / "checkpoints" / "q"
SETS = ["Set5", "Set14", "BSD100"]
WIN, ZOOM = 96, 4


def q(name):
    return json.loads((Q / f"q_{name}.json").read_text())


def best_seed(prefix):
    """checkpoint name (without .pt) of the seed with the higher validation PSNR (int8, per-image mean over val42)."""
    best = max((q(f"{prefix}_s{s}")["sets"]["val"]["int8"]["psnr_y"], s) for s in (0, 1) if (Q / f"q_{prefix}_s{s}.json").exists())
    return f"{prefix}_s{best[1]}", best[0]


def qnet_for(ckname):
    path = CK / f"{ckname}.pt"
    ck = torch.load(path, map_location="cpu")
    arrays, _ = quantize(load_fp32(str(path)), calibration_crops(100), 99.99, bool(ck.get("per_channel", False)), ck.get("act_max"))
    return qnet_from_arrays(arrays)


def per_image(name):
    d = q(name)["sets"]
    return {f"{s}/{r['image']}": r["psnr_y"] for s in SETS for r in d[s]["int8"]["per_image"]}


def label(img, text):
    img = np.ascontiguousarray(img)
    cv2.rectangle(img, (0, 0), (img.shape[1], 16), (0, 0, 0), -1)
    cv2.putText(img, text, (3, 12), cv2.FONT_HERSHEY_SIMPLEX, 0.4, (255, 255, 255), 1, cv2.LINE_AA)
    return img


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--r2", default="rep_qat", help="prefix of the R2q json/checkpoint names (seed suffix _s0/_s1 added)")
    ap.add_argument("--r3", default="plainA_qat")
    a = ap.parse_args()
    r2, v2 = best_seed(a.r2)
    r3, v3 = best_seed(a.r3)
    base, p0, p2, p3 = "baseline", per_image("baseline"), per_image(r2), per_image(r3)
    keys = sorted(p0)
    g20 = {k: p2[k] - p0[k] for k in keys}
    g32 = {k: p3[k] - p2[k] for k in keys}
    order = sorted(keys, key=lambda k: g20[k])
    picks = [("gain", order[-1]), ("median", order[len(order) // 2]), ("worst", order[0]), ("anchor", max(keys, key=lambda k: g32[k]))]
    print(f"R2q = {r2} (val {v2:.3f}), R3q = {r3} (val {v3:.3f})")
    nets = {"deployed": QNet.load(QPARAMS), "R2q": qnet_for(r2), "R3q": qnet_for(r3)}
    out_dir = ROOT / "results" / "images"
    out_dir.mkdir(parents=True, exist_ok=True)
    md = ["# Side-by-side crops (rule-based picks)", "", f"R2q = `{r2}` (val42 {v2:.3f} dB), R3q = `{r3}` (val42 {v3:.3f} dB); deployed = qparams.npz. INT8 integer model. "
          "Crop = 96x96 HR window where the models differ most, shown 4x (nearest).", "",
          "| pick | image | bicubic | deployed | R2q | R3q | window (y,x) |", "|---|---|---|---|---|---|---|"]
    for why, key in picks:
        s, stem = key.split("/")
        path = next(p for p in list_images(ROOT / "data" / "test" / "HR" / s) if p.stem == stem)
        lr, hr = make_pair(load_rgb(path), 2)
        outs = {"bicubic": upscale_pil(lr, 2), **{n: upscale(net, lr) for n, net in nets.items()}}
        diff = (np.abs(outs["R3q"].astype(np.float32) - outs["R2q"]) + np.abs(outs["R2q"].astype(np.float32) - outs["deployed"])).mean(2)
        h, w = diff.shape
        ii = cv2.integral(diff)
        best, pos = -1.0, (0, 0)
        for y in range(0, h - WIN + 1, 8):
            for x in range(0, w - WIN + 1, 8):
                sc = ii[y + WIN, x + WIN] - ii[y, x + WIN] - ii[y + WIN, x] + ii[y, x]
                if sc > best:
                    best, pos = sc, (y, x)
        y, x = pos
        panels = []
        for n in ("bicubic", "deployed", "R2q", "R3q"):
            p = cv2.resize(outs[n][y:y + WIN, x:x + WIN], None, fx=ZOOM, fy=ZOOM, interpolation=cv2.INTER_NEAREST)
            panels.append(label(p, f"{n}  {key} {p0[key] if n == 'deployed' else p2[key] if n == 'R2q' else p3[key] if n == 'R3q' else 0:.2f}" if n != "bicubic" else "bicubic"))
        panels.append(label(cv2.resize(hr[y:y + WIN, x:x + WIN], None, fx=ZOOM, fy=ZOOM, interpolation=cv2.INTER_NEAREST), "HR (ground truth)"))
        png = out_dir / f"ladder_crops_{why}_{s}_{stem}.png"
        cv2.imwrite(str(png), cv2.cvtColor(np.concatenate(panels, 1), cv2.COLOR_RGB2BGR))
        md.append(f"| {why} | {key} | - | {p0[key]:.2f} | {p2[key]:.2f} | {p3[key]:.2f} | ({y},{x}) |")
        print(why, key, f"deployed {p0[key]:.2f} R2q {p2[key]:.2f} R3q {p3[key]:.2f}", "->", png.name)
    md += ["", "Whole-image PSNR-Y (dB) in the table; the crops are in `results/images/ladder_crops_*.png` (git-ignored, regenerate with this script)."]
    (Q / "ladder_crops.md").write_text("\n".join(md) + "\n")


if __name__ == "__main__":
    main()
