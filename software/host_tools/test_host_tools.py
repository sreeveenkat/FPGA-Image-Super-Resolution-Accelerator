"""Tests for the host tools (srim, png2raw, raw2png, expected_output, compare_raw, golden_tile_h).  Run from the project root:
    .venv/bin/python software/host_tools/test_host_tools.py
Uses data/board/set14_baboon_lr_128x128.* (make_test_images.py) and data/golden/real0_*.hex (export_rtl.py); fails if they are missing."""
import re
import struct
import subprocess
import sys
import tempfile
from pathlib import Path

import numpy as np

ROOT = Path(__file__).resolve().parents[2]
HT = ROOT / "software" / "host_tools"
sys.path.insert(0, str(ROOT / "software" / "ai"))
sys.path.insert(0, str(HT))
from dataset.pairs import load_rgb  # noqa: E402
from srim import fnv1a32, read_srim, write_srim  # noqa: E402

fails = 0


def check(cond, msg):
    global fails
    print(("PASS " if cond else "FAIL ") + msg)
    if not cond:
        fails += 1


def run(*args):
    return subprocess.run([sys.executable, *map(str, args)], capture_output=True, text=True, cwd=ROOT)


def main():
    png = ROOT / "data/board/set14_baboon_lr_128x128.png"
    raw0 = ROOT / "data/board/set14_baboon_lr_128x128.raw"
    for f in (png, raw0, ROOT / "data/golden/real0_in.hex"):
        if not f.exists():
            print(f"FAIL: {f} missing (run make_test_images.py / export_rtl.py)")
            sys.exit(1)
    with tempfile.TemporaryDirectory() as t:
        t = Path(t)
        # ---- format
        img = load_rgb(png)
        b = raw0.read_bytes()
        check(b[:4] == b"SRIM" and struct.unpack("<III", b[4:16]) == (128, 128, 0) and len(b) == 16 + 128 * 128 * 3, "SRIM header: magic, w, h, reserved = 0, size")
        check(b[16:19] == img[0, 0].tobytes() and b[19:22] == img[0, 1].tobytes(), "SRIM payload is RGB interleaved, row-major")
        # ---- png2raw / raw2png round trip
        r = run(HT / "png2raw.py", png, t / "a.raw")
        check(r.returncode == 0 and (t / "a.raw").read_bytes() == b, "png2raw reproduces data/board/*.raw byte for byte")
        r = run(HT / "raw2png.py", t / "a.raw", t / "a.png")
        check(r.returncode == 0 and np.array_equal(load_rgb(t / "a.png"), img), "raw2png: PNG -> raw -> PNG is lossless")
        # ---- expected_output (integer model, whole image) and compare_raw
        r = run(HT / "expected_output.py", raw0, t / "exp")
        check(r.returncode == 0 and (t / "exp.raw").exists() and (t / "exp.png").exists(), "expected_output writes .png and .raw")
        exp = read_srim(t / "exp.raw")
        check(exp.shape == (256, 256, 3), "expected output is 2W x 2H")
        r = run(HT / "compare_raw.py", t / "exp.raw", t / "exp.raw")
        check(r.returncode == 0 and "BYTE-EXACT: yes" in r.stdout, "compare_raw: identical files -> exit 0, 'BYTE-EXACT: yes'")
        bad = exp.copy()
        bad[10, 20, 1] ^= 0x10
        bad[200, 5, 0] = (int(bad[200, 5, 0]) + 7) % 256
        bad[255, 255, 2] ^= 0xFF
        write_srim(t / "bad.raw", bad)
        r = run(HT / "compare_raw.py", t / "bad.raw", t / "exp.raw", t / "d.png")
        m = re.findall(r"^\s+\((\d+), (\d+), (\d+), (\d+), (\d+)\)$", r.stdout, re.M)
        check(r.returncode == 1 and "BYTE-EXACT: NO - 3 of" in r.stdout and (t / "d.png").exists(), "compare_raw: 3 corrupted bytes -> exit 1, count 3, diff image written")
        check([tuple(map(int, x[:3])) for x in m] == [(20, 10, 1), (5, 200, 0), (255, 255, 2)] and int(m[0][3]) == int(bad[10, 20, 1]) and int(m[0][4]) == int(exp[10, 20, 1]),
              "compare_raw: mismatches listed as (x, y, c, got, expected) in raster order")
        mx = int(np.abs(bad.astype(np.int16) - exp.astype(np.int16)).max())
        check(f"max abs diff {mx}" in r.stdout, f"compare_raw: max abs diff reported correctly ({mx})")
        junk = bytearray((t / "exp.raw").read_bytes()); junk[:4] = b"XXXX"; (t / "junk.raw").write_bytes(junk)
        check(run(HT / "compare_raw.py", t / "junk.raw", t / "exp.raw").returncode == 2, "compare_raw: bad magic -> exit 2")
        write_srim(t / "small.raw", exp[:100, :100])
        check(run(HT / "compare_raw.py", t / "small.raw", t / "exp.raw").returncode == 2, "compare_raw: different sizes -> exit 2")
        (t / "short.raw").write_bytes((t / "exp.raw").read_bytes()[:-5])
        check(run(HT / "compare_raw.py", t / "short.raw", t / "exp.raw").returncode == 2, "compare_raw: truncated file -> exit 2")
        # ---- checksum
        check(fnv1a32(b"") == 0x811C9DC5 and fnv1a32(b"a") == 0xE40C292C and fnv1a32(b"foobar") == 0xBF9CF968, "fnv1a32 matches the published FNV-1a test vectors")
    # ---- golden_tile.h (regenerated, then compared with the hex files)
    r = run(HT / "golden_tile_h.py")
    check(r.returncode == 0, "golden_tile_h.py runs")
    h = (ROOT / "software/board/sr_app/golden_tile.h").read_text()
    for name, hexf, n in (("sr_golden_in", "real0_in.hex", 14700), ("sr_golden_out", "real0_out.hex", 49152)):
        body = re.search(rf"{name}\[(\d+)\] __attribute__\(\(aligned\(64\)\)\) = \{{(.*?)\}};", h, re.S)
        vals = [int(x, 16) for x in re.findall(r"0x([0-9a-f]{2})", body.group(2))] if body else []
        exp_vals = [int(x, 16) for x in (ROOT / "data/golden" / hexf).read_text().split()]
        check(body is not None and int(body.group(1)) == n and vals == exp_vals, f"golden_tile.h: {name}[{n}] equals data/golden/{hexf}")
    if fails:
        print(f"FAIL test_host_tools: {fails} check(s) failed")
        sys.exit(1)
    print("PASS test_host_tools")


if __name__ == "__main__":
    main()
