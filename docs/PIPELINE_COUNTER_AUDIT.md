# Pipeline RTL: width audit and counter / pointer table (2026-10-27)

Branch `pipe`, files `hardware/rtl/pipe/*.v`, `hardware/rtl/top/sr_accel_top.v`, `hardware/rtl/common/requant.v`.

## Why: the anchor-FIFO deadlock (found 2026-10-26)
`anchor_fifo.v` computed its occupancy as `(wp - rp) >= DEPTH - 4`. The pointers are 13 bits, but `DEPTH - 4` is a 32-bit integer, so Verilog
evaluates `wp - rp` in 32 bits. After the write pointer wraps (8,192 pushes) while the read pointer has not, the difference is negative, so as an
unsigned number it is huge. `full` then went high with 579 entries inside, the input stopped, and the pipeline stopped (960x540: after 5 of 540
output rows, 14,400 of 1,555,200 beats).

Fix: `wire [AW:0] cnt = wp - rp;` (occupancy in the pointers' own width), the same in `pipe_fifo.v`, where it only weakened the overflow check.

**Why nothing caught it before the full-size frame.** The largest frame in the regression pushed 3,072 anchors (64x48), and no test pushed 8,192. The
mutation test (30 mutants) cannot find a bug that no test exercises: mutation testing measures whether the tests notice a change, not whether
the tests reach every state. There was no unit test of the FIFOs (they were only tested inside the stages and the top, with small frames).

## 1. Width audit: every arithmetic or comparison site, checked against the Verilog sizing rules
Rule: in `a == b`, `a < b`, `a + b` and so on, every operand is first extended to the widest operand of the expression, and an unsized integer counts as
32 bits. So `x - 1` with a 16-bit `x` is a 32-bit value, and `x == 0` there gives -1, not 0xFFFF.

| File:site | Expression | Context width | Verdict |
|---|---|---|---|
| anchor_fifo `cnt` | `wp - rp` (13 b) | **was 32 b, now 13 b** (`wire [AW:0] cnt`) | **BUG, fixed** (the deadlock) |
| anchor_fifo | `cnt == DEPTH`, `cnt >= DEPTH - 4` | 32 b; cnt <= 4096 fits 13 b | OK |
| pipe_fifo `cnt` | `wp - rp` (4 b) in `== DEPTH` | **was 32 b, now 4 b** | **BUG, fixed** (made the overflow check blind after the first wrap; no functional effect) |
| pipe_fifo | `res < DEPTH`; `res + reserve - pop` | 32 b / 4 b (LHS); res in 0..8 | OK |
| sr_pipe_core | `pw_a <= fw + 16'd6`, `ph_a <= fh + 16'd6`, stage `.in_h(fh + 16'd6/4/2)`, `py < fh + 16'd3` | **16 b** | **BUG, fixed by a limit**: H >= 65,530 wrapped (wrong pixel count, anchors not pushed), and `size_ok` accepted H up to 65,535. Now `frame_h <= MAXH = 4096` (start refused with ERROR_CODE 4 above it; the ARM's 16 MB output buffer allows much less anyway) |
| sr_pipe_core | `px == fw + 16'd5`, `px < fw + 16'd3`, `.in_w(fw + 16'd6)` | 16 b; fw <= 1018 | OK |
| sr_pipe_core | `npix_p <= pw_a * ph_a`, `nlr_p <= w_a * h_a` | 32 b (LHS) | OK: <= 1024 x 4102 |
| sr_pipe_core | `(3 * npix_p + 3) >> 2`, `3 * nlr_p` | 32 b | OK: <= 12.6 M |
| sr_pipe_core | `in_beats != nbi - 1`, `pcnt != npix` | 32 b; nbi >= 37 | OK |
| sr_pipe_core | unpacker `un - 3`, `un1 + 4`, `<< (8 * un1)` | 3 b / 56 b; un1 <= 3 when a beat is taken | OK |
| pipe_out | `rx/sx/wx == lr_w - 1` | 32 b; `lr_w - 1 = -1` only for W = 0, which `size_ok` refuses | OK (depends on W >= 1) |
| pipe_out | `{rb, rx[AW-1:0] + 1'b1}`, `{wb, wx[AW-1:0]}` | self-determined 10 b; x <= 1017 | OK, reached only by the max-width frame |
| pipe_out | packer `n - 4`, `n1 + 3`, `<< (8 * n1)` | 3 b / 56 b; n1 <= 4 when a pixel is taken | OK |
| pipe_out | `beats == n_beats - 1` | 32 b | OK |
| pipe_stage | `ix >= K-1`, `ix == in_w - 1`, `iy == in_h - 1` | 32 b; in_w >= 7 | OK |
| pipe_stage | `d1_x <= ix[AW-1:0]` (line-buffer address) | 10 b; ix <= 1023 | OK, reached only by the max-width frame |
| pipe_stage | `s == NS - 1`, `s + 4'd1` | 4 b | OK (reset by px_start) |
| pipe_stage | L4 serializer `j` (0..11, holds 12 afterwards), `hold_r[j]`, `mult_mem[j]` | 5 b | OK: at j = 12 the read is out of range, but it is only taken while `rq_v_r` = 0 |
| pipe_stage | `bias_r + {{8{sums[23]}}, sums}`, `acc + {...}` | 32 b, explicit sign extension | OK (the missing extension was found and fixed during bring-up, 2026-10-26) |
| pipe_stage | `word_n` byte insert `<< (8 * rq_tag)` | OWB bits, explicit zero extension | OK |
| adder_tree | first level: explicit sign extension of 17-bit terms; upper levels `$signed` + `$signed` | OW = 24 b | OK: 27 x 32,640 = 881,280 < 2^23 |
| pipe_mul | `{1'b0, a_r} * w_r` (9 b x 8 b signed) | 17 b (LHS) | OK: operands sign-extended to 17 b |
| requant | `acc * {1'b0, m}`, `p1 + rndx`, `>>> SHIFT`, `< 0`, `> 255` | 49 b signed | OK (exhaustively checked earlier, `test_anchor.py`, requant vectors at acc = +-2^31, M = 65535) |
| sr_accel_top | `frame_w <= MAXW - 6`, `rdata <= MAXW - 6` | 32 b | OK |

## 2. Counters and pointers: wrap point, range, and the test that crosses it
| Module | Counter / pointer | Width | Wrap point / range used | Crossed or reached by |
|---|---|---|---|---|
| anchor_fifo | `wp`, `rp` | 13 b | wrap every 8,192 pushes | `tb_fifos.v` (64-deep copy: 234 wraps); frames p192 (36,864 pushes, 4 wraps), pw960x24 (23,040, 2), pfull (518,400, 63) |
| anchor_fifo | occupancy `cnt` | 13 b | 0..4096; `full` from 4,092 | `tb_fifos.v` (exact `full` threshold, forced overflow and underflow); highest occupancy measured: **3,066** (pmaxw, W = 1018), 588 (p192), 6 (ptall) |
| pipe_fifo (x3) | `wp`, `rp` | 4 b | wrap every 16 words | every frame with >= 16 pixels; `tb_fifos.v` (20,000 words) |
| pipe_fifo | `res` (reservations) | 4 b | 0..8, full at 8 | slow-consumer tests (`tb_pipe_stage +STALL=2`, `tb_sr_pipe_top +STALL=2`), `tb_fifos.v` |
| pipe_stage (x4) | `ix` | 16 b | 0..in_w-1, back to 0 every row; at most 1,023 | every frame; 1,023 only by **pmaxw** (W = 1018) |
| pipe_stage | `iy` | 16 b | 0..in_h-1, no wrap; at most 4,101 | **ptall** (H = 4096: 4,101, past 12 bits) |
| pipe_stage | line-buffer address (`ix[9:0]`, 1,024 entries) | 10 b | 0..1,023 | **pmaxw** only |
| pipe_stage | slot `s` | 4 b | 0..15 every pixel | every frame |
| pipe_stage | L4 serializer `j` | 5 b | 0..12 | every L4 pixel |
| pipe_out | `sx`, `wx`, `rx` | 16 b | 0..W-1 every row | every frame; 1,017 by pmaxw |
| pipe_out | bank bits `sb`, `wb`, `rb`, `dy`; bank address `{b, x}` | 1 b / 11 b | toggle every row; address <= 2,041 | every frame with >= 2 rows; 2,041 by pmaxw |
| pipe_out | packer count `n` | 3 b | 0..7 | every frame |
| pipe_out | `beats` | 32 b | no wrap: <= 3WH = 12.5 M at W 1018 x H 4096 | 1,555,200 (pfull) |
| sr_pipe_core | `px`, `py` | 16 b | px 0..W+5 every row; py 0..H+5 <= 4,101 | every frame; py 4,101 by ptall |
| sr_pipe_core | `pcnt`, `in_beats` | 32 b | no wrap: <= 4.2 M / 3.2 M | 527,436 / 395,577 (pfull) |
| sr_pipe_core | unpacker `un` | 3 b | 0..7 | every frame |
| sr_pipe_core | `prep` | 3 b | 5 down to 0 | every frame |
| sr_pipe_core | `cycles` | 32 b | no wrap: a 1018 x 4096 frame is about 16 x 1022 x 4100 = 67 M cycles (2^32 = 4,295 M) | 8,398,481 (pfull) |
| sr_accel_top | `frame_w`, `frame_h`; DBG beats | 16 b / 32 b | limits checked at start (W 1..1018, H 1..4096) | refusal of W = 0, W = 1019, H = 0, H = 4097 (`+ERR=1`) |

Counters that never wrap by design (`iy`, `py`, `pcnt`, `in_beats`, `beats`, `cycles`) are shown safe by their range at the largest allowed frame. The
largest frame itself (1018 x 4096, about 67 M cycles) is not simulated. Instead, the two extremes are: the max-width frame **pmaxw** (1018 x 4) and the
max-height frame **ptall** (1 x 4096), both bit-exact in xsim with every stage's output checked.

New tests from this audit: `tb_fifos.v` (quick suite); frames p192, pw960x24, pmaxw, ptall (full suite, xsim); the ERROR_CODE 4 check for H = 4097;
mutants F2 (the old 32-bit occupancy), F3 (FIFO stopping at 2,996 entries: caught by the exact-threshold check of `tb_fifos.v`; among the frames only the max-width one would reach it), A3 (no H cap) and S15 (line-buffer
address one bit short, caught only by W > 506).
