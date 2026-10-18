"""Validation split used for ALL model selection (checkpoint choice, QAT early-stopping, learning-rate sweeps).

DIV2K valid HR (images 801-900, data/train_extra/valid_HR) minus the 58 of them that the ORIGINAL baseline (software/ai/checkpoints/srnet_fp32.pt)
was trained on (they sit in data/train/HR as img0315..img0384 with the old 12 validation images).  What is left, 42 images, was seen by NO model in the
project (the new models train on DIV2K train 1-800 + Flickr2K only), so it is a clean split for every rung, the baseline included.
The 12 old validation images are a subset of the 42.

  .venv/bin/python software/ai/dataset/valsplit.py        # (re)writes data/train_extra/valid_split.json and checks it
"""
import json
import sys
from pathlib import Path

import cv2
import numpy as np

ROOT = Path(__file__).resolve().parents[3]
sys.path.insert(0, str(ROOT / "software" / "ai"))
from dataset.pairs import list_images, load_rgb, make_pair  # noqa: E402

VALID_DIR = ROOT / "data" / "train_extra" / "valid_HR"
SPLIT = ROOT / "data" / "train_extra" / "valid_split.json"


def _sig(rgb):
    return rgb.shape[:2], cv2.resize(rgb, (16, 16), interpolation=cv2.INTER_AREA).astype(np.float32)


def build():
    valid = {p.name: _sig(load_rgb(p)) for p in list_images(VALID_DIR)}
    old = list_images(ROOT / "data" / "train" / "HR")[:192]
    sig = {p.name: _sig(load_rgb(p)) for p in old}  # each old image is loaded ONCE
    old_train, old_val = [sig[p.name] for p in old[:180]], [sig[p.name] for p in old[180:]]

    def matches(v, group):
        vs, vf = valid[v]
        return any(os_ == vs and np.abs(of - vf).mean() < 0.5 for os_, of in group)

    trained_on = sorted(v for v in valid if matches(v, old_train))
    old12 = sorted(v for v in valid if matches(v, old_val))
    clean = sorted(set(valid) - set(trained_on))
    assert len(valid) == 100 and len(old12) == 12 and set(old12) <= set(clean), (len(valid), len(old12))
    SPLIT.write_text(json.dumps({"val42": clean, "baseline_trained_on": trained_on, "old_val12": old12, "val100": sorted(valid)}, indent=1))
    print(f"valid 100 = {len(trained_on)} used by the baseline's training + {len(clean)} clean (incl. the {len(old12)} old validation images)")


def load_val_pairs(which="val42"):
    names = json.loads(SPLIT.read_text())[which]
    return [make_pair(load_rgb(VALID_DIR / n), 2) for n in names]


if __name__ == "__main__":
    build()
