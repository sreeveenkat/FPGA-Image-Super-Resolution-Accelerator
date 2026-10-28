#!/usr/bin/env python3
"""A/B of the ARM tile-copy shift seen after the driver change of 2026-10-28: R0 at 100 MHz, 20-frame T3, OLD ELF, NEW ELF, OLD ELF, NEW ELF back to back.

    .venv/bin/python software/board/run_ab.py

Old = software/board/build/sr_app_t3_20f_before_20261028.elf, new = sr_app_t3_20f.elf (same tree, same bitstream, platform init = 100 MHz, clock read back).
Reports per run: frame mean, ARM tile copy, DMA+compute and padding (means over 20 frames).  Decision rule fixed BEFORE the run: the gap (new - old) in the tile-copy time is
'persistent' if both pairs show the same sign and each gap is larger than 3 x the run-to-run difference inside the same ELF (old1 vs old2, new1 vs new2); otherwise 'drift'.
Each run must be byte-exact (0xcf947f22); stops at the first failure.  Temperature between runs only.  JTAG only.  Created 2026-10-28.
"""
import re
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))
import run_125 as R   # noqa: E402
import verify_driver_change as VD   # noqa: E402

d = VD.DES["r0"]
B = d["tree"] / "software/board/build"
exp = d["tree"] / "data/board/div2k_img0193_expected_1920x1080.raw"
out = R.MAIN / "data/board/2026-10-28/ab"
out.mkdir(parents=True, exist_ok=True)
tlog = out / "ab_temperature.log"
runs = []
for tag, elf in (("old1", "sr_app_t3_20f_before_20261028.elf"), ("new1", "sr_app_t3_20f.elf"), ("old2", "sr_app_t3_20f_before_20261028.elf"), ("new2", "sr_app_t3_20f.elf")):
    t = R.read_temp(f"before {tag}", tlog)
    if not t < R.TEMP_LIMIT_C:
        print("STOP: temperature", t)
        sys.exit(1)
    cap = R.UartCapture(out / f"ab_{tag}.log")
    raw = out / f"ab_{tag}.raw"
    rc, x = R.xsdb_run(d, B / elf, VD.LR960, raw, out / f"ab_{tag}_stats.txt", out / f"ab_{tag}_xsdb.log", 108, None, 100)
    cap.stop()
    log = (out / f"ab_{tag}.log").read_text(errors="replace")
    m = re.search(r"per frame mean (\d+) us.*?min (\d+) us, max (\d+) us; mean split: pad (\d+) us, ARM copy (\d+) us, DMA\+compute (\d+) us", log)
    exact = raw.exists() and raw.read_bytes() == exp.read_bytes()
    if rc != 0 or not exact or not m:
        print(f"STOP at {tag}: rc={rc} byte-exact={exact} parsed={bool(m)}")
        VD.recover(d, out, f"A/B run {tag}")
        sys.exit(1)
    mean, mn, mx, pad, cp, dc = (int(v) / 1000 for v in m.groups())
    runs.append(dict(tag=tag, mean=mean, min=mn, max=mx, pad=pad, copy=cp, dma=dc))
    print(f"{tag}: frame mean {mean:.3f} ms (min {mn:.3f}, max {mx:.3f}), ARM tile copy {cp:.3f} ms, DMA+compute {dc:.3f} ms, pad {pad:.3f} ms, byte-exact={exact}", flush=True)
R.read_temp("after A/B", tlog)
o1, n1, o2, n2 = runs
gap1, gap2 = n1["copy"] - o1["copy"], n2["copy"] - o2["copy"]
noise = max(abs(o1["copy"] - o2["copy"]), abs(n1["copy"] - n2["copy"]), 0.005)
fgap1, fgap2 = n1["mean"] - o1["mean"], n2["mean"] - o2["mean"]
print(f"tile-copy gap (new - old): pair 1 {gap1:+.3f} ms, pair 2 {gap2:+.3f} ms; run-to-run difference inside the same ELF: old {abs(o1['copy'] - o2['copy']):.3f}, new {abs(n1['copy'] - n2['copy']):.3f} ms", flush=True)
print(f"frame-mean gap (new - old): pair 1 {fgap1:+.3f} ms, pair 2 {fgap2:+.3f} ms", flush=True)
persistent = gap1 * gap2 > 0 and min(abs(gap1), abs(gap2)) > 3 * noise
print("VERDICT:", "persistent across both pairs -> ELF-dependent (cause not isolated)" if persistent else "not persistent -> drift", flush=True)
