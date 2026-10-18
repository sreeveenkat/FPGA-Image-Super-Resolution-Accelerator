"""Build the extra training store for the image-quality retraining: aligned LR/HR crops from the full DIV2K train set (800 images) and
Flickr2K (2650 images), as two uint8 memory-mappable arrays.  Run from the project root:

  .venv/bin/python software/ai/dataset/prepare_extra.py div2k  [--per-image 8]     # data/train_extra/raw/div2k_*.parquet
  .venv/bin/python software/ai/dataset/prepare_extra.py flickr [--per-image 6]     # data/train_extra/raw/Flickr2K.zip
  .venv/bin/python software/ai/dataset/prepare_extra.py merge div2k flickr         # -> data/train_extra/store/{lr,hr}.npy

LR protocol is the project's (dataset/pairs.py): modcrop, Pillow BICUBIC downscale of the WHOLE image, then an LR crop of 128x128 at a
random position and the matching HR crop of 256x256 (exactly aligned, so no border artefacts from cropping before downscaling).
The 12 validation images (data/train/HR, last 12 of the first 192) are recognised by the md5 of their pixels and skipped, so the
store never contains a validation image; the 3 test sets are different images (checked by the md5 of the pixels as well).
"""
import argparse
import glob
import hashlib
import io
import sys
import zipfile
from multiprocessing import Pool
from pathlib import Path

import cv2
import numpy as np

ROOT = Path(__file__).resolve().parents[3]
sys.path.insert(0, str(ROOT / "software" / "ai"))
from dataset.pairs import list_images, load_rgb, make_pair  # noqa: E402

RAW = ROOT / "data" / "train_extra" / "raw"
STORE = ROOT / "data" / "train_extra" / "store"
LRC, S = 128, 2


def md5(a: np.ndarray) -> str:
    return hashlib.md5(np.ascontiguousarray(a).tobytes()).hexdigest()


def forbidden_hashes():
    """md5 of the pixels of the 12 validation images and of every test HR image."""
    h = {}
    for p in list_images(ROOT / "data" / "train" / "HR")[:192][-12:]:
        h[md5(load_rgb(p))] = f"val:{p.name}"
    for p in list_images(ROOT / "data" / "train_extra" / "valid_HR") if (ROOT / "data" / "train_extra" / "valid_HR").exists() else []:
        h[md5(load_rgb(p))] = f"valid:{p.name}"  # all 100 DIV2K valid images (801-900) stay out of every training store
    for d in (ROOT / "data" / "test" / "HR").glob("*"):
        if d.is_dir():
            for p in list_images(d):
                h[md5(load_rgb(p))] = f"test:{d.name}/{p.name}"
    return h


def work(job):
    """job = (index, png/jpg bytes, crops per image, seed, forbidden dict) -> (index, lr crops, hr crops, status)."""
    idx, data, n, seed, forb = job
    img = cv2.imdecode(np.frombuffer(data, np.uint8), cv2.IMREAD_COLOR)
    if img is None:
        return idx, None, None, "undecodable"
    rgb = cv2.cvtColor(img, cv2.COLOR_BGR2RGB)
    key = md5(rgb)
    if key in forb:
        return idx, None, None, "skipped " + forb[key]
    lr, hr = make_pair(rgb, S)
    h, w = lr.shape[:2]
    if h < LRC or w < LRC:
        return idx, None, None, "too small"
    rng = np.random.default_rng(seed * 100003 + idx)
    L = np.empty((n, LRC, LRC, 3), np.uint8)
    H = np.empty((n, LRC * S, LRC * S, 3), np.uint8)
    for i in range(n):
        y, x = int(rng.integers(0, h - LRC + 1)), int(rng.integers(0, w - LRC + 1))
        L[i] = lr[y:y + LRC, x:x + LRC]
        H[i] = hr[y * S:(y + LRC) * S, x * S:(x + LRC) * S]
    return idx, L, H, "ok"


def sources_div2k():
    import pyarrow.parquet as pq
    for f in sorted(glob.glob(str(RAW / "div2k_*.parquet"))):
        pf = pq.ParquetFile(f)
        for b in pf.iter_batches(batch_size=4):
            col = b.column(0).to_pylist()  # the only column is the image struct {bytes, path}
            for item in col:
                yield item["bytes"]


def sources_flickr():
    with zipfile.ZipFile(RAW / "Flickr2K.zip") as z:
        for name in sorted(z.namelist()):
            if name.lower().endswith((".png", ".jpg", ".jpeg")):
                yield z.read(name)


def build(kind, per_image, seed):
    forb = forbidden_hashes()
    print(f"{len(forb)} forbidden hashes (validation + test images)", flush=True)
    src = sources_div2k() if kind == "div2k" else sources_flickr()
    STORE.mkdir(parents=True, exist_ok=True)
    tmp_l, tmp_h = STORE / f"{kind}_lr.part", STORE / f"{kind}_hr.part"
    n_ok = skipped = bad = 0
    with Pool(6) as pool, open(tmp_l, "wb") as fl, open(tmp_h, "wb") as fh:
        jobs = ((i, d, per_image, seed, forb) for i, d in enumerate(src))
        for idx, L, H, st in pool.imap(work, jobs, chunksize=2):
            if st == "ok":
                fl.write(L.tobytes()); fh.write(H.tobytes()); n_ok += 1
            elif st.startswith("skipped"):
                skipped += 1; print(f"  image {idx}: {st}", flush=True)
            else:
                bad += 1; print(f"  image {idx}: {st}", flush=True)
            if (idx + 1) % 100 == 0:
                print(f"  {idx + 1} images processed", flush=True)
    n = n_ok * per_image
    for tmp, shape, name in ((tmp_l, (n, LRC, LRC, 3), "lr"), (tmp_h, (n, LRC * S, LRC * S, 3), "hr")):
        a = np.memmap(tmp, np.uint8, "r", shape=shape)
        out = np.lib.format.open_memmap(STORE / f"{kind}_{name}.npy", "w+", np.uint8, shape)
        for i in range(0, n, 512):
            out[i:i + 512] = a[i:i + 512]
        out.flush(); del out, a
        tmp.unlink()
    print(f"{kind}: {n_ok} images used, {skipped} skipped (validation/test), {bad} unusable -> {n} crops", flush=True)


def merge(kinds):
    ls = [np.load(STORE / f"{k}_lr.npy", mmap_mode="r") for k in kinds]
    hs = [np.load(STORE / f"{k}_hr.npy", mmap_mode="r") for k in kinds]
    n = sum(len(a) for a in ls)
    rng = np.random.default_rng(0)
    perm = rng.permutation(n)  # shuffled, so --max-crops takes a random subset of every source
    out_l = np.lib.format.open_memmap(STORE / "lr.npy", "w+", np.uint8, (n, LRC, LRC, 3))
    out_h = np.lib.format.open_memmap(STORE / "hr.npy", "w+", np.uint8, (n, LRC * S, LRC * S, 3))
    base = np.cumsum([0] + [len(a) for a in ls])
    for start in range(0, n, 512):
        ids = np.sort(perm[start:start + 512])
        for j in range(len(ls)):
            sel = ids[(ids >= base[j]) & (ids < base[j + 1])] - base[j]
            pos = np.nonzero((ids >= base[j]) & (ids < base[j + 1]))[0] + start
            if len(sel):
                out_l[pos], out_h[pos] = ls[j][sel], hs[j][sel]
    out_l.flush(); out_h.flush()
    print(f"merged {kinds}: {n} crops -> {STORE}/lr.npy, hr.npy")


if __name__ == "__main__":
    ap = argparse.ArgumentParser()
    ap.add_argument("what", choices=["div2k", "flickr", "merge"])
    ap.add_argument("kinds", nargs="*")
    ap.add_argument("--per-image", type=int, default=0)
    a = ap.parse_args()
    if a.what == "merge":
        merge(a.kinds)
    else:
        build(a.what, a.per_image or (8 if a.what == "div2k" else 6), 1 if a.what == "div2k" else 2)
