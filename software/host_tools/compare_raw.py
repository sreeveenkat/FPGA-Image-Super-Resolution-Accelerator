"""Compare two SRIM raw images (board output vs expected output).

    .venv/bin/python software/host_tools/compare_raw.py board.raw expected.raw [diff.png]
Prints: byte-exact yes/no, number of mismatching bytes, first 10 mismatches as (x, y, c, got, expected), max abs diff, FNV-1a 32 of both payloads
(the board prints the same checksum for its output).  If anything differs a diff image is written (|got - expected| x 16, clamped; default <board>_diff.png).
Exit code 0 = byte-exact, 1 = different, 2 = unreadable / size mismatch.
"""
import sys
from pathlib import Path

import numpy as np

ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(ROOT / "software" / "ai"))
sys.path.insert(0, str(Path(__file__).resolve().parent))
from dataset.pairs import save_rgb  # noqa: E402
from srim import fnv1a32, read_srim  # noqa: E402


def main(argv):
    if len(argv) not in (3, 4):
        print(__doc__)
        return 2
    try:
        got, exp = read_srim(argv[1]), read_srim(argv[2])
    except (ValueError, OSError) as e:
        print("ERROR:", e)
        return 2
    print(f"board   : {argv[1]}  {got.shape[1]}x{got.shape[0]}  fnv1a32 0x{fnv1a32(got.tobytes()):08x}")
    print(f"expected: {argv[2]}  {exp.shape[1]}x{exp.shape[0]}  fnv1a32 0x{fnv1a32(exp.tobytes()):08x}")
    if got.shape != exp.shape:
        print(f"ERROR: size differs ({got.shape[1]}x{got.shape[0]} vs {exp.shape[1]}x{exp.shape[0]})")
        return 2
    diff = got.astype(np.int16) - exp.astype(np.int16)
    bad = diff != 0
    n = int(bad.sum())
    if n == 0:
        print(f"BYTE-EXACT: yes ({got.size} bytes identical)")
        return 0
    ys, xs, cs = np.nonzero(bad)
    print(f"BYTE-EXACT: NO - {n} of {got.size} bytes differ ({100.0 * n / got.size:.4f} %), pixels affected {int(bad.any(axis=2).sum())}, max abs diff {int(np.abs(diff).max())}")
    print("first mismatches (x, y, c, got, expected):")
    for i in range(min(10, n)):
        print(f"  ({xs[i]}, {ys[i]}, {cs[i]}, {got[ys[i], xs[i], cs[i]]}, {exp[ys[i], xs[i], cs[i]]})")
    out = argv[3] if len(argv) == 4 else str(Path(argv[1]).with_suffix("")) + "_diff.png"
    save_rgb(out, np.clip(np.abs(diff) * 16, 0, 255).astype(np.uint8))
    print("diff image:", out)
    return 1


if __name__ == "__main__":
    sys.exit(main(sys.argv))
