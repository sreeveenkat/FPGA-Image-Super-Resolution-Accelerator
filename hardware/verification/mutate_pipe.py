"""Mutation test of the whole-frame pipeline RTL (branch `pipe`): apply ONE deliberate defect to a copy of an RTL file, run a set of the pipeline tests
(fast first, stop at the first FAIL), and require that some test FAILS.  An unmutated control run must pass every test of the set.
Run from anywhere:  .venv/bin/python hardware/verification/mutate_pipe.py [--jobs N] [--only ID,...]      (~20 min with 4 jobs)
A mutant that no test catches is printed as SURVIVED.  A test that hangs past its timeout counts as caught (a hang is a visible failure on the board too).
Exit code 0 only if the control passed and every mutant was caught.
"""
import argparse
import shutil
import subprocess
import sys
import tempfile
from concurrent.futures import ThreadPoolExecutor
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]
RTL = ROOT / "hardware" / "rtl"
TB = ROOT / "hardware" / "verification" / "tb"

# (id, file, old, new, description[, "EQUIV: reason"]) ; an EQUIV mutant must SURVIVE (so a wrong equivalence claim is noticed)
MUTANTS = [
    ("S1", "pipe/pipe_stage.v", "wire        produce = (ix >= K - 1) && (iy >= K - 1);", "wire        produce = (ix >= K - 1) && (iy >= K - 2);", "window produced one row too early"),
    ("S2", "pipe/pipe_stage.v", "if (d1_v) lb[d1_x] <= {lb_q[IWB-1:0], d1_p};", "if (d1_v) lb[d1_x] <= {d1_p, lb_q[IWB-1:0]};", "line-buffer rows swapped"),
    ("S3", "pipe/pipe_stage.v", "(ky == 0) ? lb_q[IWB +: IWB] : (ky == 1) ? lb_q[0 +: IWB] : d1_p;", "(ky == 0) ? lb_q[0 +: IWB] : (ky == 1) ? lb_q[IWB +: IWB] : d1_p;", "window rows 0/1 swapped"),
    ("S4", "pipe/pipe_stage.v", "if (s == NS - 1) run <= 1'b0;", "if (s == NS - 2) run <= 1'b0;", "slot counter stops one slot early"),
    ("S5", "pipe/pipe_stage.v", "assign px_start = win_rdy && out_ok && (!run || s == NS - 1);", "assign px_start = win_rdy && (!run || s == NS - 1);", "consumer room (out_ok) ignored"),
    ("S6", "pipe/pipe_stage.v", "assign px_start = win_rdy && out_ok && (!run || s == NS - 1);", "assign px_start = win_rdy && out_ok && !run;", "one idle cycle per pixel (throughput only, output still exact)"),
    ("S7", "pipe/pipe_stage.v", "if (px_start) hold <= 1'b0;", "if (px_start && 1'b0) hold <= 1'b0;", "input never released after a window (hang)"),
    ("S8", "pipe/pipe_stage.v", "bias_r <= bias_mem[sd[D-1]];", "bias_r <= bias_mem[sd[D]];", "output-serial bias one slot late"),
    ("S9", "pipe/pipe_stage.v", "acc[gi] <= ((sd[D] == 4'd0) ? bias_mem[gi] : acc[gi])", "acc[gi] <= ((sd[D] == 4'd1) ? bias_mem[gi] : acc[gi])", "input-serial accumulator restarts at slot 1"),
    ("S10", "pipe/pipe_stage.v", "                        if (sd[D] == NS - 1)\n", "                        if (sd[D] == NS - 2)\n", "input-serial result captured one slot early"),
    ("S11", "pipe/pipe_stage.v", "assign a_l = snap[((L % KK) * C_IN + s) * 8 +: 8];", "assign a_l = snap[((L / KK) % KK * C_IN + s) * 8 +: 8];", "wrong tap for MODE 1/2 lanes"),
    ("S12", "pipe/pipe_stage.v", "assign a_l = snap[((L / C_IN) * C_IN + (L % C_IN)) * 8 +: 8];", "assign a_l = snap[((L % C_IN) * C_IN + (L / C_IN) % C_IN) * 8 +: 8];", "MODE 0 lane reads the wrong window byte"),
    ("S13", "pipe/pipe_stage.v", "rq_add_r <= ANCHOR ? anc_data[8 * (j >> 2) +: 8] : 8'd0;", "rq_add_r <= ANCHOR ? anc_data[8 * (j >> 1 & 3) % 24 +: 8] : 8'd0;", "anchor colour from the wrong channel index"),
    ("S14", "pipe/pipe_stage.v", "                if (ix == in_w - 1) begin\n", "                if (ix == in_w) begin\n", "row length one pixel too long"),
    ("M1", "pipe/pipe_mul.v", "wire signed [8:0] a_s = {1'b0, a_r};", "wire signed [8:0] a_s = {a_r[7], a_r};", "activation read as signed"),
    ("T1", "pipe/adder_tree.v", "+ ((2*j + 1 < CP) ? $signed({{(OW-IW){inx[(2*j+1)*IW+IW-1]}}, inx[(2*j+1)*IW +: IW]}) : $signed({OW{1'b0}}));",
     "+ ((2*j + 1 < CP) ? $signed({{(OW-IW){1'b0}}, inx[(2*j+1)*IW +: IW]}) : $signed({OW{1'b0}}));", "second term of each first-level pair zero-extended"),
    ("T2", "pipe/adder_tree.v", "+ ((2*j + 1 < CP) ? $signed(lev[l-1].v[((2*j + 1 < CP) ? 2*j + 1 : 2*j)*OW +: OW]) : $signed({OW{1'b0}}));",
     "+ ((2*j + 1 < CP - 1) ? $signed(lev[l-1].v[((2*j + 1 < CP) ? 2*j + 1 : 2*j)*OW +: OW]) : $signed({OW{1'b0}}));", "last pair of the upper levels drops a term"),
    ("C1", "pipe/sr_pipe_core.v", "wire        anc_push = ext && (px >= 16'd3) && (px < fw + 16'd3)", "wire        anc_push = ext && (px >= 16'd3) && (px <= fw + 16'd3)", "anchor FIFO gets one pixel too many per row"),
    ("C2", "pipe/sr_pipe_core.v", "nbi  <= (3 * npix_p + 3) >> 2;", "nbi  <= (3 * npix_p) >> 2;", "input beat count rounded down"),
    ("C3", "pipe/sr_pipe_core.v", "assign s_axis_tready = run_f && (in_beats != nbi) && (un1 <= 3'd3);", "assign s_axis_tready = run_f && (in_beats != nbi) && (un1 <= 3'd4);", "unpacker overflows its byte buffer"),
    ("C4", "pipe/sr_pipe_core.v", "if (pcnt == npix && run_f) un <= 3'd0;", "if (pcnt == npix && run_f && 1'b0) un <= 3'd0;", "unused bytes of the last beat kept for the next frame",
     "EQUIV: the accepted start (fstart) clears ub/un anyway, so this line is redundant"),
    ("C5", "pipe/sr_pipe_core.v", "else if (start && !busy) cycles <= 32'd1;", "else if (start && !busy) cycles <= cycles;", "cycle counter not restarted"),
    ("C6", "pipe/sr_pipe_core.v", "parameter SHIFT4 = 25,", "parameter SHIFT4 = 24,", "core default SHIFT4 wrong"),
    ("O1", "pipe/pipe_out.v", "wire [23:0] pix0 = {rq[8*(8 + 2*dy) +: 8], rq[8*(4 + 2*dy) +: 8], rq[8*(0 + 2*dy) +: 8]};",
     "wire [23:0] pix0 = {rq[8*(9 + 2*dy) +: 8], rq[8*(5 + 2*dy) +: 8], rq[8*(1 + 2*dy) +: 8]};", "pixel shuffle: dx = 0 takes the dx = 1 channels"),
    ("O2", "pipe/pipe_out.v", "wire [23:0] pix1 = {rq[8*(9 + 2*dy) +: 8], rq[8*(5 + 2*dy) +: 8], rq[8*(1 + 2*dy) +: 8]};",
     "wire [23:0] pix1 = {rq[8*(1 + 2*dy) +: 8], rq[8*(5 + 2*dy) +: 8], rq[8*(9 + 2*dy) +: 8]};", "colour order reversed (BGR) for dx = 1"),
    ("O3", "pipe/pipe_out.v", "assign ok = (sx != 16'd0) || free[sb];", "assign ok = 1'b1;", "output bank overwritten while it is read"),
    ("O4", "pipe/pipe_out.v", "ow <= pb[31:0]; ov <= 1'b1; olast <= (beats == n_beats - 1);", "ow <= pb[31:0]; ov <= 1'b1; olast <= (beats == n_beats - 2);", "TLAST one beat early"),
    ("F1", "pipe/pipe_fifo.v", "assign ok        = (res < DEPTH);", "assign ok        = (res <= DEPTH);", "FIFO accepts one reservation too many"),
    ("A1", "top/sr_accel_top.v", "(frame_w <= MAXW - 6)", "(frame_w <= MAXW - 5)", "frame width one above MAX_W accepted"),
    ("A2", "top/sr_accel_top.v", "else if (core_flags[2])  err_code <= 3'd3;", "else if (core_flags[2])  err_code <= 3'd2;", "TKEEP error reported as code 2"),
]

FILES = ["common/requant.v"] + [f"pipe/{p.name}" for p in sorted((RTL / "pipe").glob("*.v"))]
TOPF = FILES + ["top/sr_accel_top.v"]

# (name, rtl files, testbench, iverilog params, plusargs, timeout s); fast first
TESTS = (
    [(f"stage L{L} random", FILES, "tb_pipe_stage.v", [f"tb_pipe_stage.LAYER={L}", "tb_pipe_stage.REAL=0"], ["+STALL=1", "+SWEEP=2"], 120) for L in (1, 2, 3, 4)]
    + [(f"stage L{L} random, slow consumer", FILES, "tb_pipe_stage.v", [f"tb_pipe_stage.LAYER={L}", "tb_pipe_stage.REAL=0"], ["+STALL=2"], 120) for L in (1, 4)]
    + [("adder tree N=27", ["pipe/adder_tree.v"], "tb_adder_tree.v", ["tb_adder_tree.N=27"], [], 60),
       ("adder tree N=9", ["pipe/adder_tree.v"], "tb_adder_tree.v", ["tb_adder_tree.N=9"], [], 60)]
    + [(f"stage L{L} network weights", FILES, "tb_pipe_stage.v", [f"tb_pipe_stage.LAYER={L}", "tb_pipe_stage.REAL=1"], ["+FRAME=p13x7"], 180) for L in (1, 4)]
    + [("top small frames + stage outputs", TOPF, "tb_sr_pipe_top.v", [], ["+F0=p13x7", "+F1=p1x1", "+F2=p2x3", "+F3=psat", "+F4=p5x4", "+LAYERS=1"], 300),
       ("top errors + soft-reset aborts", TOPF, "tb_sr_pipe_top.v", [], ["+F0=p5x4", "+ERR=1", "+SWEEP=3"], 300),
       ("top stalls", TOPF, "tb_sr_pipe_top.v", [], ["+F0=pramp", "+F1=p2x3", "+STALL=1"], 300),
       ("top slow output sink", TOPF, "tb_sr_pipe_top.v", [], ["+F0=pramp", "+F1=p13x7", "+STALL=2"], 600)]
)


def run_test(work: Path, mut_file, test):
    name, files, tb, params, plus, tmo = test
    srcs = [str((work / f) if f == mut_file else (RTL / f)) for f in files]
    vvp = work / (name.replace(" ", "_").replace("+", "") + ".vvp")
    r = subprocess.run(["iverilog", "-g2012", "-I", ".", "-o", str(vvp)] + sum([["-P", p] for p in params], []) + srcs + [str(TB / tb)],
                       cwd=ROOT, capture_output=True, text=True)
    if r.returncode != 0:
        return "FAIL", "build error: " + " ".join(r.stderr.strip().splitlines()[:1])
    try:
        r = subprocess.run(["vvp", "-n", str(vvp)] + plus, cwd=ROOT, capture_output=True, text=True, timeout=tmo)
    except subprocess.TimeoutExpired:
        return "FAIL", f"timeout after {tmo} s (hang)"
    out = r.stdout
    if "\nFAIL" in "\n" + out or "PASS" not in out:
        first = next((l for l in out.splitlines() if l.startswith("FAIL")), "no PASS line")
        return "FAIL", first[:140]
    return "PASS", ""


def run_mutant(m):
    mid, f, old, new, desc = m[:5]
    equiv = len(m) > 5
    with tempfile.TemporaryDirectory() as tmp:
        work = Path(tmp)
        mut_file = None
        if f:
            src = (RTL / f).read_text()
            if src.count(old) != 1:
                return mid, desc, "INVALID", f"pattern found {src.count(old)} times in {f}"
            (work / f).parent.mkdir(parents=True, exist_ok=True)
            (work / f).write_text(src.replace(old, new))
            mut_file = f
        for t in TESTS:
            if mut_file and mut_file not in t[1]:
                continue
            res, why = run_test(work, mut_file, t)
            if res == "FAIL":
                return mid, desc, ("CAUGHT (EQUIV?)" if equiv else "CAUGHT") if f else "CONTROL FAILED", f"{t[0]}: {why}"
        return mid, desc, ("EQUIV, survived" if equiv else "SURVIVED") if f else "CONTROL OK", m[5] if equiv else "all tests passed"


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--jobs", type=int, default=4)
    ap.add_argument("--only", default="")
    a = ap.parse_args()
    ms = [m for m in MUTANTS if not a.only or m[0] in a.only.split(",")]
    ctrl = run_mutant(("CTRL", None, None, None, "no mutation"))
    print(f"{ctrl[0]:5s} {ctrl[2]:15s} {ctrl[1]} ({ctrl[3]})", flush=True)
    with ThreadPoolExecutor(a.jobs) as ex:
        res = list(ex.map(run_mutant, ms))
    for mid, desc, st, why in res:
        print(f"{mid:5s} {st:15s} {desc}  [{why}]")
    bad = [r for r in res if r[2] not in ("CAUGHT", "EQUIV, survived")]
    ok = ctrl[2] == "CONTROL OK" and not bad
    print(f"{'PASS' if ok else 'FAIL'} pipeline mutation test: {len(res)} mutants, {sum(r[2] == 'CAUGHT' for r in res)} caught, {sum(r[2] == 'EQUIV, survived' for r in res)} equivalent, "
          f"{sum(r[2] == 'SURVIVED' for r in res)} survived, {sum(r[2] == 'INVALID' for r in res)} invalid; control {ctrl[2]}")
    return 0 if ok else 1


if __name__ == "__main__":
    sys.exit(main())
