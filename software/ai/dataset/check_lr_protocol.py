"""Verify our LR generation against the official benchmark LR files.

* Images with even sides: our LR must be bit-identical to the official LR.
* Images with an odd side: official LR comes from the uncropped HR (scale != 2 exactly, misaligned). We only check
  that the LR *shape* agrees; the pixels intentionally differ.

Run from the project root:  .venv/bin/python software/ai/dataset/check_lr_protocol.py
"""
import sys
from pathlib import Path

import numpy as np

ROOT = Path(__file__).resolve().parents[3]
sys.path.insert(0, str(ROOT / "software" / "ai"))
from dataset.pairs import list_images, load_rgb, make_pair  # noqa: E402

SETS = ["Set5", "Set14", "BSD100"]


def main():
    for s in SETS:
        even = even_exact = odd = 0
        for hr_path in list_images(ROOT / "data" / "test" / "HR" / s):
            hr_full = load_rgb(hr_path)
            off = load_rgb(ROOT / "data" / "test" / "LR_official" / s / hr_path.name)
            lr, _ = make_pair(hr_full, 2)
            assert lr.shape == off.shape, (hr_path.name, lr.shape, off.shape)
            if hr_full.shape[0] % 2 == 0 and hr_full.shape[1] % 2 == 0:
                even += 1
                even_exact += int(np.array_equal(lr, off))
            else:
                odd += 1
        print(f"{s:7} even-sized: {even_exact}/{even} bit-exact | odd-sized (intentionally re-aligned): {odd}")
        assert even_exact == even, f"{s}: LR protocol does not reproduce official LR for even-sized images"
    print("OK: LR protocol reproduces the official LR files exactly wherever they are well-defined")


if __name__ == "__main__":
    main()
