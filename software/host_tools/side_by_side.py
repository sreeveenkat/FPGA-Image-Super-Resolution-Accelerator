"""Side-by-side picture for the demo: LR input (shown at 2x with nearest-neighbour, so both halves have the same size) | FPGA x2 output.
    .venv/bin/python software/host_tools/side_by_side.py <lr.raw|lr.png> <fpga_out.raw|png> <out.png> [title]
Optional title line on top.  Only for viewing: no numbers are computed here.
"""
import sys
from pathlib import Path

import numpy as np
from PIL import Image, ImageDraw, ImageFont

ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(ROOT / "software" / "ai"))
sys.path.insert(0, str(Path(__file__).resolve().parent))
from dataset.pairs import load_rgb  # noqa: E402
from srim import read_srim  # noqa: E402

FONT = "/usr/share/fonts/truetype/dejavu/DejaVuSans-Bold.ttf"


def load_any(path):
    return read_srim(path) if str(path).endswith(".raw") else load_rgb(path)


def font(size):
    try:
        return ImageFont.truetype(FONT, size)
    except OSError:
        return ImageFont.load_default()


def main(argv):
    if len(argv) not in (4, 5):
        sys.exit(__doc__)
    lr, sr = load_any(argv[1]), load_any(argv[2])
    if sr.shape[0] != 2 * lr.shape[0] or sr.shape[1] != 2 * lr.shape[1]:
        sys.exit(f"output {sr.shape[1]}x{sr.shape[0]} is not 2x the input {lr.shape[1]}x{lr.shape[0]}")
    up = np.repeat(np.repeat(lr, 2, axis=0), 2, axis=1)
    h, w = sr.shape[:2]
    gap, bar = 16, 56
    top = bar if len(argv) == 5 else 0
    canvas = Image.new("RGB", (2 * w + gap, h + bar + top), "white")
    canvas.paste(Image.fromarray(up), (0, top + bar))
    canvas.paste(Image.fromarray(sr), (w + gap, top + bar))
    d = ImageDraw.Draw(canvas)
    f = font(32)
    if top:
        d.text((10, 10), argv[4], fill="black", font=f)
    d.text((10, top + 10), f"INPUT {lr.shape[1]}x{lr.shape[0]} (pixels shown 2x)", fill="black", font=f)
    d.text((w + gap + 10, top + 10), f"FPGA OUTPUT {w}x{h} (CNN x2 on the ZedBoard)", fill="black", font=f)
    canvas.save(argv[3])
    print(f"wrote {argv[3]} ({canvas.size[0]}x{canvas.size[1]})")


if __name__ == "__main__":
    main(sys.argv)
