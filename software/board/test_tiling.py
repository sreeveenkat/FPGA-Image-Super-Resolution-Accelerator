"""PC proof that the board's tiling code (software/board/sr_app/sr_tiling.c, compiled with gcc) is exact:

    cut (C)  +  integer_reference.run_tile on every tile (Python)  +  assemble (C)   ==   integer_reference.upscale (whole image)   (bit-exact)

for the 128x128 test image, the 960x540 image and a set of awkward sizes (not multiples of 64, one tile, one pixel over, tiny).  Also checks that every tile the C code
cuts equals the NumPy window of the replicate-padded image, and that the C checksum (FNV-1a) equals the Python one.
    .venv/bin/python software/board/test_tiling.py [--quick]      (--quick: skips the 960x540 image)
Needs data/board/*.raw (software/host_tools/make_test_images.py) unless --quick.
"""
import subprocess
import sys
import tempfile
from pathlib import Path

import numpy as np

ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(ROOT / "software" / "ai"))
sys.path.insert(0, str(ROOT / "software" / "host_tools"))
from quantization.integer_reference import HALO, QNet, run_tile, upscale  # noqa: E402
from srim import fnv1a32, read_srim, write_srim  # noqa: E402

QPARAMS = ROOT / "software" / "ai" / "quantization" / "qparams.npz"
NET = QNet.load(QPARAMS)
fails = 0


def build(tmp):
    exe = Path(tmp) / "tiling_tool"
    cmd = ["gcc", "-std=c99", "-O1", "-g", "-Wall", "-Wextra", "-Werror", "-I", str(ROOT / "software/board"), "-I", str(ROOT / "software/board/sr_app"),
           str(ROOT / "software/board/pc_test/tiling_tool.c"), str(ROOT / "software/board/sr_app/sr_tiling.c"), "-o", str(exe)]
    san = ["-fsanitize=address,undefined", "-fno-sanitize-recover=all"]      # a buffer overrun in cut / place must not pass silently
    if subprocess.run(cmd + san, capture_output=True).returncode == 0:
        print("(built with AddressSanitizer + UBSan)")
    else:
        subprocess.run(cmd, check=True)
        print("(sanitizers not available, plain build)")
    return str(exe)


def check_image(exe, tmp, name, lr, whole=None):
    """lr: uint8 (H,W,3).  Returns True when bit-exact."""
    global fails
    h, w = lr.shape[:2]
    d = Path(tmp) / name
    d.mkdir()
    src = d / "in.raw"
    write_srim(src, lr)
    r = subprocess.run([exe, "cut", str(src), str(d)], capture_output=True, text=True)
    if r.returncode:
        print(f"FAIL {name}: cut failed: {r.stdout}{r.stderr}")
        fails += 1
        return False
    tx_n, ty_n = -(-w // 64), -(-h // 64)
    padded = np.pad(lr, ((HALO, HALO + ty_n * 64 - h), (HALO, HALO + tx_n * 64 - w), (0, 0)), mode="edge")
    bad_tiles = 0
    for ty in range(ty_n):
        for tx in range(tx_n):
            f_in = d / f"in_{ty}_{tx}.bin"
            if not f_in.exists():                                     # the C code visited fewer tiles than the geometry needs
                bad_tiles += 1
                continue
            tile = np.frombuffer(f_in.read_bytes(), dtype=np.uint8)
            if tile.size != 70 * 70 * 3:
                bad_tiles += 1
                continue
            tile = tile.reshape(70, 70, 3)
            if not np.array_equal(tile, padded[ty * 64:ty * 64 + 70, tx * 64:tx * 64 + 70]):     # the C cut == the NumPy window
                bad_tiles += 1
            (d / f"out_{ty}_{tx}.bin").write_bytes(run_tile(NET, tile).tobytes())                 # the "core"
    if bad_tiles:
        print(f"FAIL {name}: {bad_tiles} of {tx_n * ty_n} tiles cut by the C code differ from the padded-image window")
        fails += 1
        return False
    out = d / "out.raw"
    r = subprocess.run([exe, "assemble", str(src), str(d), str(out)], capture_output=True, text=True)
    if r.returncode:
        print(f"FAIL {name}: assemble failed: {r.stdout}{r.stderr}")
        fails += 1
        return False
    got = read_srim(out)
    exp = upscale(NET, lr) if whole is None else whole
    ok = got.shape == exp.shape and np.array_equal(got, exp)
    ck = subprocess.run([exe, "fnv", str(out)], capture_output=True, text=True).stdout.strip()
    ck_ok = ck == f"0x{fnv1a32(exp.tobytes()):08x}"
    print(f"{'PASS' if ok and ck_ok else 'FAIL'} {name}: {w}x{h} -> {got.shape[1]}x{got.shape[0]}, {tx_n}x{ty_n} = {tx_n * ty_n} tiles, "
          f"{'bit-exact with integer_reference.upscale' if ok else 'DIFFERENT from integer_reference.upscale'}, C checksum {ck} {'==' if ck_ok else '!='} Python")
    if not (ok and ck_ok):
        fails += 1
    return ok and ck_ok


def main():
    quick = "--quick" in sys.argv
    rng = np.random.default_rng(1234)
    with tempfile.TemporaryDirectory() as tmp:
        exe = build(tmp)
        board = ROOT / "data" / "board"
        if (board / "set14_baboon_lr_128x128.raw").exists():
            check_image(exe, tmp, "baboon_128x128", read_srim(board / "set14_baboon_lr_128x128.raw"))
        else:
            print("FAIL: data/board/set14_baboon_lr_128x128.raw missing (run software/host_tools/make_test_images.py)")
            sys.exit(1)
        for (h, w) in [(64, 64), (65, 65), (1, 1), (37, 29), (100, 90), (70, 130), (129, 63)]:        # one tile, one pixel over, tiny, non-multiples, non-square
            check_image(exe, tmp, f"random_{w}x{h}", rng.integers(0, 256, (h, w, 3), dtype=np.uint8))
        if not quick:
            raw = board / "div2k_img0193_lr_960x540.raw"
            if not raw.exists():
                print("FAIL: data/board/div2k_img0193_lr_960x540.raw missing (run software/host_tools/make_test_images.py)")
                sys.exit(1)
            check_image(exe, tmp, "div2k_960x540", read_srim(raw))
    if fails:
        print(f"FAIL test_tiling: {fails} image(s) failed")
        sys.exit(1)
    print("PASS test_tiling: C tiling code (cut + place + checksum) is bit-exact with the integer model on all images")


if __name__ == "__main__":
    main()
