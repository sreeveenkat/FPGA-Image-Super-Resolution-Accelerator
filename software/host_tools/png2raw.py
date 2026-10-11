"""PNG -> SRIM raw (format: see srim.py).   .venv/bin/python software/host_tools/png2raw.py in.png out.raw"""
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(ROOT / "software" / "ai"))
sys.path.insert(0, str(Path(__file__).resolve().parent))
from dataset.pairs import load_rgb  # noqa: E402
from srim import write_srim  # noqa: E402

if __name__ == "__main__":
    if len(sys.argv) != 3:
        sys.exit(__doc__)
    img = load_rgb(sys.argv[1])
    write_srim(sys.argv[2], img)
    print(f"{sys.argv[1]} -> {sys.argv[2]}: {img.shape[1]}x{img.shape[0]} RGB, {16 + img.size} bytes")
