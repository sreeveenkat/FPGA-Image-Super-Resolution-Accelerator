#!/usr/bin/env python3
"""Verification steps 1-4 of the driver change of 2026-10-28 (VERSION check before the DMA is touched, T7 timer, optional timing split).

    .venv/bin/python software/board/verify_driver_change.py [--out data/board/2026-10-28/verify] [--only r0,r2q,...]

For each of the six designs, with the NEW production ELFs of its tree, in this order: R0, R2q, R3q (100 MHz, platform init), r0_125, r3q_125, pipe (125 MHz, own XSA init,
clock read back and enforced by run_board_clk.tcl):
  T1 (golden tile, VERSION, 20/20 repeats), T2 (960x540 byte-exact against the tree's expected file, checksum), T3 20 frames (mean must be within +-2 ms of the mean measured
  with the old ELFs on 2026-10-27/28, max - min <= 3 ms, output byte-exact), and T5 error recovery on R0 and the pipeline.
It STOPS at the first failure (byte-exact, VERSION, checksum, T3 outside +-2 ms, T5), returns to the 100 MHz init with the OLD t2 ELF (*_before_20261028) and checks one image.
Die temperature is read through the XADC only between runs (software/board/xadc_temp.tcl); stop above 70 C.  All waits are bounded.  Uses JTAG only.
"""
import argparse
import re
import statistics
import sys
import time
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))
import run_125 as R   # noqa: E402  (shared helpers: xsdb_run, UartCapture, read_temp, md5, ...)

V, MAIN = R.V, R.MAIN
DES = {
    "r0": dict(name="R0", tree=MAIN, bit=V / "vitis/m6_sr_0602/m6_sr.runs/impl_1/design_1_wrapper.bit", ps7=None, mhz=100, version=0x53520602, fnv=0xCF947F22, ref=1311.7, t5=True),
    "r2q": dict(name="R2q", tree=V / "sandbox_R2q", bit=V / "R2q_artifacts/design_1_wrapper_R2q.bit", ps7=None, mhz=100, version=0x53522201, fnv=0x2AFBC9AE, ref=1312.0, t5=False),
    "r3q": dict(name="R3q", tree=V / "sandbox_R3q", bit=V / "R3q_artifacts/design_1_wrapper_R3q.bit", ps7=None, mhz=100, version=0x53523201, fnv=0x45DD4E2D, ref=1311.6, t5=False),
    "r0_125": dict(name="r0_125", tree=V / "sandbox_R0_125", bit=V / "R0_125_artifacts/design_1_wrapper_R0_125.bit", ps7=R.DESIGNS["r0_125"]["ps7"], mhz=125, version=0x53524201, fnv=0xCF947F22, ref=1061.85, t5=False),
    "r3q_125": dict(name="r3q_125", tree=V / "sandbox_R3q_125", bit=V / "R3q_125_artifacts/design_1_wrapper_R3q_125.bit", ps7=R.DESIGNS["r3q_125"]["ps7"], mhz=125, version=0x53524301, fnv=0x45DD4E2D, ref=1061.68, t5=False),
    "pipe": dict(name="pipe", tree=V / "sandbox_pipe", bit=V / "pipe_artifacts/design_1_wrapper_pipe.bit", ps7=R.DESIGNS["pipe"]["ps7"], mhz=125, version=0x53525301, fnv=0x45DD4E2D, ref=95.36, t5=True),
}
T3_TOL_MS = 2.0
LR960 = MAIN / "data/board/div2k_img0193_lr_960x540.raw"


def recover(d, out, why):
    print(f"!! {d['name']}: {why} -> back to the 100 MHz init with the OLD t2 ELF", flush=True)
    B = d["tree"] / "software/board/build"
    exp = d["tree"] / "data/board/div2k_img0193_expected_1920x1080.raw"
    raw = out / f"{d['name']}_recover100.raw"
    rc, o = R.xsdb_run(d, B / "sr_app_t2_before_20261028.elf", LR960, raw, out / f"{d['name']}_recover100_stats.txt", out / f"{d['name']}_recover100_xsdb.log", 60, None, 100)
    ok = rc == 0 and raw.exists() and raw.read_bytes() == exp.read_bytes()
    clk = re.search(r"CLOCK .*", o)
    print(f"   recovery run: rc={rc} byte-exact={ok} | {clk.group(0)[:160] if clk else 'no clock line'}", flush=True)


def one_design(key, out):
    d = DES[key]
    nm = d["name"]
    B = d["tree"] / "software/board/build"
    exp = d["tree"] / "data/board/div2k_img0193_expected_1920x1080.raw"
    o = out / nm
    o.mkdir(parents=True, exist_ok=True)
    tlog = o / f"{nm}_temperature.log"
    t = R.read_temp(f"before {nm}", tlog)
    if not t < R.TEMP_LIMIT_C:
        return f"temperature {t}"
    mhz = d["mhz"]
    res = {"design": nm, "mhz": mhz}
    # T1
    cap = R.UartCapture(o / f"{nm}_t1.log")
    rc, x = R.xsdb_run(d, B / "sr_app_t1.elf", "-", "-", o / f"{nm}_t1_stats.txt", o / f"{nm}_t1_xsdb.log", 60, d["ps7"], mhz)
    cap.stop()
    st = R.read_stats(o / f"{nm}_t1_stats.txt")
    print(f"[{nm}] T1: rc={rc} version={st.get('version')} result={st.get('result')} repeats={st.get('stat6')} CYCLES {st.get('stat0')}/{st.get('stat1')}/{st.get('stat2')} fclk0={st.get('fclk0_mhz')} MHz", flush=True)
    if rc != 0 or R.num(st, "version") != d["version"] or st.get("result") != "0" or "T1 PASS" not in (o / f"{nm}_t1.log").read_text(errors="replace"):
        return "T1 failed"
    # T2
    raw = o / f"{nm}_t2.raw"
    cap = R.UartCapture(o / f"{nm}_t2.log")
    rc, x = R.xsdb_run(d, B / "sr_app_t2.elf", LR960, raw, o / f"{nm}_t2_stats.txt", o / f"{nm}_t2_xsdb.log", 60, d["ps7"], mhz)
    cap.stop()
    st = R.read_stats(o / f"{nm}_t2_stats.txt")
    exact = raw.exists() and raw.read_bytes() == exp.read_bytes()
    print(f"[{nm}] T2: rc={rc} byte-exact={exact} fnv={st.get('fnv1a32')} (expected 0x{d['fnv']:08x}) version={st.get('version')} total={st.get('stat0')} us", flush=True)
    if rc != 0 or not exact or R.num(st, "fnv1a32") != d["fnv"] or R.num(st, "version") != d["version"]:
        return "T2 not byte-exact / wrong checksum or VERSION"
    # T3, 20 frames
    raw = o / f"{nm}_t3.raw"
    cap = R.UartCapture(o / f"{nm}_t3.log")
    rc, x = R.xsdb_run(d, B / "sr_app_t3_20f.elf", LR960, raw, o / f"{nm}_t3_stats.txt", o / f"{nm}_t3_xsdb.log", 3 * 26 + 30 if mhz == 100 else 108, d["ps7"], mhz)
    cap.stop()
    log = (o / f"{nm}_t3.log").read_text(errors="replace")
    frames = [int(v) for v in re.findall(r"frame \d+: total (\d+)", log)]
    exact = raw.exists() and raw.read_bytes() == exp.read_bytes()
    if len(frames) < 20:
        return f"T3: only {len(frames)} per-frame lines (rc={rc})"
    mean = statistics.mean(frames) / 1000
    spread = (max(frames) - min(frames)) / 1000
    print(f"[{nm}] T3: {len(frames)} frames mean {mean:.2f} ms (old ELF reference {d['ref']}, tolerance +-{T3_TOL_MS}), min {min(frames) / 1000:.2f} max {max(frames) / 1000:.2f}, max-min {spread:.2f} ms, byte-exact={exact}", flush=True)
    if rc != 0 or not exact:
        return "T3 run failed / not byte-exact"
    if abs(mean - d["ref"]) > T3_TOL_MS or spread > 3.0:
        return f"T3 mean {mean:.2f} ms outside {d['ref']} +- {T3_TOL_MS} ms (or max-min {spread:.2f} > 3 ms)"
    res["t3_mean"] = mean
    # T5 (error recovery) on R0 and the pipeline
    if d["t5"]:
        cap = R.UartCapture(o / f"{nm}_t5.log")
        rc, x = R.xsdb_run(d, B / "sr_app_t5.elf", "-", "-", o / f"{nm}_t5_stats.txt", o / f"{nm}_t5_xsdb.log", 120, d["ps7"], mhz)
        cap.stop()
        log = (o / f"{nm}_t5.log").read_text(errors="replace")
        ok = rc == 0 and "T5 PASS" in log
        print(f"[{nm}] T5: rc={rc} {'T5 PASS' if ok else 'NOT PASS'}", flush=True)
        for l in log.splitlines():
            if "T5" in l:
                print("     " + l.split("|", 1)[-1].strip()[:150], flush=True)
        if not ok:
            return "T5 failed"
    t = R.read_temp(f"after {nm}", tlog)
    if not t < R.TEMP_LIMIT_C:
        return f"temperature {t}"
    return None


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--out", default=str(MAIN / "data/board/2026-10-28/verify"))
    ap.add_argument("--only", default="r0,r2q,r3q,r0_125,r3q_125,pipe")
    a = ap.parse_args()
    out = Path(a.out)
    out.mkdir(parents=True, exist_ok=True)
    exp_md = (MAIN / "docs/paper/board_expected.md").read_text()
    rec = dict(re.findall(r"`(/home/[^`]+)` \| `([0-9a-f]{32})`", exp_md))
    for k in a.only.split(","):
        d = DES[k]
        for e in ("sr_app_t1.elf", "sr_app_t2.elf", "sr_app_t3_20f.elf") + (("sr_app_t5.elf",) if d["t5"] else ()):
            p = d["tree"] / "software/board/build" / e
            if e != "sr_app_t5.elf" and rec.get(str(p)) != R.md5(p):
                print(f"STOP: md5 of {p} ({R.md5(p)}) differs from board_expected.md ({rec.get(str(p))})")
                return 2
        if R.md5(d["bit"]) not in exp_md.replace("`", ""):
            print(f"STOP: bitstream md5 of {d['bit']} not in board_expected.md")
            return 2
        if d["ps7"] and R.md5(d["ps7"]) != R.PS7_125_MD5:
            print(f"STOP: {d['ps7']} md5 is not the recorded one")
            return 2
    print("md5 of all bitstreams, init scripts and production ELFs match board_expected.md (t5 ELFs are not listed there: md5 printed in the log)", flush=True)
    done = []
    for k in a.only.split(","):
        why = one_design(k, out)
        if why:
            print(f"!! STOP at {DES[k]['name']}: {why}", flush=True)
            recover(DES[k], out, why)
            return 1
        done.append(DES[k]["name"])
        print(f"== {DES[k]['name']} OK ({time.strftime('%H:%M:%S')})", flush=True)
    print(f"ALL OK: {', '.join(done)}", flush=True)
    return 0


if __name__ == "__main__":
    sys.exit(main())
