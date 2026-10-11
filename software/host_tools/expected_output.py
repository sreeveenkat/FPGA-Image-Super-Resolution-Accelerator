"""Expected board output = the INTEGER golden model on the whole image (software/ai/quantization/integer_reference.upscale).

    .venv/bin/python software/host_tools/expected_output.py <lr.png | lr.raw> <out_prefix>
writes <out_prefix>.png and <out_prefix>.raw (SRIM, 2W x 2H).  The board result must be byte-identical to <out_prefix>.raw (compare_raw.py).
"""
import sys
import time
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(ROOT / "software" / "ai"))
sys.path.insert(0, str(Path(__file__).resolve().parent))
from dataset.pairs import load_rgb, save_rgb  # noqa: E402
from quantization.integer_reference import QNet, upscale  # noqa: E402
from srim import read_srim, write_srim  # noqa: E402

QPARAMS = ROOT / "software" / "ai" / "quantization" / "qparams.npz"


def load_any(path):
    return read_srim(path) if str(path).endswith(".raw") else load_rgb(path)


if __name__ == "__main__":
    if len(sys.argv) != 3:
        sys.exit(__doc__)
    lr = load_any(sys.argv[1])
    t = time.time()
    out = upscale(QNet.load(QPARAMS), lr)
    save_rgb(sys.argv[2] + ".png", out)
    write_srim(sys.argv[2] + ".raw", out)
    print(f"{sys.argv[1]} ({lr.shape[1]}x{lr.shape[0]}) -> {sys.argv[2]}.png/.raw ({out.shape[1]}x{out.shape[0]}), integer model {time.time() - t:.1f} s")
