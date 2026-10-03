"""Image-quality metrics for RGB uint8 images (scikit-image underneath; nothing hand-rolled).

SSIM settings
  * ``ssim_*``            : Gaussian 11x11 window, sigma 1.5, population covariance - the original Wang et al.
                            definition that SR papers report. THIS is the project's SSIM.
  * ``ssim_rgb_default``  : scikit-image default (7x7 uniform window). Stored in the CSV for reference only.
PSNR/SSIM "Y" variants use BT.601 luma and shave a border of ``scale`` pixels, as in SR papers.
"""
import numpy as np
from skimage.metrics import peak_signal_noise_ratio, structural_similarity

_GAUSS = dict(gaussian_weights=True, sigma=1.5, use_sample_covariance=False, data_range=255)


def rgb_to_y(img: np.ndarray) -> np.ndarray:
    """ITU-R BT.601 luma (studio range 16..235). Returns float64 2-D array."""
    f = img.astype(np.float64)
    return (65.481 * f[..., 0] + 128.553 * f[..., 1] + 24.966 * f[..., 2]) / 255.0 + 16.0


def shave(img: np.ndarray, border: int) -> np.ndarray:
    return img[border:-border, border:-border] if border > 0 else img


def _psnr(a, b) -> float:
    with np.errstate(divide="ignore"):  # identical images -> inf, without a warning
        return float(peak_signal_noise_ratio(a, b, data_range=255))


def psnr_rgb(ref: np.ndarray, test: np.ndarray) -> float:
    return _psnr(ref, test)


def ssim_rgb(ref: np.ndarray, test: np.ndarray) -> float:
    return float(structural_similarity(ref, test, channel_axis=2, **_GAUSS))


def ssim_rgb_default(ref: np.ndarray, test: np.ndarray) -> float:
    return float(structural_similarity(ref, test, channel_axis=2, data_range=255))


def psnr_y(ref: np.ndarray, test: np.ndarray, border: int = 0) -> float:
    return _psnr(shave(rgb_to_y(ref), border), shave(rgb_to_y(test), border))


def ssim_y(ref: np.ndarray, test: np.ndarray, border: int = 0) -> float:
    return float(structural_similarity(shave(rgb_to_y(ref), border), shave(rgb_to_y(test), border), **_GAUSS))
