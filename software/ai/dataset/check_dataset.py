"""Dataset sanity checks (M1 exit item): files decode, sizes are sane, train and test never overlap.

Run from the project root:  .venv/bin/python software/ai/dataset/check_dataset.py
"""
import hashlib
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[3]
sys.path.insert(0, str(ROOT / "software" / "ai"))
from dataset.pairs import list_images, load_rgb  # noqa: E402

MIN_SIDE = 64


def scan(folder: Path):
    out = {}
    for p in list_images(folder) if folder.exists() else []:
        img = load_rgb(p)
        assert img.ndim == 3 and img.shape[2] == 3, p
        assert min(img.shape[:2]) >= MIN_SIDE, f"too small: {p}"
        out[p] = (img.shape, hashlib.sha256(img.tobytes()).hexdigest())
    return out


def main():
    train = scan(ROOT / "data" / "train" / "HR")
    test = {}
    for d in sorted((ROOT / "data" / "test" / "HR").iterdir()):
        if d.is_dir():
            test.update(scan(d))
    print(f"train images: {len(train)}   test images: {len(test)}")
    assert train and test, "empty dataset"
    shapes = [s for s, _ in train.values()]
    print("train size range: min", min(min(s[:2]) for s in shapes), "px short side;",
          "max", max(max(s[:2]) for s in shapes), "px long side")
    th = {h for _, h in train.values()}
    assert len(th) == len(train), "duplicate images inside train"
    overlap = th & {h for _, h in test.values()}
    assert not overlap, f"{len(overlap)} identical images in train AND test"
    # test LR files must exist for every test HR
    missing = [p for p in test if not (ROOT / "data" / "test" / "LR" / p.parent.name / p.name).exists()]
    assert not missing, f"missing LR for {len(missing)} test images"
    print("OK: all files decode, no duplicates, no train/test overlap, all test LR present")


if __name__ == "__main__":
    main()
