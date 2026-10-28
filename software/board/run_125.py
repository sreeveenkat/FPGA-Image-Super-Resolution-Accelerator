#!/usr/bin/env python3
"""Step 2 of the 2026-10-28 board session: run one design at its REAL 125 MHz PL clock and check it against its integer model.

    .venv/bin/python software/board/run_125.py <r0_125|r3q_125|pipe> [--out data/board/2026-10-28] [--only t1,t2,t3,sets]

What it does, in order (stops at the first unexpected result, restores the 100 MHz platform init, proves the board is healthy, and exits non-zero):
  0. md5 of bitstream, XSA init script, every ELF against docs/paper/board_expected.md; die temperature (Vivado XADC read, only BETWEEN xsdb runs).
  1. T1 (golden tile), T2 (960x540 frame, byte-exact against the tree's expected file), T3 (20 frames, UART per-frame lines), each through run_board_clk.tcl with the
     design's OWN ps7_init.tcl (env SR_PS7_INIT) and SR_EXPECT_MHZ=125: the clock registers are read back after init and the run is refused when FCLK0 != 125 MHz.
  2. all 119 test images through the T2 ELF, byte-exact against <stem>_exp.raw; die temperature after images 40 and 80 and at the end (abort above 70 C).
Per image: the wait for the ready marker is bounded (3 x the expected time + 4 s), and an image whose measured total time exceeds 3 x its expected time stops the design.
Expected time per image = the design's own T3 mean of THIS session x (tiles/135 for tiled designs, (W+4)(H+4)/(964x544) for the pipeline), floor 3 ms.
Nothing here writes QSPI, SD or eFuses; it uses JTAG (xsdb) and the XADC read only.  Created 2026-10-28.
"""
import argparse
import csv
import hashlib
import math
import os
import re
import signal
import statistics
import struct
import subprocess
import sys
import time
from pathlib import Path

V = Path.home() / "Desktop/venkat"
MAIN = V / "sem_project_all"
SCRATCH = Path("/tmp/claude-1000/-home-sreevenkat-Desktop-venkat-sem-project-all/1ad352c1-a6cb-46e2-a235-f590ad2ef8c8/scratchpad/ps7")
PLATFORM_PS7 = V / "vitis_workspace/sr_app/_ide/psinit/ps7_init.tcl"
SETTINGS_VITIS = Path.home() / "Desktop/vivado_install/Vitis/2024.1/settings64.sh"
SETTINGS_VIVADO = Path.home() / "Desktop/vivado_install/Vivado/2024.1/settings64.sh"
TEMP_LIMIT_C = 70.0

DESIGNS = {
    "r0_125": dict(tree=V / "sandbox_R0_125", bit=V / "R0_125_artifacts/design_1_wrapper_R0_125.bit", ps7=SCRATCH / "r0_125/ps7_init.tcl", version=0x53524201, fnv=0xCF947F22,
                   sets=MAIN / "data/board/testsets", kind="tiled",
                   pred_cycles_ms=926205 * 135 / 125e3, pred_overhead_ms=61.0),
    "r3q_125": dict(tree=V / "sandbox_R3q_125", bit=V / "R3q_125_artifacts/design_1_wrapper_R3q_125.bit", ps7=SCRATCH / "r3q_125/ps7_init.tcl", version=0x53524301, fnv=0x45DD4E2D,
                    sets=V / "sandbox_R3q_125/data/board/testsets", kind="tiled",
                    pred_cycles_ms=926205 * 135 / 125e3, pred_overhead_ms=61.0),
    "pipe": dict(tree=V / "sandbox_pipe", bit=V / "pipe_artifacts/design_1_wrapper_pipe.bit", ps7=SCRATCH / "pipe/ps7_init.tcl", version=0x53525301, fnv=0x45DD4E2D,
                 sets=V / "sandbox_pipe/data/board/testsets", kind="pipe",
                 pred_cycles_ms=8398481 / 125e3, pred_overhead_ms=28.0),
}
PS7_125_MD5 = "d2a7789c85395e17649026335f23d938"
PS7_PLATFORM_MD5 = "86bd78c7e9b40933e57e4e22f8bc7eb6"


def md5(p):
    return hashlib.md5(Path(p).read_bytes()).hexdigest()


def fnv1a32(b):
    h = 0x811C9DC5
    for x in b:
        h = ((h ^ x) * 0x01000193) & 0xFFFFFFFF
    return h


def sh(cmd, timeout, env_extra=None, cwd=None):
    """Run a command under bash with Vitis settings, stdin closed, hard timeout; returns (rc, output)."""
    env = dict(os.environ)
    env.update({k: str(v) for k, v in (env_extra or {}).items()})
    full = f"source {SETTINGS_VITIS} >/dev/null 2>&1; source {SETTINGS_VIVADO} >/dev/null 2>&1; {cmd}"
    try:
        r = subprocess.run(["bash", "-c", full], cwd=cwd or MAIN, env=env, stdin=subprocess.DEVNULL, capture_output=True, text=True, timeout=timeout)
        return r.returncode, r.stdout + r.stderr
    except subprocess.TimeoutExpired as e:
        return 124, (e.stdout or b"").decode() if isinstance(e.stdout, bytes) else (e.stdout or "")


class UartCapture:
    def __init__(self, path):
        self.path = path
        self.p = subprocess.Popen([str(MAIN / ".venv/bin/python"), str(MAIN / "software/board/uart_capture.py"), "--out", str(path), "--port", "/dev/ttyACM0"],
                                  stderr=open(str(path) + ".err", "w"), stdin=subprocess.DEVNULL)
        for _ in range(60):
            if Path(path).exists() and "# capture started" in Path(path).read_text(errors="replace"):
                return
            time.sleep(0.1)
        self.stop()
        raise RuntimeError("UART capture did not start")

    def stop(self):
        time.sleep(1.5)
        self.p.send_signal(signal.SIGTERM)       # by PID
        try:
            self.p.wait(timeout=10)
        except subprocess.TimeoutExpired:
            self.p.kill()


def read_temp(label, log):
    rc, out = sh(f"timeout --foreground -k 5 120 vivado -mode batch -nolog -nojournal -source {MAIN}/software/board/xadc_temp.tcl", 150)
    m = re.search(r"^XADC_TEMP_C\s+([0-9.]+)", out, re.M)
    v = re.search(r"^XADC_VCCINT\s+([0-9.]+)\s+VCCAUX\s+([0-9.]+)", out, re.M)
    t = float(m.group(1)) if m else float("nan")
    line = f"{time.strftime('%H:%M:%S')} {label}: XADC_TEMP_C {t}" + (f" VCCINT {v.group(1)} VCCAUX {v.group(2)}" if v else "")
    print(line, flush=True)
    with open(log, "a") as f:
        f.write(line + "\n")
    return t


def xsdb_run(d, elf, inp, outraw, stats, xlog, timeout_s, ps7=None, mhz=None):
    env = {"SR_BIT": d["bit"], "SR_TIMEOUT_S": int(timeout_s)}
    if ps7:
        env["SR_PS7_INIT"] = ps7
    if mhz:
        env["SR_EXPECT_MHZ"] = mhz
    rc, out = sh(f"timeout --foreground -k 5 {int(timeout_s) + 90} xsdb {MAIN}/software/board/run_board_clk.tcl {elf} {inp} {outraw} {stats}", timeout_s + 120, env)
    Path(xlog).write_text(out)
    return rc, out


def read_stats(p):
    d = {}
    if Path(p).exists():
        for l in Path(p).read_text().splitlines():
            if "=" in l:
                k, v = l.split("=", 1)
                d[k] = v
    return d


def num(d, k):
    try:
        return int(d[k], 0)
    except (KeyError, ValueError):
        return None


def tiles_of(w, h):
    return math.ceil(w / 64) * math.ceil(h / 64)


def srim_wh(p):
    b = Path(p).read_bytes()[:16]
    return struct.unpack("<II", b[4:12])


def recover_100(d, name, out, why):
    """Back to the 100 MHz platform init and one image byte-exact."""
    print(f"!! {name}: {why} -> returning to the 100 MHz init", flush=True)
    elf = d["tree"] / "software/board/build/sr_app_t2.elf"
    exp = d["tree"] / "data/board/div2k_img0193_expected_1920x1080.raw"
    raw = out / f"{name}_recover100.raw"
    rc, o = xsdb_run(d, elf, MAIN / "data/board/div2k_img0193_lr_960x540.raw", raw, out / f"{name}_recover100_stats.txt", out / f"{name}_recover100_xsdb.log", 60, None, 100)
    ok = rc == 0 and raw.exists() and raw.read_bytes() == exp.read_bytes()
    clk = re.search(r"CLOCK .*", o)
    print(f"   100 MHz recovery run: rc={rc} byte-exact={ok} | {clk.group(0)[:200] if clk else 'no clock line'}", flush=True)
    return ok


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("design", choices=DESIGNS)
    ap.add_argument("--out", default=str(MAIN / "data/board/2026-10-28"))
    ap.add_argument("--only", default="t1,t2,t3,sets")
    ap.add_argument("--limit", type=int, default=0, help="only the first N images (test of the script)")
    ap.add_argument("--test100", action="store_true", help="script test at the 100 MHz platform init (expects 100 MHz, output folder <design>_test100); never changes the clock")
    a = ap.parse_args()
    name, d = a.design, dict(DESIGNS[a.design])
    MHZ = 100 if a.test100 else 125
    if a.test100:
        d["ps7"] = PLATFORM_PS7
    out = Path(a.out) / (name + ("_test100" if a.test100 else ""))
    out.mkdir(parents=True, exist_ok=True)
    stages = a.only.split(",")
    tlog = out / f"{name}_temperature.log"
    t3_ms_ref = None
    summary = []
    B = d["tree"] / "software/board/build"

    # ---- 0. md5 checks and temperature
    exp_md = (MAIN / "docs/paper/board_expected.md").read_text()
    rec = dict(re.findall(r"`(/home/[^`]+)` \| `([0-9a-f]{32})`", exp_md))
    need = [d["bit"]] + [B / e for e in ("sr_app_t1.elf", "sr_app_t2.elf", "sr_app_t3_20f.elf")]
    for p in need:
        if rec.get(str(p)) != md5(p):
            print(f"STOP: md5 of {p} = {md5(p)} but board_expected.md has {rec.get(str(p))}")
            return 2
    if md5(d["ps7"]) != (PS7_PLATFORM_MD5 if a.test100 else PS7_125_MD5):
        print(f"STOP: {d['ps7']} md5 {md5(d['ps7'])} is not the recorded one")
        return 2
    print(f"md5 OK: bitstream {md5(d['bit'])[:8]}, ps7_init (XSA) {md5(d['ps7'])[:8]}, ELFs", [md5(B / e)[:8] for e in ("sr_app_t1.elf", "sr_app_t2.elf", "sr_app_t3_20f.elf")], flush=True)
    t = read_temp(f"before {name}", tlog)
    if not t < TEMP_LIMIT_C:
        print("STOP: temperature unreadable or above the limit")
        return 2
    lr960 = MAIN / "data/board/div2k_img0193_lr_960x540.raw"
    exp960 = d["tree"] / "data/board/div2k_img0193_expected_1920x1080.raw"
    fail = None

    # ---- 1. T1, T2, T3
    if "t1" in stages and not fail:
        cap = UartCapture(out / f"{name}_t1.log")
        rc, o = xsdb_run(d, B / "sr_app_t1.elf", "-", "-", out / f"{name}_t1_stats.txt", out / f"{name}_t1_xsdb.log", 60, d["ps7"], MHZ)
        cap.stop()
        st = read_stats(out / f"{name}_t1_stats.txt")
        clk = re.search(r"CLOCK .*", o)
        print(f"T1: rc={rc} {clk.group(0) if clk else 'NO CLOCK LINE'}", flush=True)
        print(f"T1: result={st.get('result')} version={st.get('version')} CYCLES min/max/mean {st.get('stat0')}/{st.get('stat1')}/{st.get('stat2')} repeats={st.get('stat6')} fclk0_mhz={st.get('fclk0_mhz')}", flush=True)
        if rc != 0 or num(st, "version") != d["version"] or st.get("result") != "0" or "T1 PASS" not in (out / f"{name}_t1.log").read_text(errors="replace"):
            fail = "T1 failed (see the logs)"
        summary.append(("T1", st))
    if "t2" in stages and not fail:
        raw = out / f"{name}_t2.raw"
        cap = UartCapture(out / f"{name}_t2.log")
        rc, o = xsdb_run(d, B / "sr_app_t2.elf", lr960, raw, out / f"{name}_t2_stats.txt", out / f"{name}_t2_xsdb.log", 60, d["ps7"], MHZ)
        cap.stop()
        st = read_stats(out / f"{name}_t2_stats.txt")
        exact = raw.exists() and raw.read_bytes() == exp960.read_bytes()
        print(f"T2: rc={rc} byte-exact={exact} fnv={st.get('fnv1a32')} (expected 0x{d['fnv']:08x}) version={st.get('version')} total={st.get('stat0')} us DMA+compute={st.get('stat3')} us "
              f"CYCLES min/max/mean {st.get('stat4')}/{st.get('stat5')}/{st.get('stat6')} fclk0_mhz={st.get('fclk0_mhz')}", flush=True)
        if rc != 0 or not exact or num(st, "fnv1a32") != d["fnv"] or num(st, "version") != d["version"]:
            fail = "T2 not byte-exact / wrong checksum or VERSION"
        summary.append(("T2", st))
    if "t3" in stages and not fail:
        cap = UartCapture(out / f"{name}_t3.log")
        raw = out / f"{name}_t3.raw"
        rc, o = xsdb_run(d, B / "sr_app_t3_20f.elf", lr960, raw, out / f"{name}_t3_stats.txt", out / f"{name}_t3_xsdb.log", 3 * 26 + 30, d["ps7"], MHZ)
        cap.stop()
        log = (out / f"{name}_t3.log").read_text(errors="replace")
        frames = [int(x) for x in re.findall(r"frame \d+: total (\d+)", log)]
        st = read_stats(out / f"{name}_t3_stats.txt")
        exact = raw.exists() and raw.read_bytes() == exp960.read_bytes()
        if len(frames) >= 20:
            t3_ms_ref = statistics.mean(frames) / 1000
            print(f"T3: rc={rc} {len(frames)} frames: mean {t3_ms_ref:.1f} ms min {min(frames) / 1000:.1f} max {max(frames) / 1000:.1f} ms byte-exact={exact} fnv={st.get('fnv1a32')} fclk0_mhz={st.get('fclk0_mhz')}", flush=True)
            for l in log.splitlines():
                if "T3:" in l:
                    print("   " + l.split("|", 1)[-1].strip(), flush=True)
        else:
            print(f"T3: rc={rc} only {len(frames)} per-frame lines", flush=True)
        if rc != 0 or not exact or len(frames) < 20:
            fail = "T3 failed (rc, byte-exactness or per-frame lines)"
        summary.append(("T3", st))
        read_temp(f"after T3 {name}", tlog)

    # ---- 2. 119 images
    results = []
    if "sets" in stages and not fail:
        if t3_ms_ref is None:
            print("STOP: the per-image time bound needs this session's T3 mean (run t3 first)")
            return 2
        imgs = [(s, p) for s in ("Set5", "Set14", "BSD100") for p in sorted((d["sets"] / s).glob("*_lr.raw"))]
        if a.limit:
            imgs = imgs[:a.limit]
        print(f"images: {len(imgs)} from {d['sets']}", flush=True)
        cap = UartCapture(out / f"{name}_sets.log")
        n_ok = 0
        for i, (s, p) in enumerate(imgs, 1):
            w, h = srim_wh(p)
            tl = tiles_of(w, h)
            expect_ms = max(3.0, t3_ms_ref * (tl / 135 if d["kind"] == "tiled" else (w + 4) * (h + 4) / (964 * 544)))
            tmo = 3 * expect_ms / 1000 + 4
            stem = p.name[:-7]
            raw = out / "tmp_image.raw"
            statsf = out / "tmp_stats.txt"
            if raw.exists():
                raw.unlink()
            rc, o = xsdb_run(d, B / "sr_app_t2.elf", p, raw, statsf, out / "tmp_xsdb.log", tmo, d["ps7"], MHZ)
            st = read_stats(statsf)
            exact = raw.exists() and raw.read_bytes() == (d["sets"] / s / f"{stem}_exp.raw").read_bytes()
            total_ms = (num(st, "stat0") or 0) / 1000
            row = dict(n=i, set=s, image=stem, w=w, h=h, tiles=tl, exact=exact, rc=rc, version=st.get("version"), fnv=st.get("fnv1a32"), total_ms=total_ms, pad_us=num(st, "stat1"),
                       copy_us=num(st, "stat2") if d["kind"] == "tiled" else "", dma_compute_us=num(st, "stat3"), cyc_min=num(st, "stat4"), cyc_max=num(st, "stat5"), cyc_mean=num(st, "stat6"),
                       expect_ms=round(expect_ms, 2), fclk0_mhz=st.get("fclk0_mhz"))
            results.append(row)
            bad = None
            if rc != 0 or st.get("result") != "0":
                bad = f"rc={rc} result={st.get('result')} ({(re.findall(r'(?:ERROR|rror).*', o) or [''])[0][:120]})"
            elif num(st, "version") != d["version"]:
                bad = f"VERSION {st.get('version')}"
            elif st.get("fclk0_mhz") is None or abs(float(st["fclk0_mhz"]) - MHZ) > 0.5:
                bad = f"clock {st.get('fclk0_mhz')}"
            elif not exact:
                bad = "NOT byte-exact"
            elif total_ms > 3 * expect_ms:
                bad = f"took {total_ms:.1f} ms > 3 x expected {expect_ms:.1f} ms"
            if bad:
                fail = f"image {i} {s}/{stem}: {bad}"
                break
            n_ok += 1
            if i % 10 == 0:
                print(f"  {i}/{len(imgs)} ok (last {s}/{stem}: {total_ms:.1f} ms, expected {expect_ms:.1f})", flush=True)
            if i in (40, 80) or i == len(imgs):
                cap.stop()
                tt = read_temp(f"after image {i} {name}", tlog)
                if not tt < TEMP_LIMIT_C:
                    fail = f"die temperature {tt} C at image {i}"
                    break
                if i != len(imgs):
                    cap = UartCapture(out / f"{name}_sets_{i}.log")
        else:
            cap = None
        try:
            cap.stop()
        except Exception:
            pass
        with open(out / f"{name}_images.csv", "w", newline="") as f:
            if results:
                wr = csv.DictWriter(f, fieldnames=list(results[0]))
                wr.writeheader()
                wr.writerows(results)
        print(f"IMAGES {name}: {n_ok} byte-exact of {len(imgs)} run ({len(results)} attempted)", flush=True)
        if results:
            ms = [r["total_ms"] for r in results if r["exact"]]
            print(f"  ms per frame over the images: mean {statistics.mean(ms):.2f} min {min(ms):.2f} max {max(ms):.2f}; sum tiles {sum(r['tiles'] for r in results)}; "
                  f"ms per tile (sum) {sum(ms) / sum(r['tiles'] for r in results):.3f}", flush=True)
            cy = [r["cyc_mean"] for r in results if r["cyc_mean"] is not None]
            print(f"  CYCLES (per tile for tiled / per frame for pipe) over images: min {min(cy)} max {max(cy)}", flush=True)
        Path(out / "tmp_image.raw").unlink(missing_ok=True)

    if fail:
        print(f"!! FAILURE in {name}: {fail}", flush=True)
        recover_100(d, name, out, fail)
        read_temp(f"after recovery {name}", tlog)
        return 1
    print(f"{name}: all requested stages passed", flush=True)
    return 0


if __name__ == "__main__":
    sys.exit(main())
