"""LR/HR pair creation. Colour convention for the whole project: images are RGB uint8 (H, W, 3).

OpenCV reads BGR, so every loader here converts to RGB immediately and every saver converts back.

LR protocol (see check_lr_protocol.py):
    HR  = full-size HR cropped (bottom/right) so both sides are divisible by ``scale``   ("modcrop")
    LR  = Pillow BICUBIC resize of that cropped HR to (W // scale, H // scale)
Pillow's bicubic is anti-aliased when shrinking (kernel a = -0.5).
For images whose sides are already even this is BIT-EXACT with the official Set5/Set14/BSD100 x2 LR files.
For odd-sized images the official files resize the *uncropped* HR (e.g. 391 -> 195, a factor of 2.005), which leaves
LR and HR slightly misaligned and costs PSNR; we crop first so LR and HR are perfectly aligned.
The ``*_cv2`` functions (a = -0.75, no anti-aliasing) are kept only for comparison; do not use them for training.
"""
from pathlib import Path

import cv2
import numpy as np
from PIL import Image

IMG_EXT = {".png", ".jpg", ".jpeg", ".bmp"}


def load_rgb(path) -> np.ndarray:
    bgr = cv2.imread(str(path), cv2.IMREAD_COLOR)
    if bgr is None:
        raise FileNotFoundError(path)
    return cv2.cvtColor(bgr, cv2.COLOR_BGR2RGB)


def save_rgb(path, rgb: np.ndarray) -> None:
    Path(path).parent.mkdir(parents=True, exist_ok=True)
    if not cv2.imwrite(str(path), cv2.cvtColor(rgb, cv2.COLOR_RGB2BGR)):
        raise IOError(f"could not write {path}")


def list_images(folder) -> list:
    return sorted(p for p in Path(folder).iterdir() if p.suffix.lower() in IMG_EXT)


def downscale_pil(hr: np.ndarray, scale: int = 2) -> np.ndarray:
    """HR -> LR of size (H // scale, W // scale), Pillow bicubic. Crop odd-sized HR with modcrop() first."""
    h, w = hr.shape[:2]
    return np.asarray(Image.fromarray(hr).resize((w // scale, h // scale), Image.BICUBIC))


def upscale_pil(lr: np.ndarray, scale: int = 2) -> np.ndarray:
    h, w = lr.shape[:2]
    return np.asarray(Image.fromarray(lr).resize((w * scale, h * scale), Image.BICUBIC))


def modcrop(img: np.ndarray, scale: int = 2) -> np.ndarray:
    """Crop bottom/right so both sides are divisible by ``scale``."""
    h, w = img.shape[:2]
    return img[: h - h % scale, : w - w % scale]


def make_pair(hr: np.ndarray, scale: int = 2):
    """Return (lr, hr_cropped) for a full-size HR image."""
    hr = modcrop(hr, scale)
    return downscale_pil(hr, scale), hr


# --------------------------------------------------------------------------- OpenCV (comparison only)
def upscale_cv2(lr: np.ndarray, scale: int = 2, mode: int = cv2.INTER_CUBIC) -> np.ndarray:
    h, w = lr.shape[:2]
    return cv2.resize(lr, (w * scale, h * scale), interpolation=mode)
