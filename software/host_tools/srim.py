"""The SRIM raw image format shared by all host tools and the board program (software/board/sr_app/main.c).

    offset 0   4 bytes   magic  b"SRIM"
    offset 4   u32 LE    width  (pixels)
    offset 8   u32 LE    height (pixels)
    offset 12  u32 LE    reserved (0)
    offset 16  width*height*3 bytes: RGB interleaved, row-major, uint8 (R,G,B of pixel (0,0), then pixel (1,0), ...)

Total file size = 16 + 3*width*height.  The checksum printed by the board is FNV-1a 32 over the PAYLOAD bytes (after the header).
"""
import struct
from pathlib import Path

import numpy as np

MAGIC = b"SRIM"
HEADER_BYTES = 16


def write_srim(path, rgb: np.ndarray) -> None:
    assert rgb.ndim == 3 and rgb.shape[2] == 3 and rgb.dtype == np.uint8, "need uint8 (H, W, 3)"
    h, w = rgb.shape[:2]
    Path(path).parent.mkdir(parents=True, exist_ok=True)
    with open(path, "wb") as f:
        f.write(MAGIC + struct.pack("<III", w, h, 0))
        f.write(np.ascontiguousarray(rgb).tobytes())


def read_srim(path) -> np.ndarray:
    data = Path(path).read_bytes()
    if len(data) < HEADER_BYTES or data[:4] != MAGIC:
        raise ValueError(f"{path}: not an SRIM file (bad magic or shorter than {HEADER_BYTES} bytes)")
    w, h, _ = struct.unpack("<III", data[4:16])
    if len(data) != HEADER_BYTES + 3 * w * h:
        raise ValueError(f"{path}: size {len(data)} does not match {w}x{h} (expected {HEADER_BYTES + 3 * w * h})")
    return np.frombuffer(data, dtype=np.uint8, offset=HEADER_BYTES).reshape(h, w, 3).copy()


def fnv1a32(payload: bytes) -> int:
    """FNV-1a 32 bit (same function as sr_fnv1a32 in software/board/sr_app/sr_tiling.c)."""
    h = 0x811C9DC5
    for b in payload:
        h = ((h ^ b) * 0x01000193) & 0xFFFFFFFF
    return h
