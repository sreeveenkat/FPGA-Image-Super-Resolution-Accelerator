"""Demo/slide figure from ONE test image run on the board:  bicubic | FPGA output | ground truth, with 2 zoomed crops under each panel.
    .venv/bin/python software/host_tools/make_demo_figure.py <set> <name> <board_out.raw> <out.png>
e.g.  ... Set14 zebra data/board/demo/zebra_board.raw docs/demo/compare_zebra.png
LR / HR are made exactly as in M1-M3 (dataset.pairs.make_pair), bicubic = Pillow (M1 baseline).  The script first checks that the board file is
byte-identical to the integer model (recomputed here, not read from a file) and stops if not.  PSNR = the M1 functions (evaluation.metrics):
PSNR-Y (BT.601, 2-px shave, the main number of the tables) and PSNR-RGB, both against the ground truth.
"""
import sys
from pathlib import Path

import cv2
import numpy as np
from PIL import Image, ImageDraw, ImageFont

ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(ROOT / "software" / "ai"))
sys.path.insert(0, str(Path(__file__).resolve().parent))
from dataset.pairs import load_rgb, make_pair, upscale_pil  # noqa: E402
from evaluation.metrics import psnr_rgb, psnr_y  # noqa: E402
from quantization.integer_reference import QNet, upscale  # noqa: E402
from srim import fnv1a32, read_srim  # noqa: E402

QPARAMS = ROOT / "software" / "ai" / "quantization" / "qparams.npz"
FONT_B = "/usr/share/fonts/truetype/dejavu/DejaVuSans-Bold.ttf"
FONT = "/usr/share/fonts/truetype/dejavu/DejaVuSans.ttf"
CROP, ZOOM, GAP = 72, 4, 10           # crop size in HR pixels, nearest-neighbour zoom, gap between panels
COLORS = [(255, 40, 40), (40, 160, 255)]


def font(path, size):
    try:
        return ImageFont.truetype(path, size)
    except OSError:
        return ImageFont.load_default()


def best_crops(hr, n=2):
    """n non-overlapping CROPxCROP windows with the largest gradient energy of the ground truth (same rule as make_int8_figures.py)."""
    g = cv2.Laplacian(cv2.cvtColor(hr, cv2.COLOR_RGB2GRAY).astype(np.float32), cv2.CV_32F) ** 2
    ii = cv2.integral(g)
    h, w = g.shape
    cands = []
    for y in range(0, h - CROP, 8):
        for x in range(0, w - CROP, 8):
            cands.append((ii[y + CROP, x + CROP] - ii[y, x + CROP] - ii[y + CROP, x] + ii[y, x], y, x))
    cands.sort(reverse=True)
    out = []
    for _v, y, x in cands:
        if all(abs(y - py) >= CROP or abs(x - px) >= CROP for py, px in out):
            out.append((y, x))
        if len(out) == n:
            break
    return out


def main(argv):
    if len(argv) != 5:
        sys.exit(__doc__)
    set_name, name, board_path, out_path = argv[1:]
    hits = sorted((ROOT / "data" / "test" / "HR" / set_name).glob(f"{name}.*"))
    if len(hits) != 1:
        sys.exit(f"test image {set_name}/{name} not found (or ambiguous): {hits}")
    lr, hr = make_pair(load_rgb(hits[0]), 2)
    board = read_srim(board_path)
    golden = upscale(QNet.load(QPARAMS), lr)
    if board.shape != golden.shape or not np.array_equal(board, golden):
        sys.exit(f"STOP: board output {board_path} is NOT byte-identical to the integer model (shape {board.shape} vs {golden.shape})")
    fnv = fnv1a32(board.tobytes())
    print(f"board output == integer model: byte-exact ({board.size} bytes, fnv1a32 0x{fnv:08x})")
    bic = upscale_pil(lr, 2)
    panels = [("Bicubic (Pillow)", bic), ("FPGA output (ZedBoard, INT8 CNN)", board), ("Ground truth (original HR)", hr)]
    stats = []
    for title, img in panels[:2]:
        stats.append(f"PSNR-Y {psnr_y(hr, img, 2):.2f} dB   PSNR-RGB {psnr_rgb(hr, img):.2f} dB")
    stats.append("reference")
    for (title, _), s in zip(panels, stats):
        print(f"  {title:34s} {s}")

    h, w = hr.shape[:2]
    crops = best_crops(hr)
    zw = CROP * ZOOM
    col_w = max(w, len(crops) * zw + (len(crops) - 1) * GAP)
    head, cap, foot = 64, 64, 40
    H = head + cap + h + GAP + zw + foot
    W = 3 * col_w + 2 * GAP
    canvas = Image.new("RGB", (W, H), "white")
    d = ImageDraw.Draw(canvas)
    d.text((8, 8), f"{set_name} '{name}' (test image, never used in training): {lr.shape[1]}x{lr.shape[0]} -> {w}x{h}, super-resolution x2",
           fill="black", font=font(FONT_B, 26))
    for i, ((title, img), s) in enumerate(zip(panels, stats)):
        x0 = i * (col_w + GAP)
        d.text((x0 + 4, head), title, fill="black", font=font(FONT_B, 24))
        d.text((x0 + 4, head + 30), s, fill=(30, 30, 30), font=font(FONT, 21))
        canvas.paste(Image.fromarray(img), (x0, head + cap))
        for k, (y, x) in enumerate(crops):
            d.rectangle([x0 + x, head + cap + y, x0 + x + CROP - 1, head + cap + y + CROP - 1], outline=COLORS[k], width=2)
            z = cv2.resize(img[y:y + CROP, x:x + CROP], None, fx=ZOOM, fy=ZOOM, interpolation=cv2.INTER_NEAREST)
            zx, zy = x0 + k * (zw + GAP), head + cap + h + GAP
            canvas.paste(Image.fromarray(z), (zx, zy))
            d.rectangle([zx, zy, zx + zw - 1, zy + zw - 1], outline=COLORS[k], width=3)
    d.text((8, H - foot + 8), f"Zoomed crops: {CROP}x{CROP} px, {ZOOM}x nearest-neighbour.  PSNR-Y: BT.601 luma, 2-px border shave.  "
           f"FPGA output byte-identical to the integer model (fnv1a32 0x{fnv:08x}).", fill=(60, 60, 60), font=font(FONT, 19))
    Path(out_path).parent.mkdir(parents=True, exist_ok=True)
    canvas.save(out_path)
    print(f"wrote {out_path} ({W}x{H})")


if __name__ == "__main__":
    main(sys.argv)
