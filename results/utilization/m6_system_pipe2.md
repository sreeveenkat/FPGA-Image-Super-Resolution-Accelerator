# Pipeline v2 (branch `pipe2`, VERSION 0x53526301): Vivado system build

Built 2026-11-10 with `hardware/vivado/scripts/build_m6_system.tcl` (2 jobs), Vivado 2024.1, xc7z020clg484-1, FCLK0 125 MHz (8.000 ns).
Project `~/Desktop/venkat/vitis/m6_sr_pipev2c`; copies of the bitstream, XSA, reports and ELFs in `~/Desktop/venkat/pipe2_artifacts/`.
These are Vivado post-implementation numbers, NOT board measurements. v2 was measured on the board on 2026-11-10 (section "Board result" at the end).

## Result (build 3 = the current bitstream)

| | pipe (branch `pipe`, board-tested) | **pipe2 v2** | Model prediction (`cycle_model.py` Part 6) |
|---|---|---|---|
| Cycles per LR pixel | 16 | **8** | 8 |
| Routed WNS / WHS at 125 MHz | +0.267 / +0.014 ns | **+0.231 / +0.019 ns**, 0 of 47,085 endpoints failing | risk |
| Slice LUT | 9,888 (19 %) | **20,651 (39 %)** | ~27,000 (51 %) |
| Slice registers | 15,782 (15 %) | **21,612 (20 %)** | ~32,600 |
| Block RAM tiles | 27 | **27** | ~25 |
| DSP48E1 | 170 (77 %) | **220 (100 %)** | 220 |
| Power, Vivado vectorless (low confidence) | 2.290 W | **2.900 W** | n/a |
| Simulated cycles, 960x540 frame | 8,398,481 | **4,203,124** (2.00x fewer) | 4.20 M |
| Critical path | | LUT multiplier `s4/tree[11].lane[12].g_lut.u_mul` w_r -> prod (9 logic levels) | |

Per stage (LUT / FF / DSP): s1 1,599 / 1,809 / 58 (54 lanes + 2 requantizers), s2 999 / 3,196 / 22, s3 1,000 / 1,312 / 36,
s4 11,852 / 10,379 / 102 (98 DSP lanes + 118 LUT lanes + 2 requantizers), core 200 / 418 / 2. A LUT multiplier lane costs about
(11,852 - 32 x 216) / 118 = ~42 LUT here, less than the ~96 LUT of `dsp_vs_lut.md` (that was a MAC lane with accumulator; `pipe_mul` is a
bare 8x8 product feeding an adder tree), which is why the model over-predicted LUTs.

Synthesis log checks (`design_1_sr_accel_top_0_0_synth_1/runme.log`): 12/12 weight files read (`wpipe8_L1..4`, `bias_L1..4`, `mult_L1..4`),
`NS bound to: 8` in all stages, `NDSP bound to: 98` on L4, 0 x Synth 8-311, 0 critical warnings (synthesis and implementation).
DRC: same warning types as `pipe` (DPOP-2 MREG pipelining 208, PDCN-1569 3, RTSTAT-10 1; advisory REQP-181 2).

## Builds that led here

| Build | Change | WNS | Worst path |
|---|---|---|---|
| 1 | first v2 build | +0.035 ns | `fw` -> `fw + 2` adder -> s3 column compare -> `ix` reset (7 CARRY4) |
| 2 | stage frame sizes registered in `sr_pipe_core.v` (`sw6/sh6/sw4/sh4/sw2/sh2`, set from `fw/fh` every cycle; the stages start 5 cycles after the accepted start, so no cycle is added: 960x540 still 4,203,124) | +0.093 ns | s2 `d1_v` -> clock enable of the whole 9 x 128-bit window (0 logic levels, 6.9 ns route) |
| 3 | `(* max_fanout = 64 *)` on `d1_v` in `pipe_stage.v` (replication only, no functional change) | **+0.231 ns** | inside a LUT multiplier (the design's natural limit) |

Superseded builds 1 and 2 are kept in `~/Desktop/venkat/pipe2_artifacts/superseded_build*`.

## Verification of this RTL

`run_tests.sh quick` 69/69; mutation test 41 mutants: 39 caught, 2 equivalent (V4 one more LUT lane, C4 redundant line), 0 survived;
960x540 frame in xsim bit-exact 4,203,124 cycles; post-synthesis netlist (MAXW = 32) 4/4 PASS (12/12 weight files, 220 DSP48E1;
frames, stalls, error codes); NS = 16 still reproduces branch `pipe` cycle for cycle (3,241 / 4,433 / 22,089).

## Board software (built; run on the board 2026-11-10)

Platform from this XSA: `~/Desktop/venkat/vitis_ws_pipe2_platform` (xparameters.h byte-identical to the one the `pipe` ELFs used).
ELFs (`software/board/build/`, copies in `pipe2_artifacts/elf/`): t1, t2, t3_20f, t5, t2_x_both and t3_20f_x_both (non-cacheable buffers,
`-DSR_NC_OUT -DSR_NC_PAD`); 0 warnings from our code; the VERSION check compares with 0x53526300 (`mov #0x6300; movt #0x5352`), the `pipe`
ELFs with 0x53525300, so each refuses the other's bitstream. Expected output = the `pipe` output (same R3q weights): fnv 0x45dd4e2d for the
960x540 frame.

## Predicted board numbers (model + board-measured overheads of `pipe`, NOT measured)

Compute 4,203,124 / 125 MHz = 33.6 ms. Cached buffers: + 28.2 ms (pad 5.8 + cache maintenance 22.4, measured on `pipe`, scales with image
size only) = **61.8 ms, 16.2 fps**. Non-cacheable buffers: + 3.3 ms (pad) = **37.0 ms, 27.1 fps**.

## Board result (2026-11-10)
Measured at a read-back 125.000 MHz: T1 20/20, T2 byte-exact (0x45dd4e2d), 119/119 test images, T5 PASS x4, VERSION refusal both ways; 20-frame means 61.64 ms cached and 36.95 ms non-cacheable (27.1 fps). Full regression: 94/94. Details in main: `results/board/2026-11-10/SUMMARY.md`.
