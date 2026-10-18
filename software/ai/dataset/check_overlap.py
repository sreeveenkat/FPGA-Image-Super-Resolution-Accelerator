"""Check that Set5 / Set14 / BSD100 (and the DIV2K validation split) share no image with ANY training source, old or new.

Training sources checked: data/train/HR (the 192 DIV2K images of the deployed model, 180 trained + 12 old validation),
the DIV2K train set (800, parquet) and Flickr2K (2650, zip) behind the new crop store.
Three tests, all on whole source images:
  1. exact: md5 of the decoded pixels (also of the 8 flips/rotations of the test image);
  2. near-duplicate of the whole image (resized, re-compressed, flipped, rotated): 32x32 grey thumbnail, correlation > 0.95 with any of the 8 dihedral variants;
  3. test image contained as a (sub-)region of a training image at the same scale or after a 2x resize: normalised cross-correlation
     template matching at 1/8 scale (the test image at 1/8 and 1/16 is searched in the training image at 1/8); templates smaller than 24 px or
     almost flat are skipped (they match anything); score > 0.97 is flagged AND must be confirmed at 1/2 and 1/4 scale with score > 0.99 (a true copy does; a flat bright/dark area does not).
Limits (stated, not hidden): test 3 does not find crops that were also rotated or resized by an arbitrary factor, and the store crops themselves
are not searched (they come from the source images above, and the source image is what is compared).

Run from the project root:  .venv/bin/python software/ai/dataset/check_overlap.py  -> results/quality/train_test_overlap.md
"""
import hashlib
import json
import sys
import zipfile
from multiprocessing import Pool
from pathlib import Path

import cv2
import numpy as np

ROOT = Path(__file__).resolve().parents[3]
sys.path.insert(0, str(ROOT / "software" / "ai"))
from dataset.pairs import list_images, load_rgb  # noqa: E402
from dataset.prepare_extra import RAW, sources_div2k  # noqa: E402

cv2.setNumThreads(1)
SETS = ["Set5", "Set14", "BSD100"]


def md5(a):
    return hashlib.md5(np.ascontiguousarray(a).tobytes()).hexdigest()


def dihedral(a):
    out = []
    for k in range(4):
        r = np.rot90(a, k)
        out += [r, r[:, ::-1]]
    return out


def thumb(rgb):
    g = cv2.cvtColor(rgb, cv2.COLOR_RGB2GRAY)
    t = cv2.resize(g, (32, 32), interpolation=cv2.INTER_AREA).astype(np.float32).ravel()
    t -= t.mean()
    return t / (np.linalg.norm(t) + 1e-9)


def small(rgb, f):
    g = cv2.cvtColor(rgb, cv2.COLOR_RGB2GRAY)
    return cv2.resize(g, (max(1, round(g.shape[1] * f)), max(1, round(g.shape[0] * f))), interpolation=cv2.INTER_AREA)


def load_tests():
    tests = []
    for s in SETS:
        for p in list_images(ROOT / "data" / "test" / "HR" / s):
            tests.append((f"{s}/{p.stem}", load_rgb(p)))
    split = json.loads((ROOT / "data" / "train_extra" / "valid_split.json").read_text())["val42"]
    for n in split:
        tests.append((f"val42/{n}", load_rgb(ROOT / "data" / "train_extra" / "valid_HR" / n)))
    return tests


G = {}


def init(tests):
    G["names"] = [n for n, _ in tests]
    G["imgs"] = [im for _, im in tests]
    G["md5"] = {}
    for n, im in tests:
        for v in dihedral(im):
            G["md5"][md5(v)] = n
    G["thumbs"] = np.stack([np.stack([thumb(v) for v in dihedral(im)]) for _, im in tests])  # (T, 8, 1024)
    # templates: test image at 1/8, 1/4 and 1/2 of the scale of the (1/8-scaled) training image, i.e. training image = 1x, 2x, 4x bigger
    G["tpl"] = [[small(im, f) for f in (1 / 8, 1 / 16)] for _, im in tests]


def work(job):
    src, data = job
    img = cv2.imdecode(np.frombuffer(data, np.uint8), cv2.IMREAD_COLOR)
    if img is None:
        return src, None
    rgb = cv2.cvtColor(img, cv2.COLOR_BGR2RGB)
    res = {"src": src, "shape": rgb.shape[:2], "exact": G["md5"].get(md5(rgb))}
    t = thumb(rgb)
    cor = G["thumbs"] @ t  # (T, 8)
    ti = int(np.argmax(cor.max(1)))
    res["thumb"] = (G["names"][ti], float(cor[ti].max()))
    base = small(rgb, 1 / 8)
    best = (None, -1.0)
    for i, tpls in enumerate(G["tpl"]):
        for tp in tpls:
            if tp.shape[0] < 24 or tp.shape[1] < 24 or tp.shape[0] > base.shape[0] or tp.shape[1] > base.shape[1]:
                continue
            if tp.std() < 8.0:  # flat template: normalised correlation meaningless
                continue
            sc = float(cv2.matchTemplate(base, tp, cv2.TM_CCOEFF_NORMED).max())
            if sc > best[1]:
                best = (G["names"][i], sc)
    if best[1] > 0.97:  # confirm at 1/2 scale: a real copy scores > 0.99 at the finer scale, a flat-area false match does not
        i = G["names"].index(best[0])
        fine = 0.0
        for f in (1 / 2, 1 / 4):
            for g in (1.0, 0.5):
                tp, bs = small(G["imgs"][i], f * g), small(rgb, f)
                if tp.shape[0] <= bs.shape[0] and tp.shape[1] <= bs.shape[1] and tp.std() > 8.0:
                    fine = max(fine, float(cv2.matchTemplate(bs, tp, cv2.TM_CCOEFF_NORMED).max()))
        res["tm_fine"] = fine
        best = (best[0], best[1] if fine > 0.99 else 0.0)  # only a confirmed match keeps its score
    res["tm"] = best
    return src, res


def sources():
    for i, p in enumerate(list_images(ROOT / "data" / "train" / "HR")):
        yield f"old_{'trained' if i < 180 else 'heldout'}/{p.name}", p.read_bytes()
    for i, d in enumerate(sources_div2k()):
        yield f"div2k_train/{i}", d
    with zipfile.ZipFile(RAW / "Flickr2K.zip") as z:
        for name in sorted(z.namelist()):
            if name.lower().endswith((".png", ".jpg", ".jpeg")):
                yield f"flickr2k/{Path(name).name}", z.read(name)


def main():
    tests = load_tests()
    print(f"{len(tests)} test/validation images", flush=True)
    rows, n = [], 0
    with Pool(2, initializer=init, initargs=(tests,)) as pool:
        for src, r in pool.imap_unordered(work, sources(), chunksize=2):
            n += 1
            if r is not None:
                rows.append(r)
            if n % 250 == 0:
                print(f"  {n} training images compared", flush=True)
    # old_heldout = the 12 images the deployed model never trained on (its old validation set): they ARE in val42 on purpose
    ok = lambda r: r["src"].startswith("old_heldout/") and r["thumb"][0].startswith("val42/")  # noqa: E731
    exact = [r for r in rows if r["exact"] and not ok(r)]
    expected = [r for r in rows if r["exact"] and ok(r)]
    th = sorted((r for r in rows if not ok(r)), key=lambda r: -r["thumb"][1])[:5]
    tm = sorted((r for r in rows if not ok(r)), key=lambda r: -r["tm"][1])[:5]
    th_hits = [r for r in rows if r["thumb"][1] > 0.95 and not ok(r)]
    tm_hits = [r for r in rows if r["tm"][1] > 0.97 and not ok(r)]
    lines = ["# Train / test overlap check", "",
             f"Compared {len(rows)} training source images (old deployed training set data/train/HR: 192, DIV2K train: 800, Flickr2K: 2650) "
             f"against {len(tests)} test and validation images (Set5, Set14, BSD100, and the 42 DIV2K validation images).", "",
             f"* expected: {len(expected)} held-out images of the deployed model's old validation set (data/train/HR #181-192) are part of val42 on purpose "
             "and are in NO training set (the new store excludes them by md5)",
             f"* exact pixel match (incl. flips/rotations), unexpected: **{len(exact)}**" + "".join(f"  ({r['src']} == {r['exact']})" for r in exact),
             f"* whole-image near duplicate (thumbnail correlation > 0.95, 8 dihedral variants): **{len(th_hits)}**",
             f"* contained as a region (template matching at 1/8 scale, score > 0.97): **{len(tm_hits)}**", "",
             "Closest candidates (highest scores found; below the thresholds they are different images):", "",
             "| test | training image | thumbnail corr. |", "|---|---|---|"]
    lines += [f"| {r['thumb'][0]} | {r['src']} | {r['thumb'][1]:.3f} |" for r in th]
    lines += ["", "| test | training image | template score |", "|---|---|---|"]
    lines += [f"| {r['tm'][0]} | {r['src']} | {r['tm'][1]:.3f} |" for r in tm]
    lines += ["", "Hits above threshold (empty = none):", ""] + [f"* {r['src']}: thumb {r['thumb']}, template {r['tm']}" for r in th_hits + tm_hits]
    lines += ["", "Limits: crops that were also rotated or resized by an arbitrary factor are not found by the template test; the store crops are not searched "
              "directly (they are cut from the source images compared here). Saved by software/ai/dataset/check_overlap.py."]
    out = ROOT / "results" / "quality" / "train_test_overlap.md"
    out.write_text("\n".join(lines) + "\n")
    print("\n".join(lines))
    sys.exit(1 if (exact or th_hits or tm_hits) else 0)


if __name__ == "__main__":
    main()
