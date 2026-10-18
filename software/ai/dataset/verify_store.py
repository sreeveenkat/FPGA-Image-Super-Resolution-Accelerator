"""Verify a crop store written by prepare_extra.py.  Run from the project root:
  .venv/bin/python software/ai/dataset/verify_store.py div2k            # full: every crop recomputed from the source and compared
  .venv/bin/python software/ai/dataset/verify_store.py flickr --sample 0.1   # zip CRC test + recompute a random 10 % of the images
  .venv/bin/python software/ai/dataset/verify_store.py merged            # lr.npy / hr.npy: sizes, no empty crops, every crop found in a source store

Checks: array shapes / dtype / file size, no all-zero (never written) crop, the crops of every image equal a fresh recomputation from the source
bytes (same seeds, so bit-identical), and md5 of the finished arrays written to data/train_extra/store/MANIFEST.txt.
Exit code 1 on any mismatch.
"""
import argparse
import hashlib
import sys
import zipfile
from multiprocessing import Pool
from pathlib import Path

import numpy as np

ROOT = Path(__file__).resolve().parents[3]
sys.path.insert(0, str(ROOT / "software" / "ai"))
from dataset import prepare_extra as P  # noqa: E402


def md5_file(path):
    h = hashlib.md5()
    with open(path, "rb") as f:
        for blk in iter(lambda: f.read(1 << 24), b""):
            h.update(blk)
    return h.hexdigest()


def recompute(job):
    idx, data, n, seed, forb, lr_path, hr_path, base = job
    _, L, H, st = P.work((idx, data, n, seed, forb))
    if st != "ok":
        return idx, st, 0
    lr = np.load(lr_path, mmap_mode="r")[base:base + n]
    hr = np.load(hr_path, mmap_mode="r")[base:base + n]
    return idx, st, int(not (np.array_equal(L, lr) and np.array_equal(H, hr)))


def check_arrays(lr_path, hr_path):
    lr, hr = np.load(lr_path, mmap_mode="r"), np.load(hr_path, mmap_mode="r")
    ok = lr.dtype == np.uint8 and hr.dtype == np.uint8 and len(lr) == len(hr) and lr.shape[1:] == (128, 128, 3) and hr.shape[1:] == (256, 256, 3)
    empty = []
    for i in range(0, len(lr), 256):  # an all-zero crop is either genuinely black content or a crop that was never written
        z = (lr[i:i + 256].reshape(len(lr[i:i + 256]), -1).max(1) == 0) | (hr[i:i + 256].reshape(len(hr[i:i + 256]), -1).max(1) == 0)
        empty += [int(i + j) for j in np.nonzero(z)[0]]
    expect = 128 + len(lr) * 128 * 128 * 3
    size_ok = Path(lr_path).stat().st_size - expect < 1024 and Path(lr_path).stat().st_size >= len(lr) * 128 * 128 * 3
    print(f"  {Path(lr_path).name}: {len(lr)} crops, shapes/dtype {'OK' if ok else 'BAD'}, file size {'OK' if size_ok else 'BAD'}, all-zero crops: {len(empty)} (their source images are recomputed below)")
    return ok and size_ok, len(lr), empty


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("kind", choices=["div2k", "flickr", "merged"])
    ap.add_argument("--sample", type=float, default=1.0, help="fraction of images to recompute (flickr)")
    ap.add_argument("--per-image", type=int, default=0)
    a = ap.parse_args()
    ok = True
    if a.kind == "merged":
        ok, n, empty = check_arrays(P.STORE / "lr.npy", P.STORE / "hr.npy")
        ok &= not empty or True  # merged: black crops are accepted when found in a source store (checked below)
        # every merged (LR, HR) PAIR must equal a pair of one source store: LR md5 -> candidate (store, index); HR must match one of them
        src, srcs = {}, {}
        for k in ("div2k", "flickr"):
            if (P.STORE / f"{k}_lr.npy").exists():
                srcs[k] = (np.load(P.STORE / f"{k}_lr.npy", mmap_mode="r"), np.load(P.STORE / f"{k}_hr.npy", mmap_mode="r"))
                for i, c in enumerate(srcs[k][0]):
                    src.setdefault(hashlib.md5(np.ascontiguousarray(c).tobytes()).digest(), []).append((k, i))
        mlr, mhr = np.load(P.STORE / "lr.npy", mmap_mode="r"), np.load(P.STORE / "hr.npy", mmap_mode="r")
        miss = unpaired = 0
        used = set()
        for i in range(len(mlr)):
            cands = src.get(hashlib.md5(np.ascontiguousarray(mlr[i]).tobytes()).digest())
            if not cands:
                miss += 1
            elif not any(np.array_equal(mhr[i], srcs[k][1][j]) for k, j in cands):
                unpaired += 1
            else:
                used.add(min(c for c in cands if np.array_equal(mhr[i], srcs[c[0]][1][c[1]])))
        total = sum(len(v[0]) for v in srcs.values())
        print(f"  merged crops not found in a source store: {miss}; found but HR does not belong to that LR: {unpaired}; "
              f"distinct source crops used: {len(used)} of {total}")
        ok &= unpaired == 0 and len(mlr) == total
        ok &= miss == 0
    else:
        per = a.per_image or (8 if a.kind == "div2k" else 6)
        seed = 1 if a.kind == "div2k" else 2
        lr_path, hr_path = P.STORE / f"{a.kind}_lr.npy", P.STORE / f"{a.kind}_hr.npy"
        ok, n, empty = check_arrays(lr_path, hr_path)
        must = {c // per for c in empty}  # images that own an all-zero crop are always recomputed
        if a.kind == "flickr":
            with zipfile.ZipFile(P.RAW / "Flickr2K.zip") as z:
                bad = z.testzip()
            print(f"  zip CRC test: {'OK' if bad is None else 'BAD member ' + bad}")
            ok &= bad is None
        forb = P.forbidden_hashes()
        rng = np.random.default_rng(0)
        src = P.sources_div2k() if a.kind == "div2k" else P.sources_flickr()
        jobs = []
        for i, d in enumerate(src):
            if a.sample >= 1.0 or i in must or rng.random() < a.sample:
                jobs.append((i, d, per, seed, forb, lr_path, hr_path, i * per))
        with Pool(6) as pool:
            res = list(pool.imap(recompute, jobs, chunksize=2))
        bad = [r for r in res if r[2] or r[1] != "ok"]
        print(f"  recomputed {len(res)} images from the source: {len(bad)} differ / not ok  (expected crops = images x {per} = {n if a.sample >= 1.0 else '-'})")
        ok &= not bad
        if a.sample >= 1.0:
            ok &= len(res) * per == n
        man = P.STORE / "MANIFEST.txt"
        lines = [l for l in (man.read_text().splitlines() if man.exists() else []) if not l.startswith(a.kind + "_")]
        lines += [f"{a.kind}_lr.npy md5 {md5_file(lr_path)} crops {n}", f"{a.kind}_hr.npy md5 {md5_file(hr_path)} crops {n}"]
        man.write_text("\n".join(lines) + "\n")
        print("  manifest updated:", man)
    print("RESULT:", "STORE OK" if ok else "STORE BROKEN")
    sys.exit(0 if ok else 1)


if __name__ == "__main__":
    main()
