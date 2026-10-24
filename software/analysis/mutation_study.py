#!/usr/bin/env python3
"""RTL mutation study: is each deliberate RTL bug caught by the tests, and how much would it change image quality?

Run from the project root:
    .venv/bin/python software/analysis/mutation_study.py run  [--jobs 4] [--only ID,...] [--suite quick|full]   # sandboxes + RTL regression per mutant (slow)
    .venv/bin/python software/analysis/mutation_study.py eval [--md docs/paper/mutation_study.md]  # twins + PSNR/SSIM on Set5/Set14/BSD100

`run`: for every mutant a sandbox copy of the tracked files (+ a copy of data/golden) gets exactly ONE textual RTL edit, then
`hardware/verification/run_tests.sh quick` runs there (`--suite full` runs the full suite instead, about 25 min each: meant for the mutants that survived quick;
its results are kept as <ID>_full.json / <ID>_full.log and shown in the extra "Caught (full)" column); the FAIL lines are kept per test section. In the same sandbox the tile core
(HC=6) simulates the golden tiles small12 and small12b once more with +NOEXTRA +DUMP, so the mutant's real output bytes are known.
The main tree is never edited.

`eval`: each mutant has a Python "twin" (the same bug applied to the integer model). A twin is used for image metrics ONLY if it
reproduces the RTL mutant's simulated output byte for byte on both small tiles (otherwise the PSNR column says "twin not verified").
Control-path mutants (reset gates) leave the arithmetic unchanged; their twin is the clean model, verified the same way.
"""
from __future__ import annotations

import argparse
import concurrent.futures as cf
import hashlib
import json
import os
import re
import shutil
import subprocess
import sys
import time
from pathlib import Path

import numpy as np

ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(ROOT / "software" / "ai"))
WORK = Path(os.environ.get("SR_MUT_WORK", "/tmp/sr_mutation_study"))   # sandboxes + logs (outside the repo)

E = "hardware/rtl/conv_engine/conv_engine.v"
RQ = "hardware/rtl/common/requant.v"
MAC = "hardware/rtl/common/mac_unit.v"
CORE = "hardware/rtl/sr_core/sr_tile_core.v"

# id, kind, file, old text (must occur exactly once), new text, description, twin flags
MUTANTS = [
    ("R1", "datapath", RQ, "s2 <= p1 + RND;", "s2 <= p1;", "requant: rounding constant removed (floor)", {"rnd": "zero"}),
    ("R2", "datapath", RQ, "localparam signed [48:0] RND = 49'sd1 <<< (SHIFT - 1);",
     "localparam signed [48:0] RND = 49'sd1 <<< (SHIFT - 2);", "requant: rounding constant halved", {"rnd": "quarter"}),
    ("R3", "datapath", RQ, "wire signed [48:0] shifted = s2 >>> SHIFT;", "wire signed [48:0] shifted = s2 >>> (SHIFT + 1);",
     "requant: shift one bit too far", {"shift_plus": 1}),
    ("R4", "datapath", RQ, "else if (shifted > 255) y <= 8'd255;", "else if (shifted > 254) y <= 8'd254;",
     "requant: upper clamp 254 instead of 255", {"clip_hi": 254}),
    ("R5", "datapath", RQ, "if (shifted < 0)        y <= 8'd0;", "if (1'b0)        y <= 8'd0;",
     "requant: lower clamp removed (negatives wrap)", {"neg_wrap": True}),
    ("R6", "datapath", RQ, "else                    y <= shifted[7:0];", "else                    y <= {shifted[7:1], 1'b0};",
     "requant: output LSB stuck at 0", {"lsb_clear": True}),
    ("R7", "datapath", RQ, "wire signed [16:0] m_s = {1'b0, m};", "wire signed [16:0] m_s = {m[15], m};",
     "requant: multiplier M read as signed", {"m_signed": True}),
    ("A1", "datapath", MAC, "wire signed [8:0] a_s = {1'b0, a};", "wire signed [8:0] a_s = {a[7], a};",
     "MAC: activation read as signed", {"a_signed": True}),
    ("A2", "datapath", MAC, "if (v_d) acc <= (first_d ? bias : acc) + prod;", "if (v_d) acc <= (first_d ? 32'sd0 : acc) + prod;",
     "MAC: bias dropped", {"bias": "zero"}),
    ("A3", "datapath", MAC, "if (v_d) acc <= (first_d ? bias : acc) + prod;", "if (v_d) acc <= (first_d ? bias + 32'sd1 : acc) + prod;",
     "MAC: bias off by +1", {"bias": "plus1"}),
    ("A4", "datapath", MAC, "prod    <= a_s * w;", "prod    <= a_s * $signed({w[7:1], 1'b0});",
     "MAC: weight LSB dropped", {"w_lsb_clear": True}),
    ("E1", "datapath", E, "rq_m_r   <= mult_mem[rq_i];", "rq_m_r   <= mult_mem[0];",
     "engine: channel 0's multiplier used for every channel", {"m_ch0": True}),
    ("E2", "datapath", E, ".clk(clk), .v(v1), .first(first1), .bias(bias_mem[co]),", ".clk(clk), .v(v1), .first(first1), .bias(bias_mem[0]),",
     "engine: channel 0's bias used for every channel", {"bias": "ch0"}),
    ("E3", "datapath", E, "else begin ky <= ky + 1; ky_off <= ky_off + IN_W; end", "else begin ky <= ky + 1; ky_off <= ky_off + IN_W - 1; end",
     "engine: kernel row offset one pixel short (address bug)", None),
    ("C1", "datapath", CORE, "wire [3:0]    kch = {oc[1:0], oy[0], ox[0]};", "wire [3:0]    kch = {oc[1:0], ox[0], oy[0]};",
     "core: pixel-shuffle dy/dx swapped", {"shuffle_swap": True}),
    ("C2", "datapath", CORE, "assign r0_wdata = {in_data, b1, b0};", "assign r0_wdata = {b0, b1, in_data};",
     "core: input colour order reversed (BGR)", {"bgr": True}),
    ("C3", "datapath", CORE, "parameter SHIFT4 = 24,", "parameter SHIFT4 = 25,",
     "core: wrong default SHIFT of layer 4", {"shift4": 25}),
    ("K1", "control", RQ, "v1 <= v_in && !rst;", "v1 <= v_in;", "requant: reset gate of the valid pipeline removed", {}),
    ("K2", "control", E, "if (rst) rq_busy <= 1'b0;", "if (1'b0) rq_busy <= 1'b0;", "engine: requantizer busy flag not reset", {}),
    ("K3", "control", CORE, "            cycles <= 0;\n", "", "core: cycle counter not reset", {}),
]
SECTIONS = ["unit tests", "conv engine, layer by layer", "conv engine, randomized", "tile_ram_split", "full tile core",
            "AXI-Stream wrapper", "accelerator top", "board software"]


# ---------------------------------------------------------------- run: sandboxes + RTL regression
def make_sandbox(sb: Path) -> None:
    if sb.exists():
        shutil.rmtree(sb)
    sb.mkdir(parents=True)
    files = subprocess.run(["git", "ls-files", "-c", "-z"], cwd=ROOT, capture_output=True, check=True).stdout.split(b"\0")
    for f in files:
        if not f:
            continue
        src = ROOT / f.decode()
        if src.is_file():
            dst = sb / f.decode()
            dst.parent.mkdir(parents=True, exist_ok=True)
            shutil.copy2(src, dst)
    shutil.copytree(ROOT / "data" / "golden", sb / "data" / "golden", dirs_exist_ok=True)
    for link in (".venv", "data/test", "data/train"):            # read-only inputs; nothing here deletes through them
        (sb / link).symlink_to(ROOT / link)


def apply_mutant(sb: Path, m) -> None:
    mid, _, f, old, new, *_ = m
    p = sb / f
    s = p.read_text()
    n = s.count(old)
    if n != 1:
        raise RuntimeError(f"{mid}: pattern found {n} times in {f}")
    p.write_text(s.replace(old, new))


def dump_core(sb: Path, tag: str) -> dict:
    """Simulate the HC=6 core on small12 / small12b once (+NOEXTRA) and dump the output bytes."""
    rtl = " ".join(f"hardware/rtl/{x}" for x in ("common/mac_unit.v", "common/requant.v", "common/weight_rom.v",
                                                  "common/tile_ram_split.v", "conv_engine/conv_engine.v", "sr_core/sr_tile_core.v"))
    out = {}
    exe = sb / f"core6_{tag}.vvp"
    b = subprocess.run(f"iverilog -g2012 -I . -o {exe} -P tb_sr_tile.HC=6 {rtl} hardware/verification/tb/tb_sr_tile.v",
                       shell=True, cwd=sb, capture_output=True, text=True)
    if b.returncode:
        return {"build_error": b.stderr[-500:]}
    for t in ("small12", "small12b"):
        d = sb / f"dump_{t}.hex"
        if d.exists():
            d.unlink()
        r = subprocess.run(["timeout", "300", "vvp", str(exe), f"+TILE={t}", "+NOEXTRA", f"+DUMP={d}"], cwd=sb,
                           capture_output=True, text=True)
        out[t] = d.read_text().split() if d.exists() else None
        out[t + "_log"] = r.stdout[-300:]
    return out


def parse_fails(log: str) -> dict:
    """FAIL lines per test section.  The seam test has no header of its own (it runs at the end of the board-software section);
    its lines are recognised by their HC=8 tile names and filed under 'seam test'."""
    fails, sec = {}, "?"
    for line in log.splitlines():
        if line.startswith("== "):
            sec = next((s for s in SECTIONS if line[3:].startswith(s)), line[3:40])
            continue
        seam = line.startswith(("[seam", "FAIL seam", "FAIL sr_tile_core HC=8", "hc8_t"))
        bad = line.startswith("FAIL") or (line.startswith("[seam") and not line.rstrip().endswith(" 0 failed"))
        if bad:
            fails.setdefault("seam test" if seam else sec, []).append(line[:160])
    return fails


def run_one(m, suite: str = "quick") -> dict:
    mid = m[0]
    tag = "" if suite == "quick" else "_full"           # quick keeps the original file names
    sb = WORK / (mid + tag)
    t0 = time.time()
    make_sandbox(sb)
    if mid != "CLEAN":
        apply_mutant(sb, m)
    r = subprocess.run(["timeout", "1800" if suite == "quick" else "5400", "hardware/verification/run_tests.sh", suite], cwd=sb, capture_output=True, text=True)
    log = r.stdout + r.stderr
    (WORK / f"{mid}_{suite}.log").write_text(log)
    fails = parse_fails(log)
    summ = re.search(r"summary: (\d+) test runs passed, (\d+) failed", log)
    dumps = dump_core(sb, mid)
    res = dict(id=mid, exit=r.returncode, passed=int(summ.group(1)) if summ else None, failed=int(summ.group(2)) if summ else None,
               fails=fails, dumps=dumps, seconds=round(time.time() - t0))
    (WORK / f"{mid}{tag}.json").write_text(json.dumps(res))
    shutil.rmtree(sb)
    return res


def cmd_run(a) -> None:
    WORK.mkdir(parents=True, exist_ok=True)
    todo = [("CLEAN", "clean", "", "", "", "no mutation", {})] + MUTANTS
    if a.only:
        keep = set(a.only.split(","))
        todo = [m for m in todo if m[0] in keep]
    with cf.ThreadPoolExecutor(a.jobs) as ex:
        for res in ex.map(lambda m: run_one(m, a.suite), todo):
            print(f"{res['id']}: exit {res['exit']}, {res['passed']} passed / {res['failed']} failed, "
                  f"sections failing: {sorted(res['fails'])}, {res['seconds']} s", flush=True)


# ---------------------------------------------------------------- eval: twins + image metrics
def twin_net(flags: dict):
    """Layer list for the twin forward pass (integer_reference conventions, int64 maths)."""
    from quantization.integer_reference import LAYER_SPEC
    z = np.load(ROOT / "software/ai/quantization/qparams.npz")
    layers = []
    for name, cin, cout, k, dw in LAYER_SPEC:
        w = z[f"{name}_w"].astype(np.int64)
        b = z[f"{name}_b"].astype(np.int64)
        m = z[f"{name}_m"].astype(np.int64)
        sh = int(z[f"{name}_shift"])
        if flags.get("w_lsb_clear"):
            w = w & -2
        if flags.get("bias") == "zero":
            b = np.zeros_like(b)
        elif flags.get("bias") == "plus1":
            b = b + 1
        elif flags.get("bias") == "ch0":
            b = np.full_like(b, b[0])
        if flags.get("m_ch0"):
            m = np.full_like(m, m[0])
        if flags.get("m_signed"):
            m = np.where(m >= 32768, m - 65536, m)
        if name == "L4" and "shift4" in flags:
            sh = flags["shift4"]
        layers.append((w, b, m, sh, dw))
    return layers


def twin_requant(acc, m, sh, f):
    """The RTL if/else chain: if (y < 0) 0; else if (y > T) H; else y[7:0]  (T = H = 255 normally)."""
    rnd = {"zero": 0, "quarter": 1 << (sh - 2)}.get(f.get("rnd"), 1 << (sh - 1))
    y = (acc * m[:, None, None] + rnd) >> (sh + f.get("shift_plus", 0))
    hi = f.get("clip_hi", 255)
    body = y & 255
    if f.get("lsb_clear"):
        body = body & ~1
    out = np.where(y > hi, hi, body)
    if not f.get("neg_wrap"):
        out = np.where(y < 0, 0, out)
    return out


def twin_forward(layers, f, x_hwc_padded):
    """Valid convs on an already padded uint8 HWC input -> (2H x 2W x 3) uint8, with the twin's bugs."""
    x = x_hwc_padded.astype(np.int64).transpose(2, 0, 1)
    if f.get("bgr"):
        x = x[::-1].copy()
    if f.get("a_signed"):
        signed = lambda t: np.where(t >= 128, t - 256, t)  # noqa: E731
    else:
        signed = lambda t: t  # noqa: E731
    for w, b, m, sh, dw in layers:
        k = w.shape[2]
        h, wd = x.shape[1] - k + 1, x.shape[2] - k + 1
        xs = signed(x)
        acc = np.zeros((w.shape[0], h, wd), np.int64) + b[:, None, None]
        for ky in range(k):
            for kx in range(k):
                win = xs[:, ky:ky + h, kx:kx + wd]
                tap = w[:, :, ky, kx]
                if dw:
                    acc += win * tap[:, 0][:, None, None]
                else:
                    acc += np.einsum("oc,chw->ohw", tap, win)
        x = twin_requant(acc, m, sh, f)
    c4, h, wd = x.shape
    out = np.zeros((h * 2, wd * 2, 3), np.uint8)
    for c in range(3):
        for dy in range(2):
            for dx in range(2):
                kk = 4 * c + (2 * dx + dy if f.get("shuffle_swap") else 2 * dy + dx)
                out[dy::2, dx::2, c] = x[kk]
    return out


def read_hex(p: Path):
    return [int(v, 16) for v in p.read_text().split()]


def cmd_eval(a) -> None:
    from dataset.pairs import list_images, load_rgb, make_pair
    from evaluation.metrics import psnr_rgb, psnr_y, ssim_y
    from quantization.integer_reference import QNet, pad_replicate, upscale

    golden_in = {t: np.array(read_hex(ROOT / f"data/golden/{t}_in.hex"), np.uint8).reshape(12, 12, 3) for t in ("small12", "small12b")}
    images = []
    for s in ("Set5", "Set14", "BSD100"):
        for p in list_images(ROOT / "data" / "test" / "HR" / s):
            lr, hr = make_pair(load_rgb(p), 2)
            images.append((s, p.stem, lr, hr))
    net = QNet.load(ROOT / "software/ai/quantization/qparams.npz")
    clean = {}
    for s, n, lr, hr in images:
        sr = upscale(net, lr)
        clean[(s, n)] = (psnr_y(hr, sr, 2), ssim_y(hr, sr, 2), psnr_rgb(hr, sr), hashlib.sha1(sr.tobytes()).hexdigest())

    rows = []
    for m in [("CLEAN", "clean", "", "", "", "no mutation", {})] + MUTANTS:
        mid, kind, f, _, _, desc, flags = m
        jf = WORK / f"{mid}.json"
        if not jf.exists():
            rows.append(dict(id=mid, kind=kind, desc=desc, status="not run"))
            continue
        res = json.loads(jf.read_text())
        log = (WORK / f"{mid}_quick.log").read_text()
        row = dict(id=mid, kind=kind, file=f, desc=desc, exit=res["exit"], passed=res["passed"], failed=res["failed"],
                   caught=res["exit"] != 0, sections=sorted(parse_fails(log)))
        jf_full = WORK / f"{mid}_full.json"
        if jf_full.exists():
            rf = json.loads(jf_full.read_text())
            row.update(exit_full=rf["exit"], passed_full=rf["passed"], failed_full=rf["failed"], caught_full=rf["exit"] != 0)
        twin_ok = None
        if flags is not None:
            layers = twin_net(flags)
            twin_ok = True
            for t, x in golden_in.items():
                rtl = res["dumps"].get(t)
                want = twin_forward(layers, flags, x).reshape(-1).tolist()
                if rtl is None or [int(v, 16) for v in rtl] != want:
                    twin_ok = False
        row["twin"] = {None: "none", True: "verified", False: "NOT verified"}[twin_ok]
        if twin_ok:
            layers = twin_net(flags)
            dp, ds, dr, changed = [], [], [], 0
            for s, n, lr, hr in images:
                sr = twin_forward(layers, flags, pad_replicate(lr))
                py, sy, pr = psnr_y(hr, sr, 2), ssim_y(hr, sr, 2), psnr_rgb(hr, sr)
                c = clean[(s, n)]
                dp.append(py - c[0]); ds.append(sy - c[1]); dr.append(pr - c[2])
                changed += int(hashlib.sha1(sr.tobytes()).hexdigest() != c[3])
            row.update(d_psnr_y_mean=float(np.mean(dp)), d_psnr_y_worst=float(min(dp)), d_ssim_y_mean=float(np.mean(ds)),
                       d_psnr_rgb_mean=float(np.mean(dr)), images_changed=changed)
        rows.append(row)
        print(mid, row.get("caught"), row["twin"], row.get("d_psnr_y_mean"), flush=True)
    (WORK / "eval.json").write_text(json.dumps(rows, indent=1))
    text = report(rows, len(images))
    print(text)
    if a.md:
        Path(a.md).write_text(text)


def report(rows, n_img: int) -> str:
    L = ["# RTL mutation study: caught by the tests vs effect on image quality\n",
         f"Generated by `software/analysis/mutation_study.py` on {time.strftime('%Y-%m-%d')}. Each mutant = one textual edit of the RTL, "
         "run in a sandbox with `run_tests.sh quick` (bit-exact unit/layer/core tests, randomized layers, reset/abort sweeps, AXI wrapper/top, "
         f"20-tile seam test). Image effect = the mutant's Python twin on all {n_img} test images (Set5, Set14, BSD100), only when the twin "
         "reproduces the RTL mutant's simulated output byte-exactly on the golden tiles small12 and small12b. dPSNR/dSSIM = mutant minus clean "
         "INT8 model (mean over images; worst = most negative).\n",
         "| ID | Kind | Mutation | Caught (quick) | Caught (full) | Failing sections (quick) | Twin | dPSNR-Y mean | dPSNR-Y worst | dSSIM-Y mean | Images changed |",
         "|---|---|---|---|---|---|---|---|---|---|---|"]
    for r in rows:
        if r.get("status") == "not run":
            L.append(f"| {r['id']} | {r['kind']} | {r['desc']} | not run | | | | | | | |")
            continue
        caught = "baseline" if r["id"] == "CLEAN" else ("yes" if r["caught"] else "**NO**")
        if "d_psnr_y_mean" in r:
            num = (f"{r['d_psnr_y_mean']:+.4f} | {r['d_psnr_y_worst']:+.4f} | {r['d_ssim_y_mean']:+.5f} | "
                   f"{r['images_changed']}/{n_img}")
        else:
            num = "- | - | - | -"
        full = "not run (caught by quick)" if r["id"] != "CLEAN" and r["caught"] and "caught_full" not in r else (
            "-" if "caught_full" not in r else ("baseline" if r["id"] == "CLEAN" else ("yes" if r["caught_full"] else "**NO**")))
        L.append(f"| {r['id']} | {r['kind']} | {r['desc']} | {caught} | {full} | {', '.join(r['sections']) or '-'} | {r['twin']} | {num} |")
    muts = [r for r in rows if r["id"] != "CLEAN" and r.get("status") != "not run"]
    small = [r for r in muts if "d_psnr_y_mean" in r and abs(r["d_psnr_y_mean"]) < 0.01 and abs(r["d_psnr_y_worst"]) < 0.01]
    small_caught = [r for r in small if r["caught"]]
    L.append(f"\n**Counts:** {len(muts)} mutants run, {sum(r['caught'] for r in muts)} caught; "
             f"{sum('d_psnr_y_mean' in r for r in muts)} with a verified twin; "
             f"{len(small)} change PSNR-Y by < 0.01 dB (mean and worst image), of which {len(small_caught)} are caught "
             f"({', '.join(r['id'] for r in small_caught) or 'none'}).")
    surv = [r for r in muts if not r["caught"]]
    L.append(f"Survivors of the quick suite: {', '.join(r['id'] for r in surv) or 'none'}. Of these, run with the full suite: "
             f"{', '.join(r['id'] + (' (caught)' if r.get('caught_full') else ' (NOT caught)') for r in surv if 'caught_full' in r) or 'none'}.")
    clean = next((r for r in rows if r["id"] == "CLEAN"), None)
    if clean:
        L.append(f"Clean design in the same flow: exit {clean['exit']}, {clean['passed']} passed / {clean['failed']} failed; twin {clean['twin']}.")
    return "\n".join(L) + "\n"


def main() -> None:
    ap = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    sp = ap.add_subparsers(dest="cmd", required=True)
    r = sp.add_parser("run")
    r.add_argument("--jobs", type=int, default=4)
    r.add_argument("--only", help="comma-separated mutant IDs (CLEAN = unmutated)")
    r.add_argument("--suite", choices=("quick", "full"), default="quick")
    e = sp.add_parser("eval")
    e.add_argument("--md")
    a = ap.parse_args()
    cmd_run(a) if a.cmd == "run" else cmd_eval(a)


if __name__ == "__main__":
    main()
