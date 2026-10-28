#!/usr/bin/env python3
"""Flagged timing runs of 2026-10-28 (driver built with -DSR_TIMING_SPLIT) at the REAL 125 MHz clock, plus the T7 run with the fixed timer.

    .venv/bin/python software/board/run_split.py [--only r0_125,r3q_125,pipe,t7]

Per 125 MHz design (own XSA init, clock read back and enforced): T2 split ELF (1 frame, byte-exact) and T3 20-frame split ELF (byte-exact, mean within +-2 ms of the production
mean measured today with the same tree, max - min <= 3 ms).  Parses the "split over N call(s)" lines the ARM prints after every frame and averages them.
t7: R0 tree, new T7 ELF at 100 MHz (platform init): byte-exact (0xcf947f22) and the ARM-side time must now be non-zero; it is compared with the host timestamps of the UART lines.
Stops at the first failure and returns to the 100 MHz init with the OLD t2 ELF.  Temperature read between runs only.  JTAG only.  Created 2026-10-28.
"""
import argparse
import re
import statistics
import sys
from datetime import datetime
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))
import run_125 as R   # noqa: E402
import verify_driver_change as VD   # noqa: E402

MAIN = R.MAIN
PROD_MEAN = {"r0_125": 1062.21, "r3q_125": 1062.35, "pipe": 95.36}   # production new-ELF T3 means of verify_driver_change.py (same day)
KEYS = ["busy+regs", "flush in", "flush out", "DMA set-up+START", "wait", "check+invalidate+CYCLES", "sum"]


def parse_split(line):
    m = re.search(r"split over (\d+) call\(s\), us: busy\+regs (\d+), flush in (\d+), flush out (\d+), DMA set-up\+START (\d+), wait (\d+), check\+invalidate\+CYCLES (\d+), sum (\d+)", line)
    return (int(m.group(1)), [int(m.group(i)) for i in range(2, 9)]) if m else None


def split_design(key, out):
    d = VD.DES[key]
    nm = d["name"]
    B = d["tree"] / "software/board/build"
    exp = d["tree"] / "data/board/div2k_img0193_expected_1920x1080.raw"
    o = out / nm
    o.mkdir(parents=True, exist_ok=True)
    tlog = o / f"{nm}_temperature.log"
    t = R.read_temp(f"before split {nm}", tlog)
    if not t < R.TEMP_LIMIT_C:
        return f"temperature {t}"
    # T2 split, one frame
    raw = o / f"{nm}_t2_split.raw"
    cap = R.UartCapture(o / f"{nm}_t2_split.log")
    rc, x = R.xsdb_run(d, B / "sr_app_t2_split.elf", VD.LR960, raw, o / f"{nm}_t2_split_stats.txt", o / f"{nm}_t2_split_xsdb.log", 60, d["ps7"], d["mhz"])
    cap.stop()
    st = R.read_stats(o / f"{nm}_t2_split_stats.txt")
    exact = raw.exists() and raw.read_bytes() == exp.read_bytes()
    log = (o / f"{nm}_t2_split.log").read_text(errors="replace")
    sp = [parse_split(l) for l in log.splitlines() if "split over" in l]
    print(f"[{nm}] T2 split: rc={rc} byte-exact={exact} fnv={st.get('fnv1a32')} fclk0={st.get('fclk0_mhz')} MHz; split lines {len(sp)}", flush=True)
    if rc != 0 or not exact or R.num(st, "fnv1a32") != d["fnv"] or not sp or sp[0] is None:
        return "T2 split failed"
    # T3 split, 20 frames
    raw = o / f"{nm}_t3_split.raw"
    cap = R.UartCapture(o / f"{nm}_t3_split.log")
    rc, x = R.xsdb_run(d, B / "sr_app_t3_20f_split.elf", VD.LR960, raw, o / f"{nm}_t3_split_stats.txt", o / f"{nm}_t3_split_xsdb.log", 108, d["ps7"], d["mhz"])
    cap.stop()
    log = (o / f"{nm}_t3_split.log").read_text(errors="replace")
    frames = [int(v) for v in re.findall(r"frame \d+: total (\d+)", log)]
    exact = raw.exists() and raw.read_bytes() == exp.read_bytes()
    if len(frames) < 20:
        return f"T3 split: only {len(frames)} frames (rc={rc})"
    mean = statistics.mean(frames) / 1000
    spread = (max(frames) - min(frames)) / 1000
    print(f"[{nm}] T3 split (20 frames): mean {mean:.2f} ms (production {PROD_MEAN[key]}), min {min(frames) / 1000:.2f}, max {max(frames) / 1000:.2f}, max-min {spread:.2f}, byte-exact={exact}", flush=True)
    if rc != 0 or not exact:
        return "T3 split failed / not byte-exact"
    if abs(mean - PROD_MEAN[key]) > 2.0 or spread > 3.0:
        return f"T3 split mean {mean:.2f} ms outside {PROD_MEAN[key]} +- 2 ms (or spread {spread:.2f} > 3 ms)"
    rows = [parse_split(l) for l in log.splitlines() if "split over" in l]
    rows = [r for r in rows if r]
    calls = rows[0][0]
    avg = [statistics.mean(r[1][i] for r in rows) for i in range(7)]
    runs = [int(v) for v in re.findall(r"DMA/compute wait (\d+)", log)]
    cyc = R.num(R.read_stats(o / f"{nm}_t3_split_stats.txt"), "stat11") or R.num(R.read_stats(o / f"{nm}_t3_split_stats.txt"), "stat6")
    print(f"[{nm}] split per frame, mean of {len(rows)} frames, {calls} DMA call(s) per frame, us:", flush=True)
    for k, v in zip(KEYS, avg):
        print(f"      {k:26s} {v:12.1f}", flush=True)
    if runs:
        print(f"      (T3 'DMA/compute wait' window, mean: {statistics.mean(runs):.1f} us; split sum minus window: {avg[6] - statistics.mean(runs):+.1f} us)", flush=True)
    core_us = (cyc or 0) * (calls if d["mhz"] and key != "pipe" else 1) / d["mhz"]
    print(f"      core cycles per frame = {core_us:.1f} us at {d['mhz']} MHz (CYCLES {cyc} x {calls if key != 'pipe' else 1}); wait minus core cycles = {avg[4] - core_us:.1f} us", flush=True)
    t = R.read_temp(f"after split {nm}", tlog)
    return None if t < R.TEMP_LIMIT_C else f"temperature {t}"


def t7(out):
    d = VD.DES["r0"]
    o = out / "R0_t7"
    o.mkdir(parents=True, exist_ok=True)
    B = d["tree"] / "software/board/build"
    exp = d["tree"] / "data/board/div2k_img0193_expected_1920x1080.raw"
    raw = o / "R0_t7.raw"
    cap = R.UartCapture(o / "R0_t7.log")
    rc, x = R.xsdb_run(d, B / "sr_app_t11.elf", VD.LR960, raw, o / "R0_t7_stats.txt", o / "R0_t7_xsdb.log", 60, None, 100)
    cap.stop()
    st = R.read_stats(o / "R0_t7_stats.txt")
    exact = raw.exists() and raw.read_bytes() == exp.read_bytes()
    log = (o / "R0_t7.log").read_text(errors="replace")
    frame = re.search(r"frame 0: total (\d+) us = pad (\d+) \+ ARM tile copy (\d+) \+ ARM compute (\d+)", log)
    stamps = {}
    for l in log.splitlines():
        m = re.match(r"(\d{4}-\d\d-\d\d \d\d:\d\d:\d\d\.\d+)", l)
        if m and "T7: ARM-only" in l:
            stamps["start"] = datetime.fromisoformat(m.group(1))
        if m and "frame 0:" in l:
            stamps["end"] = datetime.fromisoformat(m.group(1))
    host = (stamps["end"] - stamps["start"]).total_seconds() if len(stamps) == 2 else None
    print(f"[R0 T7] rc={rc} byte-exact={exact} fnv={st.get('fnv1a32')} (expected 0xcf947f22)", flush=True)
    if frame:
        tot, pad, cp, run = (int(frame.group(i)) for i in range(1, 5))
        print(f"[R0 T7] ARM timer: total {tot} us = pad {pad} + ARM tile copy {cp} + ARM compute {run}; host timestamps (T7 start line -> frame line): {host} s", flush=True)
        if tot == 0:
            return "T7 timer still reads 0"
    else:
        return "T7: no frame line"
    if rc != 0 or not exact:
        return "T7 failed / not byte-exact"
    return None


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--out", default=str(MAIN / "data/board/2026-10-28/split"))
    ap.add_argument("--only", default="r0_125,r3q_125,pipe,t7")
    a = ap.parse_args()
    out = Path(a.out)
    out.mkdir(parents=True, exist_ok=True)
    for k in a.only.split(","):
        why = t7(out) if k == "t7" else split_design(k, out)
        if why:
            print(f"!! STOP at {k}: {why}", flush=True)
            if k != "t7":
                VD.recover(VD.DES[k], out, why)
            return 1
        print(f"== {k} OK", flush=True)
    print("ALL OK", flush=True)
    return 0


if __name__ == "__main__":
    sys.exit(main())
