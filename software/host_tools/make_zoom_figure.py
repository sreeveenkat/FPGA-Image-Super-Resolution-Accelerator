"""Slide figure: ONE region of a test image, enlarged, as  bicubic | FPGA output | ground truth  (the difference is visible from the back of a room).
    .venv/bin/python software/host_tools/make_zoom_figure.py <set> <name> <board_out.raw> <out.png> <y> <x> <h> <w> <zoom>
(y, x, h, w) = region in ground-truth (HR) pixels; zoom = nearest-neighbour factor.  Same checks as make_demo_figure.py: the board file must be
byte-identical to the integer model (recomputed here), PSNR = the M1 functions on the WHOLE image (not only the region).
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
from evaluation.metrics import psnr_y  # noqa: E402
from quantization.integer_reference import QNet, upscale  # noqa: E402
from srim import read_srim  # noqa: E402

QPARAMS = ROOT / "software" / "ai" / "quantization" / "qparams.npz"
FB, FR = "/usr/share/fonts/truetype/dejavu/DejaVuSans-Bold.ttf", "/usr/share/fonts/truetype/dejavu/DejaVuSans.ttf"


def font(path, size):
    try:
        return ImageFont.truetype(path, size)
    except OSError:
        return ImageFont.load_default()


def main(argv):
    if len(argv) != 10:
        sys.exit(__doc__)
    set_name, name, board_path, out_path = argv[1:5]
    y, x, h, w, zoom = (int(v) for v in argv[5:10])
    hits = sorted((ROOT / "data" / "test" / "HR" / set_name).glob(f"{name}.*"))
    if len(hits) != 1:
        sys.exit(f"test image {set_name}/{name} not found: {hits}")
    lr, hr = make_pair(load_rgb(hits[0]), 2)
    board = read_srim(board_path)
    if board.shape != hr.shape or not np.array_equal(board, upscale(QNet.load(QPARAMS), lr)):
        sys.exit(f"STOP: {board_path} is NOT byte-identical to the integer model")
    if y < 0 or x < 0 or y + h > hr.shape[0] or x + w > hr.shape[1]:
        sys.exit(f"region outside the image ({hr.shape[1]}x{hr.shape[0]})")
    bic = upscale_pil(lr, 2)
    panels = [("Bicubic", f"PSNR-Y {psnr_y(hr, bic, 2):.2f} dB", bic),
              ("FPGA (ZedBoard CNN)", f"PSNR-Y {psnr_y(hr, board, 2):.2f} dB", board),
              ("Ground truth", "original", hr)]
    zw, zh, gap, head, foot = w * zoom, h * zoom, 14, 100, 70
    canvas = Image.new("RGB", (3 * zw + 2 * gap, head + zh + foot), "white")
    d = ImageDraw.Draw(canvas)
    for i, (title, sub, img) in enumerate(panels):
        x0 = i * (zw + gap)
        d.text((x0 + 6, 6), title, fill="black", font=font(FB, 40))
        d.text((x0 + 6, 54), sub, fill=(40, 40, 40), font=font(FR, 32))
        z = cv2.resize(img[y:y + h, x:x + w], None, fx=zoom, fy=zoom, interpolation=cv2.INTER_NEAREST)
        canvas.paste(Image.fromarray(z), (x0, head))
    d.text((6, head + zh + 8), f"{set_name} '{name}' (test image, not used in training), x2 super-resolution; region {w}x{h} px enlarged {zoom}x.\n"
           "FPGA output byte-identical to the integer model; PSNR over the whole image.", fill=(70, 70, 70), font=font(FR, 22))
    Path(out_path).parent.mkdir(parents=True, exist_ok=True)
    canvas.save(out_path)
    print(f"wrote {out_path} ({canvas.size[0]}x{canvas.size[1]})")


if __name__ == "__main__":
    main(sys.argv)
