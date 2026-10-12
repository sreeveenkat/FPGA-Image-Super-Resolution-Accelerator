"""M7: run the whole test sets (Set5, Set14, BSD100 = 119 images) through the board and evaluate the board outputs.

    .venv/bin/python software/host_tools/board_testsets.py prep   # LR inputs + integer-model expected outputs -> data/board/testsets/<set>/
    software/board/run_testsets.sh                                # (board) every <stem>_lr.raw -> <stem>_board.raw
    .venv/bin/python software/host_tools/board_testsets.py eval   # byte-exact check + metrics -> results/quality/model_fpga_x2.{md,csv}

The LR input of every image is made exactly as in M2/M3 (dataset.pairs.make_pair: modcrop, Pillow bicubic), the expected output is
quantization.integer_reference.upscale (the golden model), and the metrics are the M1-M3 functions (evaluation.metrics). `eval` fails (exit 1)
if any board output is missing or not byte-identical to the integer model.  The FPGA metrics are computed from the BOARD files, not copied.
"""
import csv
import sys
from pathlib import Path

import numpy as np

ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(ROOT / "software" / "ai"))
sys.path.insert(0, str(Path(__file__).resolve().parent))
from dataset.pairs import list_images, load_rgb, make_pair  # noqa: E402
from evaluation.metrics import psnr_rgb, psnr_y, ssim_rgb, ssim_y  # noqa: E402
from quantization.integer_reference import QNet, upscale  # noqa: E402
from srim import fnv1a32, read_srim, write_srim  # noqa: E402

SETS = ["Set5", "Set14", "BSD100"]
QPARAMS = ROOT / "software" / "ai" / "quantization" / "qparams.npz"
OUT = ROOT / "data" / "board" / "testsets"


def images():
    for s in SETS:
        for p in list_images(ROOT / "data" / "test" / "HR" / s):
            yield s, p


def prep():
    net = QNet.load(QPARAMS)
    n = 0
    for s, p in images():
        lr, _hr = make_pair(load_rgb(p), 2)
        write_srim(OUT / s / f"{p.stem}_lr.raw", lr)
        write_srim(OUT / s / f"{p.stem}_exp.raw", upscale(net, lr))
        n += 1
        print(s, p.stem, f"{lr.shape[1]}x{lr.shape[0]}", flush=True)
    print(f"prep: {n} images in {OUT}")


def evaluate():
    rows, bad = [], []
    for s, p in images():
        _lr, hr = make_pair(load_rgb(p), 2)
        bf = OUT / s / f"{p.stem}_board.raw"
        if not bf.exists():
            bad.append(f"{s}/{p.stem}: board output missing")
            continue
        got, exp = read_srim(bf), read_srim(OUT / s / f"{p.stem}_exp.raw")
        if got.shape != exp.shape or not np.array_equal(got, exp):
            nd = int((got != exp).sum()) if got.shape == exp.shape else -1
            bad.append(f"{s}/{p.stem}: NOT byte-exact ({nd} bytes differ)")
            continue
        assert got.shape == hr.shape
        rows.append({"set": s, "image": p.stem, "method": "fpga", "fnv1a32": f"0x{fnv1a32(got.tobytes()):08x}",
                     "psnr_rgb": psnr_rgb(hr, got), "ssim_rgb": ssim_rgb(hr, got), "psnr_y": psnr_y(hr, got, 2), "ssim_y": ssim_y(hr, got, 2)})
        print(s, p.stem, "byte-exact", flush=True)
    for b in bad:
        print("FAIL", b)
    if bad:
        print(f"eval: {len(bad)} images failed, {len(rows)} byte-exact; no table written")
        return 1
    res = ROOT / "results" / "quality"
    with open(res / "model_fpga_x2.csv", "w", newline="") as f:
        w = csv.DictWriter(f, fieldnames=list(rows[0]))
        w.writeheader()
        w.writerows(rows)
    lines = ["# FPGA (ZedBoard) output, x2 - BOARD-MEASURED outputs, metrics computed on the PC", "",
             "Every board output was byte-identical to the integer model (`integer_reference.upscale`) before the metrics were computed.",
             "Same LR protocol and metric code as M1-M3 (`software/host_tools/board_testsets.py`).", "",
             "| Set | Method | PSNR RGB | SSIM RGB | PSNR Y | SSIM Y |", "|---|---|---|---|---|---|"]
    for s in SETS:
        sel = [r for r in rows if r["set"] == s]
        mean = lambda k: float(np.mean([r[k] for r in sel]))  # noqa: E731
        lines.append(f"| {s} ({len(sel)}) | fpga | {mean('psnr_rgb'):.2f} | {mean('ssim_rgb'):.4f} | {mean('psnr_y'):.2f} | {mean('ssim_y'):.4f} |")
    text = "\n".join(lines) + "\n"
    (res / "model_fpga_x2.md").write_text(text)
    print(text)
    print(f"eval: {len(rows)} of {len(rows)} images byte-exact")
    return 0


if __name__ == "__main__":
    cmd = sys.argv[1] if len(sys.argv) > 1 else ""
    if cmd == "prep":
        prep()
    elif cmd == "eval":
        sys.exit(evaluate())
    else:
        sys.exit(__doc__)
