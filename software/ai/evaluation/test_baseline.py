"""Tests for M1. Run: .venv/bin/python software/ai/evaluation/test_baseline.py"""
import csv
import sys
from pathlib import Path

import numpy as np

ROOT = Path(__file__).resolve().parents[3]
sys.path.insert(0, str(ROOT / "software" / "ai"))
from dataset.pairs import downscale_pil, list_images, load_rgb, make_pair, modcrop, save_rgb, upscale_pil  # noqa: E402
from evaluation.metrics import psnr_rgb, psnr_y, rgb_to_y, ssim_rgb, ssim_y  # noqa: E402


class Skip(Exception):
    pass


def need(path):
    if not Path(path).exists():
        raise Skip(f"missing {Path(path).relative_to(ROOT)} (download the datasets, see data/README.md)")


def rnd(shape, seed=0):
    return np.random.default_rng(seed).integers(0, 256, shape, dtype=np.uint8)


def test_identical_images():
    img = rnd((32, 32, 3))
    assert psnr_rgb(img, img) == float("inf")
    assert abs(ssim_rgb(img, img) - 1.0) < 1e-9 and abs(ssim_y(img, img, 2) - 1.0) < 1e-9


def test_known_mse():
    a, b = np.full((32, 32, 3), 100, np.uint8), np.full((32, 32, 3), 110, np.uint8)
    assert abs(psnr_rgb(a, b) - 10 * np.log10(255**2 / 100)) < 1e-9


def test_y_conversion_known_values():
    assert abs(rgb_to_y(np.zeros((1, 1, 3), np.uint8))[0, 0] - 16.0) < 1e-9
    assert abs(rgb_to_y(np.full((1, 1, 3), 255, np.uint8))[0, 0] - 235.0) < 1e-6


def test_y_conversion_distinguishes_r_g_b():
    for rgb, expect in [((255, 0, 0), 16 + 65.481), ((0, 255, 0), 16 + 128.553), ((0, 0, 255), 16 + 24.966)]:
        got = rgb_to_y(np.array([[rgb]], np.uint8))[0, 0]
        assert abs(got - expect) < 1e-9, (rgb, got, expect)


def test_colour_order_is_rgb_on_load_and_save(tmp_path=None):
    import tempfile
    import cv2
    d = Path(tempfile.mkdtemp())
    img = np.zeros((4, 4, 3), np.uint8)
    img[..., 0] = 200   # pure-ish red in RGB
    img[..., 2] = 10
    save_rgb(d / "t.png", img)
    assert np.array_equal(load_rgb(d / "t.png"), img)                     # round trip keeps RGB
    raw = cv2.imread(str(d / "t.png"))                                    # OpenCV's own view is BGR
    assert raw[0, 0].tolist() == [10, 0, 200]


def test_more_noise_lower_scores():
    a = rnd((48, 48, 3), 1)
    n1 = np.clip(a.astype(int) + 5, 0, 255).astype(np.uint8)
    n2 = np.clip(a.astype(int) + 40, 0, 255).astype(np.uint8)
    assert psnr_rgb(a, n1) > psnr_rgb(a, n2) and psnr_y(a, n1, 2) > psnr_y(a, n2, 2)


def test_shapes_and_modcrop():
    img = np.zeros((101, 77, 3), np.uint8)
    lr, hr = make_pair(img, 2)
    assert hr.shape == (100, 76, 3) and lr.shape == (50, 38, 3)
    assert upscale_pil(lr, 2).shape == hr.shape and modcrop(hr, 2).shape == hr.shape


def test_flat_image_survives_resize():
    img = np.full((20, 20, 3), 77, np.uint8)
    assert (upscale_pil(downscale_pil(img, 2), 2) == 77).all()


def test_pixel_alignment_no_shift():
    # a bright square in the centre must stay centred after down+up (no half-pixel shift)
    img = np.zeros((64, 64, 3), np.uint8)
    img[24:40, 24:40] = 255
    sr = upscale_pil(downscale_pil(img, 2), 2)[..., 0].astype(float)
    ys, xs = np.mgrid[:64, :64]
    cy, cx = (sr * ys).sum() / sr.sum(), (sr * xs).sum() / sr.sum()
    assert abs(cy - 31.5) < 0.1 and abs(cx - 31.5) < 0.1


def test_psnr_y_shaving_ignores_border_only_differences():
    a = rnd((40, 40, 3), 3)
    b = a.copy()
    b[:2], b[-2:], b[:, :2], b[:, -2:] = 0, 255, 0, 255  # corrupt ONLY the outer 2 px
    assert psnr_y(a, b, border=2) == float("inf")
    assert psnr_y(a, b, border=0) < 40
    assert ssim_y(a, b, border=2) > 0.999999 and ssim_y(a, b, border=0) < 0.999


def test_ssim_uses_gaussian_11_sigma_1p5_definition():
    from skimage.metrics import structural_similarity
    a = rnd((48, 48, 3), 4)
    b = np.clip(a.astype(int) + np.random.default_rng(5).integers(-30, 31, a.shape), 0, 255).astype(np.uint8)
    ref = structural_similarity(a, b, channel_axis=2, gaussian_weights=True, sigma=1.5, use_sample_covariance=False, data_range=255)
    assert abs(ssim_rgb(a, b) - ref) < 1e-12
    ya, yb = rgb_to_y(a), rgb_to_y(b)
    ref_y = structural_similarity(ya[2:-2, 2:-2], yb[2:-2, 2:-2], gaussian_weights=True, sigma=1.5, use_sample_covariance=False, data_range=255)
    assert abs(ssim_y(a, b, 2) - ref_y) < 1e-12


def test_real_data_lr_matches_official_and_files_exist():
    need(ROOT / "data" / "test" / "LR" / "Set5")
    for s, n in [("Set5", 5), ("Set14", 14), ("BSD100", 100)]:
        paths = list_images(ROOT / "data" / "test" / "HR" / s)
        assert len(paths) == n, (s, len(paths))
        p = paths[0]
        hr = load_rgb(p)
        assert hr.ndim == 3 and hr.shape[2] == 3 and hr.dtype == np.uint8
        lr, _ = make_pair(hr, 2)
        saved = load_rgb(ROOT / "data" / "test" / "LR" / s / p.name)
        assert np.array_equal(saved, lr), f"saved LR differs from regenerated LR ({s}/{p.name})"


def test_results_csv_sane():
    need(ROOT / "results" / "quality" / "baseline_x2.csv")
    with open(ROOT / "results" / "quality" / "baseline_x2.csv") as f:
        rows = list(csv.DictReader(f))
    assert len(rows) == (5 + 14 + 100) * 3
    for r in rows:
        assert 10 < float(r["psnr_rgb"]) < 60 and 0 < float(r["ssim_rgb"]) <= 1
    for s in ("Set5", "Set14", "BSD100"):  # bicubic must beat nearest on average
        m = lambda meth: np.mean([float(r["psnr_rgb"]) for r in rows if r["set"] == s and r["method"] == meth])  # noqa: E731
        assert m("bicubic") > m("nearest")


if __name__ == "__main__":
    for name, fn in list(globals().items()):
        if name.startswith("test_"):
            try:
                fn()
                print("PASS", name)
            except Skip as e:
                print("SKIP", name, "-", e)
