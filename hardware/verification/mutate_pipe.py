"""Mutation test of the whole-frame pipeline RTL (branch `pipe2p`: stage tests at NS = 8 with PACK = 1, plus L4 unpacked with LUT and DSP lanes; the top at NS = 8, PACK = 1): apply ONE deliberate defect to a copy of an RTL file, run a set of the pipeline tests
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
    ("S8", "pipe/pipe_stage.v", "wire [7:0]        bc_i = sd[D-1] * P + r;", "wire [7:0]        bc_i = sd[D] * P + r;", "output-serial bias one slot late"),
    ("S9", "pipe/pipe_stage.v", "acc[gi] <= ((sd[D] == 0) ? bias_mem[gi] : acc[gi])", "acc[gi] <= ((sd[D] == 1) ? bias_mem[gi] : acc[gi])", "input-serial accumulator restarts at slot 1"),
    ("S10", "pipe/pipe_stage.v", "                        if (sd[D] == NS - 1)\n", "                        if (sd[D] == NS - 2)\n", "input-serial result captured one slot early"),
    ("S11", "pipe/pipe_stage.v", "snap[((t % KK) * C_IN + ch1) * 8 +: 8]", "snap[(((t + 1) % KK) * C_IN + ch1) * 8 +: 8]", "wrong tap for MODE 1 lanes"),
    ("S11b", "pipe/pipe_stage.v", "assign a_l = snap[((t % KK) * C_IN + s * P + t / KK) * 8 +: 8];", "assign a_l = snap[((t % KK) * C_IN + s * P) * 8 +: 8];", "MODE 2: both channels of a slot read channel s*P (v2 only)"),
    ("S12", "pipe/pipe_stage.v", "assign a_l = snap[t * 8 +: 8];", "assign a_l = snap[((t % C_IN) * C_IN + (t / C_IN) % C_IN) * 8 +: 8];", "MODE 0 lane reads the wrong window byte"),
    ("S13", "pipe/pipe_stage.v", "rq_add_r <= ANCHOR ? anc_data[8 * (ch >> 2) +: 8] : 8'd0;", "rq_add_r <= ANCHOR ? anc_data[8 * (ch >> 1 & 3) % 24 +: 8] : 8'd0;", "anchor colour from the wrong channel index"),
    ("S14", "pipe/pipe_stage.v", "always @(posedge clk) begin wm1 <= in_w - 16'd1;", "always @(posedge clk) begin wm1 <= in_w;", "row length one pixel too long"),
    ("V1", "pipe/pipe_stage.v", "wire [7:0]        ac_i = sd[D] * P + r;", "wire [7:0]        ac_i = sd[D] * P;", "MODE 0/1: all requantizers of a slot get channel s*P"),
    ("V2", "pipe/pipe_stage.v", "wire [4:0]        ch = j * NRQ + r;", "wire [4:0]        ch = j + r;", "MODE 2: requantizer channels overlap (v2 only)"),
    ("V3", "pipe/pipe_stage.v", "for (ri = 0; ri < NRQ; ri = ri + 1)", "for (ri = 0; ri < 1; ri = ri + 1)", "only the first requantizer writes the output word (v2 only)"),
    ("V4", "pipe/pipe_stage.v", "if (L < NDSP) begin : g_dsp", "if (L < NDSP - 1) begin : g_dsp", "one more lane in LUTs (function unchanged)",
     "EQUIV: pipe_mul and pipe_mul_lut compute the same product with the same latency; only the DSP/LUT mapping changes"),
    ("V5", "pipe/sr_pipe_core.v", '(NS == 8) ? "wpipe8_" : "wpipe6_";', '(NS == 8) ? "wpipe8_" : "wpipe8_";', "core loads the 8-slot weight ROMs at NS = 6"),
    ("M2", "pipe/pipe_mul_lut.v", "wire signed [8:0] a_s = {1'b0, a_r};", "wire signed [8:0] a_s = {a_r[7], a_r};", "LUT multiplier lanes read the activation as signed"),
    ("P1", "pipe/pipe_mul2.v", "assign b      = po[16];", "assign b      = 1'b0;", "packed multiplier: borrow of the high product dropped"),
    ("P2", "pipe/pipe_mul2.v", "$signed({w2, 17'd0})", "$signed({w2, 16'd0})", "packed multiplier: second weight shifted by 16 instead of 17"),
    ("P3", "pipe/pipe_mul2.v", "assign hi_raw = po[33:17];", "assign hi_raw = {po[32], po[32:17]};", "packed multiplier: bit 33 of the product replaced by bit 32",
     "EQUIV: |P| <= ((127 << 17) + 127) * 255 < 2^32, so P fits 33 bits and p[33] == p[32] always"),
    ("P4", "pipe/pipe_stage.v", ".w2(wrow[8*(L + NT) +: 8])", ".w2(wrow[8*L +: 8])", "packed lanes: the odd tree gets the even tree's weights"),
    ("P5", "pipe/pipe_stage.v", "for (bi = 0; bi < NT; bi = bi + 1) bc = bc", "for (bi = 1; bi < NT; bi = bi + 1) bc = bc", "borrow of term 0 not counted"),
    ("P6", "pipe/pipe_stage.v", "localparam NTT = PK ? NT + 1 : NT;", "localparam NTT = NT;", "borrow-count term missing from the adder trees (packed stages)"),
    ("P7", "pipe/pipe_mul2.v", "wire signed [8:0]  a_s = {1'b0, a_r};", "wire signed [8:0]  a_s = {a_r[7], a_r};", "packed multiplier: activation read as signed"),
    ("M1", "pipe/pipe_mul.v", "wire signed [8:0] a_s = {1'b0, a_r};", "wire signed [8:0] a_s = {a_r[7], a_r};", "activation read as signed"),
    ("T1", "pipe/adder_tree.v", "+ ((2*j + 1 < CP) ? $signed({{(OW-IW){inx[(2*j+1)*IW+IW-1]}}, inx[(2*j+1)*IW +: IW]}) : $signed({OW{1'b0}}));",
     "+ ((2*j + 1 < CP) ? $signed({{(OW-IW){1'b0}}, inx[(2*j+1)*IW +: IW]}) : $signed({OW{1'b0}}));", "second term of each first-level pair zero-extended"),
    ("T2", "pipe/adder_tree.v", "+ ((2*j + 1 < CP) ? $signed(lev[l-1].v[((2*j + 1 < CP) ? 2*j + 1 : 2*j)*OW +: OW]) : $signed({OW{1'b0}}));",
     "+ ((2*j + 1 < CP - 1) ? $signed(lev[l-1].v[((2*j + 1 < CP) ? 2*j + 1 : 2*j)*OW +: OW]) : $signed({OW{1'b0}}));", "last pair of the upper levels drops a term"),
    ("C1", "pipe/sr_pipe_core.v", "if (px + 16'd1 == fw3)   xin <= 1'b0;", "if (px + 16'd1 == fw3 + 16'd1)   xin <= 1'b0;", "anchor FIFO gets one pixel too many per row"),
    ("C1b", "pipe/sr_pipe_core.v", "if (py + 16'd1 == 16'd3) yin <= 1'b1;", "if (py + 16'd1 == 16'd2) yin <= 1'b1;", "anchor rows start one padded row early"),
    ("C7", "pipe/sr_pipe_core.v", "pix_left <= (pcnt + 32'd1 != npix);", "pix_left <= 1'b1;", "registered pixel-left flag never clears (extra pixel from leftover bytes)"),
    ("C2", "pipe/sr_pipe_core.v", ": (3 * npix_p + 3) >> 2;", ": (3 * npix_p) >> 2;", "input beat count rounded down"),
    ("C3", "pipe/sr_pipe_core.v", "assign s_axis_tready = run_f && (in_beats != nbi) && (un1 <= 3'd3);", "assign s_axis_tready = run_f && (in_beats != nbi) && (un1 <= 3'd4);", "unpacker overflows its byte buffer"),
    ("C4", "pipe/sr_pipe_core.v", "if (!u_left && run_f) un <= 3'd0;", "if (!u_left && run_f && 1'b0) un <= 3'd0;", "unused bytes of the last beat kept for the next frame",
     "EQUIV: the accepted start (fstart) clears ub/un anyway, so this line is redundant"),
    ("C8", "pipe/sr_pipe_core.v", "nu   <= pe ? nlr_p : npix_p;", "nu   <= npix_p;", "PL padding: unpacker expects the padded pixel count"),
    ("C9", "pipe/sr_pipe_core.v", "nbi  <= pe ? (3 * nlr_p + 3) >> 2", "nbi  <= pe ? (3 * nlr_p) >> 2", "PL padding: raw input beat count rounded down"),
    ("D1", "pipe/sr_pipe_core.v", "u_left && (ahead <= 2'd1);", "u_left && (ahead <= 2'd2);", "PL padding: writer overwrites the row the reader still uses"),
    ("D2", "pipe/sr_pipe_core.v", "rd_left && (ahead != 2'd0)", "rd_left", "PL padding: reader starts a raw row before it is complete"),
    ("D13", "pipe/sr_pipe_core.v", "rd_left <= (rcnt + 32'd1 != npix);", "rd_left <= 1'b1;", "PL padding: reader never stops (reads past the frame)"),
    ("D14", "pipe/sr_pipe_core.v", "ahead <= ahead + {1'b0, wr_eol} - {1'b0, rd_nxr};", "ahead <= ahead + {1'b0, wr_eol};", "PL padding: rows-ahead counter never decremented (writer stalls)"),
    ("D3", "pipe/sr_pipe_core.v", "(qy >= 16'd3) && (rrow != rh1)", "(qy >= 16'd2) && (rrow != rh1)", "PL padding: only 2 replicated rows at the top"),
    ("D4", "pipe/sr_pipe_core.v", "if (qx >= 16'd3 && {", "if (qx >= 16'd2 && {", "PL padding: only 2 replicated columns on the left"),
    ("D5", "pipe/sr_pipe_core.v", "(qy >= 16'd3) && (rrow != rh1)", "(qy >= 16'd3)", "PL padding: bottom rows not clamped to the last raw row"),
    ("D6", "pipe/sr_pipe_core.v", "{{(16-AW){1'b0}}, rx} != rw1) rx <= rx + 1'b1;", "1'b1) rx <= rx + 1'b1;", "PL padding: right columns not clamped to the last raw column"),
    ("D7", "pipe/sr_pipe_core.v", "+ {2'b0, rd_v} < 3'd2)", "+ {2'b0, rd_v} < 3'd3)", "PL padding: 2-entry queue overfilled"),
    ("D8", "pipe/sr_pipe_core.v", "2'b11: begin if (qn == 2'd1) q0 <= rq;", "2'b11: begin if (qn == 2'd1) q0 <= q0;", "PL padding: queue push+pop with one entry keeps the old pixel"),
    ("D9", "pipe/sr_pipe_core.v", "rq <= rb[{rrow[0], rx}];", "rq <= rb[{wrow[0], rx}];", "PL padding: reader reads the writer's half"),
    ("D10", "pipe/sr_pipe_core.v", "fw <= lr_w; fh <= lr_h; pe <= pad_en;", "fw <= lr_w; fh <= lr_h; pe <= 1'b0;", "PL padding enable ignored by the core"),
    ("D11", "top/sr_accel_top.v", "if (aw_addr[5:2] == 4'd10 && w_strb[0]) pad_en <= w_data[0];", "if (aw_addr[5:2] == 4'd10 && w_strb[0]) pad_en <= w_data[1];", "CONFIG.PAD_EN written from the wrong bit"),
    ("D12", "pipe/sr_pipe_core.v", "if (wr_take) rb[{wrow[0], wx}] <= ub[23:0];", "if (wr_take) rb[{wrow[0], wx}] <= ub[31:8];", "PL padding: row buffer stores the wrong bytes"),
    # pipe4 (NS = 6): ceil channels per slot, odd tree packing, LUT pairs, L4 output-serial with the anchor, borrow-count width
    ("N1", "pipe/pipe_stage.v", "assign anc_pop = (ANCHOR != 0) && vd[D] && (sd[D] == 0) && !rst;", "assign anc_pop = (ANCHOR != 0) && vd[D] && (sd[D] == 1) && !rst;", "MODE 0 anchor popped at slot 1 (slot 0 gets the previous pixel's anchor)"),
    ("N2", "pipe/pipe_stage.v", "rq_add_r <= ANCHOR ? anc_data[8 * (acc_c >> 2) +: 8] : 8'd0;   // pipe4", "rq_add_r <= ANCHOR ? anc_data[8 * ((acc_c >> 1) % 3) +: 8] : 8'd0;   // pipe4", "MODE 0 anchor colour from the wrong channel"),
    ("N3", "pipe/pipe_stage.v", "localparam BW = $clog2(NT + 1);", "localparam BW = 6;", "borrow count 6 bits (the bug found 2026-11-18: overflows above 63 borrows)"),
    ("N4", "pipe/pipe_stage.v", "localparam P   = (NCH + NS - 1) / NS;", "localparam P   = NCH / NS;", "channels per slot rounded down (NS = 6: 12 of 16 channels)"),
    ("N5", "pipe/pipe_stage.v", "pipe_mul_lut #(.LAT(MLAT)) u_m2 (.clk(clk), .a(a_l), .w(wrow[8*(L + NT) +: 8]), .prod(hi));", "pipe_mul_lut #(.LAT(MLAT)) u_m2 (.clk(clk), .a(a_l), .w(wrow[8*L +: 8]), .prod(hi));", "LUT pair: odd tree gets the even tree's weight"),
    ("N6", "pipe/pipe_stage.v", "if (rq_tag[5*ri +: 5] == C_OUT - 1) last_n = 1'b1;", "if (rq_tag[5*ri +: 5] == C_OUT - 2) last_n = 1'b1;", "output word sent before its last channel"),
    ("N7", "pipe/pipe_stage.v", "acc_v  <= vd[D] && (ac_i < C_OUT) && !rst;", "acc_v  <= vd[D] && !rst;", "empty channels (>= C_OUT) reach the requantizers",
     "EQUIV: channels >= C_OUT carry tags 16/17; the output word only takes part-selects inside its 8*C_OUT bits (writes beyond are dropped) and last_n compares with C_OUT - 1, so the pixel's word and its timing are unchanged"),
    ("N8", "pipe/pipe_stage.v", "if (!PK || (NG % 2 == 1 && g == NG - 1)) begin : g_one", "if (!PK || (NG % 2 == 1 && g == 0)) begin : g_one", "odd tree count: the wrong tree left unpacked"),
    ("N9", "pipe/sr_pipe_core.v", ".MODE((NS == 6) ? 0 : 2)", ".MODE(2)", "L4 kept input-serial at NS = 6"),
    ("C5", "pipe/sr_pipe_core.v", "else if (start && !busy) cycles <= 32'd1;", "else if (start && !busy) cycles <= cycles;", "cycle counter not restarted"),
    ("C6", "pipe/sr_pipe_core.v", "parameter SHIFT4 = 25,", "parameter SHIFT4 = 24,", "core default SHIFT4 wrong"),
    ("O1", "pipe/pipe_out.v", "wire [23:0] pix0 = {rq[8*(8 + 2*dy) +: 8], rq[8*(4 + 2*dy) +: 8], rq[8*(0 + 2*dy) +: 8]};",
     "wire [23:0] pix0 = {rq[8*(9 + 2*dy) +: 8], rq[8*(5 + 2*dy) +: 8], rq[8*(1 + 2*dy) +: 8]};", "pixel shuffle: dx = 0 takes the dx = 1 channels"),
    ("O2", "pipe/pipe_out.v", "wire [23:0] pix1 = {rq[8*(9 + 2*dy) +: 8], rq[8*(5 + 2*dy) +: 8], rq[8*(1 + 2*dy) +: 8]};",
     "wire [23:0] pix1 = {rq[8*(1 + 2*dy) +: 8], rq[8*(5 + 2*dy) +: 8], rq[8*(9 + 2*dy) +: 8]};", "colour order reversed (BGR) for dx = 1"),
    ("O3", "pipe/pipe_out.v", "assign ok = (sx != 16'd0) || free[sb];", "assign ok = 1'b1;", "output bank overwritten while it is read"),
    ("O4", "pipe/pipe_out.v", "ow <= pb[31:0]; ov <= 1'b1; olast <= (beats == n_beats - 1);", "ow <= pb[31:0]; ov <= 1'b1; olast <= (beats == n_beats - 2);", "TLAST one beat early"),
    ("F2", "pipe/anchor_fifo.v", "    reg  [AW:0] cnt;", "    reg  [AW-1:0] cnt;", "anchor FIFO occupancy one bit short (wraps at 4096: never full, err on overflow)"),
    ("F4", "pipe/anchor_fifo.v", "- ((pop && !empty) ? 1'b1 : 1'b0);", ";", "anchor FIFO occupancy never decremented (fills up: deadlock)"),
    ("N10", "pipe/pipe_mul_lut.v", "prod  <= $signed(pp_lo) + ($signed(pp_hi) <<< 4);", "prod  <= $signed(pp_lo) + ($signed(pp_hi) <<< 3);", "3-cycle LUT multiplier: high half shifted by 3"),
    ("N11", "pipe/pipe_mul_lut.v", "pp_lo <= a_s * $signed({1'b0, w_r[3:0]});", "pp_lo <= a_s * $signed(w_r[3:0]);", "3-cycle LUT multiplier: low nibble taken as signed"),
    ("N12", "pipe/sr_pipe_core.v", ".MLAT((NS == 6) ? 3 : 2)", ".MLAT(2)", "core: L4 multipliers 3-cycle in the stage test but 2 in the core (D mismatch is not possible: D follows MLAT; checks the parameter is passed)",
     "EQUIV (function): MLAT only changes the multiplier latency and D follows it (D = MLAT + tree levels); the output is identical, only the 142.86 MHz timing of the LUT multipliers needs MLAT = 3 (checked by the Vivado build, not by simulation)"),
    ("F3", "pipe/anchor_fifo.v", "            full <= (cnt >= DEPTH - 4);", "            full <= (cnt >= DEPTH - 1100);", "anchor FIFO stops early (2,996 entries < the 3,066 a max-width frame needs)"),
    ("A3", "top/sr_accel_top.v", " && (frame_h <= MAXH);", ";", "frame height cap missing (H > 4096 accepted)"),
    ("S15", "pipe/pipe_stage.v", "        d1_x    <= ix[AW-1:0];", "        d1_x    <= ix[AW-2:0];", "line-buffer write address one bit short (only W > 506 notices)"),
    ("F1", "pipe/pipe_fifo.v", "assign ok        = (res < DEPTH);", "assign ok        = (res <= DEPTH);", "FIFO accepts one reservation too many"),
    ("A1", "top/sr_accel_top.v", "(frame_w <= MAXW - 6)", "(frame_w <= MAXW - 5)", "frame width one above MAX_W accepted"),
    ("A2", "top/sr_accel_top.v", "else if (core_flags[2])  err_code <= 3'd3;", "else if (core_flags[2])  err_code <= 3'd2;", "TKEEP error reported as code 2"),
]

FILES = ["common/requant.v"] + [f"pipe/{p.name}" for p in sorted((RTL / "pipe").glob("*.v"))]
TOPF = FILES + ["top/sr_accel_top.v"]

def NS8(layer: int) -> list[str]:
    """Stage tests run the v2 configuration: NS = 8; L4 with NDSP = 50 (DSP and LUT multiplier lanes both used)."""
    return ["tb_pipe_stage.NS=8", "tb_pipe_stage.PACK=1"]


def NS6(layer: int) -> list[str]:
    """pipe4: NS = 6, packed; L4 with NDSP2 = 40 so packed DSP pairs and LUT pairs are both used."""
    return ["tb_pipe_stage.NS=6", "tb_pipe_stage.PACK=1"] + (["tb_pipe_stage.NDSP2=40"] if layer == 4 else [])


def NS6A(layer: int) -> list[str]:
    """pipe4: NS = 6, packed, every pair on DSPs (the borrow count reaches its maximum)."""
    return ["tb_pipe_stage.NS=6", "tb_pipe_stage.PACK=1"]


def NS8U(layer: int) -> list[str]:
    """The unpacked v2 configuration (branch pipe2): L4 with NDSP = 50 (DSP and LUT multiplier lanes both used)."""
    return ["tb_pipe_stage.NS=8", "tb_pipe_stage.PACK=0"] + (["tb_pipe_stage.NDSP=50"] if layer == 4 else [])


# (name, rtl files, testbench, iverilog params, plusargs, timeout s); fast first
TESTS = (
    [("fifos (pointer wrap)", ["pipe/anchor_fifo.v", "pipe/pipe_fifo.v"], "tb_fifos.v", [], [], 120)]
    + [(f"stage L{L} random", FILES, "tb_pipe_stage.v", [f"tb_pipe_stage.LAYER={L}", "tb_pipe_stage.REAL=0"] + NS8(L), ["+STALL=1", "+SWEEP=2"], 120) for L in (1, 2, 3, 4)]
    + [(f"stage L{L} random, slow consumer", FILES, "tb_pipe_stage.v", [f"tb_pipe_stage.LAYER={L}", "tb_pipe_stage.REAL=0"] + NS8(L), ["+STALL=2"], 120) for L in (1, 4)]
    + [(f"stage L{L} random, unpacked", FILES, "tb_pipe_stage.v", [f"tb_pipe_stage.LAYER={L}", "tb_pipe_stage.REAL=0"] + NS8U(L), ["+STALL=1"], 120) for L in (1, 2, 4)]
    + [(f"stage L{L} random, NS=6", FILES, "tb_pipe_stage.v", [f"tb_pipe_stage.LAYER={L}", "tb_pipe_stage.REAL=0"] + NS6(L), ["+STALL=1", "+SWEEP=2"], 180) for L in (1, 2, 3, 4)]
    + [("stage L4 random, NS=6, all pairs on DSPs", FILES, "tb_pipe_stage.v", ["tb_pipe_stage.LAYER=4", "tb_pipe_stage.REAL=0"] + NS6A(4), ["+STALL=1"], 180)]
    + [("adder tree N=27", ["pipe/adder_tree.v"], "tb_adder_tree.v", ["tb_adder_tree.N=27"], [], 60),
       ("adder tree N=9", ["pipe/adder_tree.v"], "tb_adder_tree.v", ["tb_adder_tree.N=9"], [], 60)]
    + [(f"stage L{L} network weights", FILES, "tb_pipe_stage.v", [f"tb_pipe_stage.LAYER={L}", "tb_pipe_stage.REAL=1"] + NS8(L), ["+FRAME=p13x7"], 180) for L in (1, 2, 3, 4)]
    + [("top small frames + stage outputs", TOPF, "tb_sr_pipe_top.v", [], ["+F0=p13x7", "+F1=p1x1", "+F2=p2x3", "+F3=psat", "+F4=p5x4", "+LAYERS=1"], 300),
       ("top errors + soft-reset aborts", TOPF, "tb_sr_pipe_top.v", [], ["+F0=p5x4", "+ERR=1", "+SWEEP=3"], 300),
       ("top stalls", TOPF, "tb_sr_pipe_top.v", [], ["+F0=pramp", "+F1=p2x3", "+STALL=1"], 300),
       ("top slow output sink", TOPF, "tb_sr_pipe_top.v", [], ["+F0=pramp", "+F1=p13x7", "+STALL=2"], 600),
       ("top max width 1018 (anchor FIFO and line buffers at their limit)", TOPF, "tb_sr_pipe_top.v", [], ["+F0=pmaxw"], 900),
       # pipe3: PL padding (raw input)
       ("top PL padding small frames + stage outputs", TOPF, "tb_sr_pipe_top.v", [], ["+F0=p13x7", "+F1=p1x1", "+F2=p2x3", "+F3=psat", "+F4=p5x4", "+F5=pramp", "+PAD=1", "+LAYERS=1"], 300),
       ("top PL padding errors + aborts", TOPF, "tb_sr_pipe_top.v", [], ["+F0=p5x4", "+PAD=1", "+ERR=1", "+SWEEP=3"], 300),
       ("top PL padding mixed + slow sink", TOPF, "tb_sr_pipe_top.v", [], ["+F0=pramp", "+F1=p13x7", "+F2=p2x3", "+PAD=2", "+STALL=2"], 600),
       ("top PL padding 37x29 stalls", TOPF, "tb_sr_pipe_top.v", [], ["+F0=preal2", "+PAD=1", "+STALL=1"], 600),
       ("top PL padding max width 1018", TOPF, "tb_sr_pipe_top.v", [], ["+F0=pmaxw", "+PAD=1"], 900)]
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
