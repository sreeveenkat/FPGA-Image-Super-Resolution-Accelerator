#!/usr/bin/env python3
"""Non-cacheable DMA buffers, pipeline tree, REAL 125 MHz (own XSA init, clock read back and enforced).  Created 2026-10-28.

    .venv/bin/python software/board/run_nc.py

Variants (ELFs built from the same sources; software/board/build/*_x_<v>.elf in sandbox_pipe):
  fnv  = -DSR_FNV_TIME   cached buffers (reference), only adds the timing print of the ARM's output read
  out  = -DSR_NC_OUT     output region non-cacheable
  pad  = -DSR_NC_PAD     padded-input region non-cacheable
  both = both flags
Order: fnv, both, fnv, both (A/B/A/B), then out, pad.  Per variant: T1, T2 (byte-exact, 0x45dd4e2d), T5 (PASS), T3 20 frames (byte-exact; mean must be inside the predicted
range of that variant, else STOP).  Reported per variant: frame time (excludes the ARM's read of the output: the frame window ends when the DMA/compute wait ends, the read
is done by the test program afterwards to compute the checksum), pad time, DMA+compute window, ARM output read (flush or drain + FNV-1a), wall time per frame (frame + read).
At the end, and after any stop, the PRODUCTION pipeline ELF is loaded and one T2 must be byte-exact.  Temperature between runs only (stop above 70 C).  JTAG only.
"""
import re
import statistics
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))
import run_125 as R   # noqa: E402
import verify_driver_change as VD   # noqa: E402

d = VD.DES["pipe"]
B = d["tree"] / "software/board/build"
exp = d["tree"] / "data/board/div2k_img0193_expected_1920x1080.raw"
out = R.MAIN / "data/board/2026-10-28/nc"
out.mkdir(parents=True, exist_ok=True)
tlog = out / "nc_temperature.log"
# predicted frame-time ranges, ms (model, docs: cached 95.2-95.4; OUT only 75.8; PAD only 92.3 + dpad; both 73.0 + dpad, dpad -1..+4, worst +8)
RANGE = {"fnv": (93.4, 97.4), "out": (72.0, 81.0), "pad": (89.0, 100.0), "both": (70.0, 83.0)}
ORDER = ["fnv", "both", "fnv", "both", "out", "pad"]
rows = []


def production_check(why, safe=False):
    raw = out / "production_check.raw"
    rc, x = R.xsdb_run(d, B / "sr_app_t2.elf", VD.LR960, raw, out / "production_check_stats.txt", out / "production_check_xsdb.log", 60, None if safe else d["ps7"], 100 if safe else 125)
    st = R.read_stats(out / "production_check_stats.txt")
    ok = rc == 0 and raw.exists() and raw.read_bytes() == exp.read_bytes() and R.num(st, "version") == d["version"]
    print(f"PRODUCTION ELF CHECK ({why}): rc={rc} byte-exact={ok} fnv={st.get('fnv1a32')} version={st.get('version')} fclk0={st.get('fclk0_mhz')} MHz", flush=True)
    return ok


def one(v, k):
    tag = f"{v}{k}"
    o = out / tag
    o.mkdir(exist_ok=True)
    t = R.read_temp(f"before {tag}", tlog)
    if not t < R.TEMP_LIMIT_C:
        return f"temperature {t}"
    # T1
    cap = R.UartCapture(o / "t1.log")
    rc, x = R.xsdb_run(d, B / f"sr_app_t1_x_{v}.elf", "-", "-", o / "t1_stats.txt", o / "t1_xsdb.log", 60, d["ps7"], 125)
    cap.stop()
    st = R.read_stats(o / "t1_stats.txt")
    if rc != 0 or st.get("result") != "0" or "T1 PASS" not in (o / "t1.log").read_text(errors="replace"):
        return f"T1 failed (rc {rc})"
    # T2
    raw = o / "t2.raw"
    cap = R.UartCapture(o / "t2.log")
    rc, x = R.xsdb_run(d, B / f"sr_app_t2_x_{v}.elf", VD.LR960, raw, o / "t2_stats.txt", o / "t2_xsdb.log", 60, d["ps7"], 125)
    cap.stop()
    st = R.read_stats(o / "t2_stats.txt")
    log2 = (o / "t2.log").read_text(errors="replace")
    exact = raw.exists() and raw.read_bytes() == exp.read_bytes()
    nc = re.search(r"set-up (\d+) us", log2)
    f2 = re.search(r"output buffer \w[\w-]*\): (\d+) us", log2)
    print(f"[{tag}] T2: rc={rc} byte-exact={exact} fnv={st.get('fnv1a32')} total={st.get('stat0')} us pad={st.get('stat1')} us NC set-up={nc.group(1) if nc else '-'} us ARM output read={f2.group(1) if f2 else '-'} us", flush=True)
    if rc != 0 or not exact or R.num(st, "fnv1a32") != d["fnv"]:
        return "T2 not byte-exact"
    # T5
    cap = R.UartCapture(o / "t5.log")
    rc, x = R.xsdb_run(d, B / f"sr_app_t5_x_{v}.elf", "-", "-", o / "t5_stats.txt", o / "t5_xsdb.log", 120, d["ps7"], 125)
    cap.stop()
    ok5 = rc == 0 and "T5 PASS" in (o / "t5.log").read_text(errors="replace")
    print(f"[{tag}] T5: {'PASS' if ok5 else 'NOT PASS'}", flush=True)
    if not ok5:
        return "T5 failed"
    # T3
    raw = o / "t3.raw"
    cap = R.UartCapture(o / "t3.log")
    rc, x = R.xsdb_run(d, B / f"sr_app_t3_20f_x_{v}.elf", VD.LR960, raw, o / "t3_stats.txt", o / "t3_xsdb.log", 150, d["ps7"], 125)
    cap.stop()
    log = (o / "t3.log").read_text(errors="replace")
    frames = [int(q) for q in re.findall(r"frame \d+: total (\d+)", log)]
    exact = raw.exists() and raw.read_bytes() == exp.read_bytes()
    if len(frames) < 20:
        return f"T3: only {len(frames)} frames (rc {rc})"
    m = re.search(r"mean split: pad (\d+) us, ARM copy \d+ us, DMA\+compute (\d+) us", log)
    w = re.search(r"mean (\d+) us; frame time (\d+) us excludes it; wall per frame \(frame \+ output read\) (\d+) us", log)
    mean = statistics.mean(frames) / 1000
    row = dict(variant=v, run=k, frame_ms=mean, min_ms=min(frames) / 1000, max_ms=max(frames) / 1000, pad_ms=int(m.group(1)) / 1000, dma_ms=int(m.group(2)) / 1000,
               fnv_ms=int(w.group(1)) / 1000 if w else float("nan"), wall_ms=int(w.group(3)) / 1000 if w else float("nan"), nc_setup_us=int(nc.group(1)) if nc else 0)
    rows.append(row)
    print(f"[{tag}] T3 20 frames: byte-exact={exact} frame {mean:.2f} ms (min {row['min_ms']:.2f}, max {row['max_ms']:.2f}), pad {row['pad_ms']:.2f} ms, DMA+compute {row['dma_ms']:.2f} ms, "
          f"ARM output read {row['fnv_ms']:.2f} ms, wall per frame {row['wall_ms']:.2f} ms", flush=True)
    if rc != 0 or not exact:
        return "T3 failed / not byte-exact"
    lo, hi = RANGE[v]
    if not lo <= mean <= hi:
        return f"T3 frame mean {mean:.2f} ms outside the predicted range {lo}-{hi} ms"
    t = R.read_temp(f"after {tag}", tlog)
    return None if t < R.TEMP_LIMIT_C else f"temperature {t}"


seen = {}
fail = None
for v in ORDER:
    seen[v] = seen.get(v, 0) + 1
    fail = one(v, seen[v])
    if fail:
        print(f"!! STOP at {v}{seen[v]}: {fail}", flush=True)
        break
print("\nSUMMARY (125 MHz, pipeline, 20-frame means, ms):", flush=True)
print("  run        frame    pad   DMA+comp  ARM-out-read  wall(frame+read)", flush=True)
for r in rows:
    print(f"  {r['variant']}{r['run']:<7d} {r['frame_ms']:7.2f} {r['pad_ms']:6.2f} {r['dma_ms']:9.2f} {r['fnv_ms']:12.2f} {r['wall_ms']:14.2f}", flush=True)
ok = production_check("after the flagged runs") if not fail else production_check(f"after STOP ({fail}): back at the 100 MHz init", safe=True)
sys.exit(0 if (not fail and ok) else 1)
