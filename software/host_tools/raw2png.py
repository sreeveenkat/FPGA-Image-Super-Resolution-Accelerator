"""SRIM raw -> PNG (format: see srim.py).   .venv/bin/python software/host_tools/raw2png.py in.raw out.png"""
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(ROOT / "software" / "ai"))
sys.path.insert(0, str(Path(__file__).resolve().parent))
from dataset.pairs import save_rgb  # noqa: E402
from srim import read_srim  # noqa: E402

if __name__ == "__main__":
    if len(sys.argv) != 3:
        sys.exit(__doc__)
    img = read_srim(sys.argv[1])
    save_rgb(sys.argv[2], img)
    print(f"{sys.argv[1]} -> {sys.argv[2]}: {img.shape[1]}x{img.shape[0]} RGB")
