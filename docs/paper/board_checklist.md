# Board checklist: T1/T2 re-run, T7 ARM baseline, R2q, R3q, r0_125, pipelines

Prepared 2026-10-19, updated for the per-design VERSION values. **Nothing below has been run on the board.** Everything on the PC side (simulation, builds, byte-exact C model) is done and listed in
`results/utilization/m6_system_R2q.md` (branch `r2q`) and `results/utilization/m6_system_R3q.md` (branch `r3q`).
Board on the PROG/JTAG USB (J17), boot jumpers on JTAG. Run every `xsdb` command from the project root of the tree named in the heading.

Companion files (2026-10-24): `docs/paper/board_session_runbook.md` (the order of the day and every command), `docs/paper/board_expected.md` (what the board must print for each design, generated from each tree's integer model), `software/board/board_run.sh` (run + UART log capture, PC-tested only).

## 0. The six designs and how to tell them apart

| Name | Weights | Bitstream (outside the repo) | Tree to run from | 960x540 expected fnv1a32 | 128x128 baboon fnv1a32 |
|---|---|---|---|---|---|
| **R0 / 0602** (deployed) | `main` | `~/Desktop/venkat/vitis/m6_sr_0602/m6_sr.runs/impl_1/design_1_wrapper.bit` (default of `run_board.tcl`; fallback copy `~/Desktop/venkat/TESTED_0602.bit`) | `~/Desktop/venkat/sem_project_all` | 0xcf947f22 | 0x91a4506d |
| **R2q** (re-param + QAT, SHIFT 22/22/21/22) | branch `r2q` | `~/Desktop/venkat/R2q_artifacts/design_1_wrapper_R2q.bit` | `~/Desktop/venkat/sandbox_R2q` | 0x2afbc9ae | 0x272bafbb |
| **R3q** (plain + anchor + QAT, SHIFT 22/22/21/25, RTL change) | branch `r3q` | `~/Desktop/venkat/R3q_artifacts/design_1_wrapper_R3q.bit` | `~/Desktop/venkat/sandbox_R3q` | 0x45dd4e2d | 0xa1d2f75c |
| **r0_125** (R0 weights, one more register per engine run, 125 MHz) | branch `r0_125` | `~/Desktop/venkat/R0_125_artifacts/design_1_wrapper_R0_125.bit` | `~/Desktop/venkat/sandbox_R0_125` | 0xcf947f22 (same weights as R0) | 0x91a4506d |
| **r3q_125** (R3q weights + anchor, the r0_125 register, 125 MHz; the owner's final tiled target) | branch `r3q_125` | `~/Desktop/venkat/R3q_125_artifacts/design_1_wrapper_R3q_125.bit` | `~/Desktop/venkat/sandbox_R3q_125` | 0x45dd4e2d (same weights as R3q) | 0xa1d2f75c |
| **pipe** (whole-frame layer pipeline, R3q weights + anchor, 125 MHz, `docs/ARCHITECTURE_PIPELINE.md`) | branch `pipe` | `~/Desktop/venkat/pipe_artifacts/design_1_wrapper_pipe.bit` | `~/Desktop/venkat/sandbox_pipe` | 0x45dd4e2d (same weights as R3q) | 0xa1d2f75c |

**Each design has its own VERSION register value** (read by the ARM driver and printed as `version=` in the stats of every run):

| Design | VERSION |
|---|---|
| R0 / 0602 | `0x53520602` |
| R2q | `0x53522201` |
| R3q | `0x53523201` |
| r0_125 | `0x53524201` |
| r3q_125 | `0x53524301` |
| pipe | `0x53525301` (other register map: FRAME_W/FRAME_H instead of TILE_SIZE, `docs/REGISTER_MAP.md` in that branch) |

Each tree's driver accepts only its own family (`VERSION & 0xFFFFFF00`), so an ELF built in the R2q tree **refuses** to run on any other bitstream (`SR: VERSION 0x..., expected 0x53522201`, result != 0): a loud, free negative control. `run_board.tcl`, `demo.sh`, `run_testsets.sh` and `fresh_load_soak.sh` of the R2q/R3q trees default to their own bitstream and VERSION (override with `SR_BIT` / `SR_EXPECT_VERSION`). The golden tile (T1) and the checksum of the 960x540 output (T2) still prove the weights: each tree has its own `golden_tile.h`, `sr_weights.h` and `data/board/*expected*` made from its own weights. As a second negative control, the first R2q T2 output should also be compared against the R0 expected file: `compare_raw.py` must say `BYTE-EXACT: no`.

`SR_BIT=<path> xsdb software/board/run_board.tcl ...` selects another bitstream (the script reprograms the PL every run, with PS-PL isolation).

## 1. On the PC, before connecting (the ELFs are already built; rebuild only if a source changes)
```bash
source ~/Desktop/vivado_install/Vitis/2024.1/settings64.sh
cd <tree>; .venv/bin/python software/host_tools/golden_tile_h.py; .venv/bin/python software/host_tools/weights_h.py
for n in 1 2 11; do software/board/build_elf.sh $n; done          # T1, T2, T7 (1 frame)
software/board/test_swmodel.sh                                      # T7 code on the PC: 4x PASS byte-exact vs the tree's expected output
```
ELFs in each tree's `software/board/build/`: `sr_app_t1.elf`, `sr_app_t2.elf`, `sr_app_t11.elf` (T7, 1 frame), `sr_app_t11_20f.elf` (T7, 20 frames),
`sr_app_t3_20f.elf` (T3, 20 frames, frame time), `sr_app_t3_200f.elf` (T3, 200 frames, ~4.4 min).
Input files `data/board/div2k_img0193_lr_960x540.raw` (R2q/R3q trees have it; expected output in the same folder).

## 2. Current design (R0 / 0602), from `~/Desktop/venkat/sem_project_all` (main.c changed on 2026-10-16: T1/T2 must be re-run)

| Step | Command | Pass when |
|---|---|---|
| T1 | `xsdb software/board/run_board.tcl software/board/build/sr_app_t1.elf - - t1_r0.txt` | `result=0`, `version=0x53520602`, stat6 = 20, CYCLES 926,210-926,241 (R0 runs seen: 926,217-926,241 in `results/speed/m7_timing_20frames.md`; 926,210-926,216 in the Vitis run of 13 Oct and 926,217-926,220 in the xsdb run of that day: `docs/paper/rehearsal_2026-10-13_notes.md` sections 1-2) |
| T2 | `xsdb software/board/run_board.tcl software/board/build/sr_app_t2.elf data/board/div2k_img0193_lr_960x540.raw t2_r0.raw t2_r0.txt` then `.venv/bin/python software/host_tools/compare_raw.py t2_r0.raw data/board/div2k_img0193_expected_1920x1080.raw` | `BYTE-EXACT: yes`, fnv1a32 0xcf947f22, stat0 about 1,311,000 us |
| T7, 1 frame (never run before) | `xsdb software/board/run_board.tcl software/board/build/sr_app_t11.elf data/board/div2k_img0193_lr_960x540.raw t7_r0.raw t7_r0.txt` then the same `compare_raw.py` with `t7_r0.raw` | `result=0`, `BYTE-EXACT: yes`; record stat1 (time per frame), stat4 pad, stat5 ARM copy, stat6 ARM compute. Expect seconds per frame (scalar C -O2, no NEON, 650 MHz Cortex-A9; not predicted). The PC runs the same C code in 0.9 s. If it exceeds the 900 s timeout of `run_board.tcl`, raise `TIMEOUT_S`. |

## 3. R2q, from `~/Desktop/venkat/sandbox_R2q` (bitstream `~/Desktop/venkat/R2q_artifacts/design_1_wrapper_R2q.bit`, VERSION 0x53522201; this is the tree's default, no `SR_BIT` needed)

| Step | Command | Pass when |
|---|---|---|
| T1 | `xsdb software/board/run_board.tcl software/board/build/sr_app_t1.elf - - t1_r2q.txt` | `result=0`, **`version=0x53522201`**, stat6 = 20 (as for R0; the golden tile is the R2q one), CYCLES 926,210-926,241 (same as R0: only constants changed) |
| T2 (byte-exact) | `xsdb software/board/run_board.tcl software/board/build/sr_app_t2.elf data/board/div2k_img0193_lr_960x540.raw t2_r2q.raw t2_r2q.txt`, then `compare_raw.py t2_r2q.raw data/board/div2k_img0193_expected_1920x1080.raw` | `BYTE-EXACT: yes`, fnv1a32 **0x2afbc9ae**, stat0 about 1,311,000 us |
| negative control (VERSION) | run `sr_app_t1.elf` of the R2q tree once with `SR_BIT=~/Desktop/venkat/vitis/m6_sr_0602/m6_sr.runs/impl_1/design_1_wrapper.bit` | the driver prints `SR: VERSION 0x53520602, expected 0x53522201`, `result` != 0, then run T1 normally again (reprograms the right bitstream) |
| negative control (output) | `compare_raw.py t2_r2q.raw ~/Desktop/venkat/sem_project_all/data/board/div2k_img0193_expected_1920x1080.raw` | `BYTE-EXACT: no` (R2q output differs from R0, as it must) |
| frame time | `xsdb software/board/run_board.tcl software/board/build/sr_app_t3_20f.elf data/board/div2k_img0193_lr_960x540.raw t3_r2q.raw t3_r2q.txt` | 20-frame mean within ±2 ms of R0's 1,311.9 ms, max − min ≤ 3 ms, CYCLES per tile 926,210-926,241 (R0: `results/speed/m7_timing_20frames.md` 926,217-926,241 and T1 of 13 Oct 926,210-926,216, `docs/paper/rehearsal_2026-10-13_notes.md` section 1; identical cycle count: 926,201 per tile in simulation); output byte-exact (fnv 0x2afbc9ae). **Save per-frame times to a file** (see section 6) |
| 119 test images (optional, 11 min) | first `.venv/bin/python software/host_tools/board_testsets.py prep` in the R2q tree (writes the R2q expected outputs, a few minutes on the PC), then `software/board/run_testsets.sh` (M7 script; `SR_BIT` as above, results in `data/board/testsets/`), then `board_testsets.py eval` | 119/119 byte-exact against the R2q integer model |
| T7 | T7 with the R2q tree's `sr_app_t11.elf` | `BYTE-EXACT: yes`, fnv 0x2afbc9ae (the C model has the R2q weights compiled in) |

If T1 fails on R2q: check that the right bitstream was loaded (`SR_BIT`), then run `SR_BIT=~/Desktop/venkat/TESTED_0602.bit` with the R0 T1 to prove the board and
the tooling are fine; then report the failing tile and the `t1_r2q.txt` stats.

## 4. Power

Board power was **not measured** and will not be: no board power session is planned. Every power number in this project is a Vivado
on-chip estimate (vectorless, and for some designs with simulated switching activity): `results/power_estimate/SUMMARY.md`.

## 5. Later: R3q (anchor), from `~/Desktop/venkat/sandbox_R3q` (bitstream `~/Desktop/venkat/R3q_artifacts/design_1_wrapper_R3q.bit`, VERSION 0x53523201; the tree's default)
Only after R2q passed section 3. Same steps as section 3 with the R3q tree's ELFs and files; expected values:

| Step | Pass when |
|---|---|
| T1 | `result=0`, **`version=0x53523201`**, stat6 = 20 (as for R0; the golden tile is the R3q one and includes the anchor path), CYCLES 926,210-926,241 (the anchor adds **no** cycles: simulated 926,201 per tile as before) |
| T2 | `BYTE-EXACT: yes`, fnv1a32 **0x45dd4e2d** |
| negative controls | the R3q output compared with the R2q expected file and with the R0 expected file: `BYTE-EXACT: no` for both |
| frame time | 20-frame mean within ±2 ms of 1,311.9 ms, max − min ≤ 3 ms, CYCLES per tile 926,210-926,241 (see section 2 T1 row and `results/speed/m7_timing_20frames.md`); per-frame times saved to a file |
| T7 | `BYTE-EXACT: yes`, fnv 0x45dd4e2d (anchor compiled into `sr_swmodel.c`) |
| power | not measured on the board (no board power session will be done); Vivado on-chip estimates only, `results/power_estimate/SUMMARY.md` |

Seam and halo alignment are covered in simulation (20-tile and 4-tile seam tests, 26 anchor mutants); the board T2 on a real 960x540 frame (135 tiles) is the first
real-hardware check of the anchor's halo-aligned read.

## 5a. After R3q: r0_125 (R0 weights at 125 MHz), from `~/Desktop/venkat/sandbox_R0_125` (bitstream `~/Desktop/venkat/R0_125_artifacts/design_1_wrapper_R0_125.bit`, VERSION 0x53524201; the tree's default)
Only after R3q (section 5). Built 2026-10-25: routed WNS +0.632 ns at 125.000 MHz, full simulation 88/88, 926,205 cycles per tile in simulation (R0: 926,201); **never run on a board**
(`docs/paper/fmax_plan.md` section 7; `results/utilization/m6_system_R0_125.md` in branch `r0_125`). Commands: `board_session_runbook.md` section 7. Expected values (`board_expected.md`, section "R0 at 125 MHz"):

| Step | Pass when |
|---|---|
| T1 | `result=0`, **`version=0x53524201`**, stat6 = 20, CYCLES each within **926,214-926,245** (the R0 window + 4) |
| T2 | `BYTE-EXACT: yes`, fnv1a32 **0xcf947f22** (same as R0: the weights are unchanged) |
| negative control | the R0-tree ELF must refuse this bitstream (VERSION family 0x535242xx vs 0x535206xx) |
| frame time | 20-frame mean in **1,033-1,064 ms** (predicted 1,061.8 ms, a model value; lower end = core cycles at 125 MHz + ARM padding/copies), max - min <= 3 ms; per-frame times saved |
| power | not measured on the board (no board power session will be done); Vivado on-chip estimates only, `results/power_estimate/SUMMARY.md` |

If T1 or T2 fails: record it, stop, do not retry silently. The final target (R3q at 125 MHz) is built only after R3q and r0_125 both pass on the board (`docs/STATUS.md`).

## 5c. After r0_125: r3q_125 (R3q at 125 MHz), from `~/Desktop/venkat/sandbox_R3q_125` (bitstream `~/Desktop/venkat/R3q_125_artifacts/design_1_wrapper_R3q_125.bit`, VERSION 0x53524301; the tree's default)
Built 2026-10-26: routed WNS +0.393 ns at 125 MHz, quick 42/42, full 95/95, netlist simulation 5/5, 926,205 cycles per tile in simulation; **never run on a board**
(`results/utilization/m6_system_R3q_125.md` in branch `r3q_125`). Commands: `board_session_runbook.md` section 8. Expected values: `board_expected.md`, section "R3q at 125 MHz".

| Step | Pass when |
|---|---|
| T1 | `result=0`, **`version=0x53524301`**, stat6 = 20, CYCLES each within **926,214-926,245** |
| T2 | `BYTE-EXACT: yes`, fnv1a32 **0x45dd4e2d** (same as R3q) |
| 119 test images | `run_testsets.sh` from that tree: 119/119 byte-exact |
| negative control | the R3q-tree ELF must refuse this bitstream (0x535243xx vs 0x535232xx) |
| frame time | 20-frame mean in **1,033-1,064 ms** (prediction as for r0_125), max - min <= 3 ms |
| power | not measured on the board (no board power session will be done); Vivado on-chip estimates only, `results/power_estimate/SUMMARY.md` |

## 5d. The pipeline (`pipe`), from `~/Desktop/venkat/sandbox_pipe` (bitstream `~/Desktop/venkat/pipe_artifacts/design_1_wrapper_pipe.bit`, VERSION 0x53525301; the tree's default)
Built 2026-10-27: routed WNS +0.267 / WHS +0.014 ns at 125 MHz, 170 DSP / 27 BRAM / 9,888 LUT; quick 48/48, full (see `results/utilization/m6_system_pipe.md` in branch
`pipe`), netlist simulation 4/4, 960x540 frame bit-exact in xsim (8,398,481 cycles); **never run on a board**. Different register map and driver (one DMA transfer per frame,
no tiles): run ONLY the ELFs of this tree. Commands: `board_session_runbook.md` section 9. Expected values: `board_expected.md`, section "Pipeline".

| Step | Pass when |
|---|---|
| T1 (golden tile as a 64 x 64 frame) | `result=0`, **`version=0x53525301`**, stat6 = 20, CYCLES each within **74,641-74,700** (simulation 74,641; window PROPOSED) |
| T2 (960x540, one frame) | `BYTE-EXACT: yes`, fnv1a32 **0x45dd4e2d**; stat4..6 = frame CYCLES within **8,398,481-8,440,473** (simulation + 0.5 %, PROPOSED) |
| T5 error recovery | `T5 PASS` (4 bad frames, each followed by a byte-exact good one) |
| 119 test images | `run_testsets.sh` from that tree: 119/119 byte-exact (first whole-frame run on many sizes: a failure here is the most informative result of the session) |
| negative controls | (a) the R3q-tree ELF must refuse this bitstream (VERSION); (b) this tree's T2 output compared with the R0 expected file must say `BYTE-EXACT: no` |
| frame time | 20-frame mean in **73.1-102.3 ms** (PREDICTED from the simulated cycles + R0's measured padding; cache maintenance and DMA set-up not modelled), max - min <= 3 ms; per-frame times saved. The headline number of the session if it passes (R0: 1,311.9 ms) |
| power | not measured on the board (no board power session will be done); Vivado on-chip estimates only, `results/power_estimate/SUMMARY.md` |

If T1 fails here but passed for the tiled designs: the driver/register map is new (FRAME_W/H, one transfer per frame), so first check `version=` and ERROR_CODE in the stats
(4 = size refused, 5 = internal FIFO error), and the UART log. Do not retry silently.

## 5e. Pipeline v2 (`pipe2`), from `~/Desktop/venkat/sandbox_pipe2` (bitstream `~/Desktop/venkat/pipe2_artifacts/design_1_wrapper_pipe2.bit`, VERSION 0x53526301; the tree's default board programs are built against `~/Desktop/venkat/vitis_ws_pipe2_platform`)
**DONE 2026-11-10: every step passed (power not measured); results `results/board/2026-11-10/SUMMARY.md`.**
Added 2026-11-10. 8 cycles per LR pixel (twice the lanes of `pipe`, 220 DSP + 118 LUT multipliers). Built: routed WNS +0.231 / WHS +0.019 ns at 125 MHz, 20,651 LUT /
21,612 FF / 27 BRAM / 220 DSP; quick 69/69, mutation 41 (39 caught, 2 equivalent), netlist simulation 4/4, 960x540 bit-exact in xsim (4,203,124 cycles)
(`results/utilization/m6_system_pipe2.md` in branch `pipe2`); **never run on a board**. Same register map and driver as `pipe`; MUST run at 125 MHz with the XSA's own
ps7_init (md5 d2a7789c..., identical to the other 125 MHz designs): `run_125.py pipe2` does that and refuses to run if FCLK0 is not 125 MHz. Commands: runbook section 10.

| Step | Pass when |
|---|---|
| T1 (golden tile as a 64 x 64 frame) | `result=0`, **`version=0x53526301`**, stat6 = 20, CYCLES each within **37,620-37,679** (simulation 37,620; window = `pipe`'s board offset +11..+40 plus margin, PROPOSED) |
| T2 (960x540) | `BYTE-EXACT: yes`, fnv1a32 **0x45dd4e2d** (same as `pipe`: same weights); frame CYCLES within **4,203,124-4,224,140** (simulation + 0.5 %, PROPOSED) |
| T5 error recovery | `T5 PASS` |
| 119 test images | 119/119 byte-exact (`run_125.py pipe2`) |
| negative controls | (a) a `pipe`-tree ELF must refuse this bitstream (compares 0x53525300; this tree's ELF compares 0x53526300); (b) this tree's ELF must refuse the `pipe` bitstream |
| frame time, cached (`sr_app_t3_20f.elf`) | 20-frame mean in **59.8-63.8 ms** (PREDICTED: 33.6 ms compute + `pipe`'s measured 28.2 ms pad + cache maintenance, +-2 ms), max - min <= 3 ms |
| frame time, non-cacheable (`sr_app_t3_20f_x_both.elf`) | 20-frame mean in **35.0-39.0 ms** = 27 fps (PREDICTED: 33.6 + 3.3 ms pad, +-2 ms), byte-exact; the headline number if it passes (`pipe` NC: 70.52 ms) |
| temperature | die temperature logged (`xadc_temp.tcl`); stop above 70 C (all 220 DSPs busy: expect more heat than `pipe`'s 47.7-50.6 C) |
| power | not measured on the board (no board power session will be done); Vivado on-chip estimates only, `results/power_estimate/SUMMARY.md` |

If T1 fails here but `pipe` passed in the same session: the only RTL differences are in `pipe_stage.v` (NS = 8 lanes/requantizers, LUT multipliers, `max_fanout` on `d1_v`) and
`sr_pipe_core.v` (registered stage sizes, `wpipe8_*` ROMs). First check `version=`, ERROR_CODE (5 = internal FIFO error) and that FCLK0 read back 125 MHz.

## 5f. Pipeline v2 PACKED (`pipe2p`), from `~/Desktop/venkat/sandbox_pipe2p` (bitstream `~/Desktop/venkat/pipe2p_artifacts/design_1_wrapper_pipe2p.bit`, VERSION 0x53527301; board programs built against `~/Desktop/venkat/vitis_ws_pipe2p_platform`)
**DONE 2026-11-10: every step passed (power not measured); results `results/board/2026-11-10/SUMMARY.md`.**
Added 2026-11-10. Same speed as `pipe2` (8 cycles per LR pixel, +1 cycle per frame), two multiplies per DSP48 (`pipe_mul2.v`). Built: routed WNS +0.450 / WHS +0.007 ns at 125 MHz,
13,323 LUT / 19,688 FF / 27 BRAM / 190 DSP, 0 LUT multipliers; quick 99/99, mutation 48 (45 caught, 3 equivalent, 0 survived), netlist 4/4, 960x540 bit-exact in xsim
(4,203,125 cycles); **never run on a board**. Same register map, driver and ps7_init (md5 d2a7789c...) as `pipe2`. Commands: runbook section 11.
Note the small hold margin (WHS +0.007 ns, met).

| Step | Pass when |
|---|---|
| T1 (golden tile as 64 x 64 frame) | `result=0`, **`version=0x53527301`**, stat6 = 20, CYCLES each within **37,621-37,680** (simulation 37,621; PROPOSED) |
| T2 (960x540) | `BYTE-EXACT: yes`, fnv1a32 **0x45dd4e2d**; frame CYCLES within **4,203,125-4,224,141** (simulation + 0.5 %, PROPOSED) |
| T5 error recovery | `T5 PASS` |
| 119 test images | 119/119 byte-exact (`run_125.py pipe2p`) |
| negative controls | the `pipe2`-tree ELF must refuse this bitstream (0x535263xx vs 0x535273xx) and this tree's ELF must refuse the `pipe2` bitstream |
| frame time | cached 59.8-63.8 ms, non-cacheable 35.0-39.0 ms (PREDICTED, same as `pipe2`) |
| temperature | as 5e |

## 5g. Pipeline v3 (`pipe3`: v2 packed + PL padding, 142.857 MHz), from `~/Desktop/venkat/sandbox_pipe3` (bitstream `~/Desktop/venkat/pipe3_artifacts/design_1_wrapper_pipe3.bit`, VERSION 0x53528301; board programs built against `~/Desktop/venkat/vitis_ws_pipe3_platform`)
**DONE 2026-11-18: every step passed (power not measured); 29.44 ms = 34.0 fps non-cacheable, 51.4 ms cached, 119/119 byte-exact at a read-back 142.857 MHz; results `results/board/2026-11-18/SUMMARY.md`.**
Added 2026-11-18. Same datapath and output as `pipe2p`; new: CONFIG register 0x28 (PAD_EN: the DMA sends the RAW frame, the PL pads it),
FCLK0 **142.857 MHz** (IO PLL / 7; its own XSA ps7_init, md5 dd869514..., FPGA0_CLK_CTRL 0x00100700), AXI DMA memory side 64 bit (needed for timing).
Built: routed WNS +0.132 / WHS +0.015 ns at 142.857 MHz, 13,334 LUT / 19,938 FF / 29.5 BRAM / 190 DSP. Design note and verification: `docs/ARCHITECTURE_PIPELINE_V3.md` and
`results/utilization/m6_system_pipe3.md` in the branch. Commands: runbook section 12. **Clock check:** every run must read back 142.857 MHz (`fclk0_mhz=142.857` in the stats);
`run_125.py pipe3` enforces it (SR_EXPECT_MHZ 142.857). Watch the die temperature (higher clock; abort above 70 C as before).

| Step | Pass when |
|---|---|
| T1 (golden tile as a PADDED 64 x 64 frame, PAD_EN = 0) | `result=0`, **`version=0x53528301`**, stat6 = 20, CYCLES each within **37,621-37,680** (simulation 37,621, same as pipe2p; PROPOSED) |
| T2 (960x540, RAW frame, PAD_EN = 1) | `BYTE-EXACT: yes`, fnv1a32 **0x45dd4e2d** (same as pipe2p); frame CYCLES within **4,205,054-4,226,080** (xsim + 0.5 %, PROPOSED); pad time printed as 0 |
| T5 error recovery | `T5 PASS` (uses the padded golden tile) |
| 119 test images | 119/119 byte-exact (`run_125.py pipe3`; raw frames, PL padding, odd sizes included) |
| negative controls | the `pipe2p`-tree ELF must refuse this bitstream (0x535273xx vs 0x535283xx) and this tree's ELF must refuse the `pipe2p` bitstream |
| frame time (PREDICTED, `run_nc.py --design pipe3`) | non-cacheable in + out (`both`) 27.4-31.5 ms (29.4 = 34 fps); ARM-padding variant on the same bitstream (`armpad`) 30.7-34.7 ms; cached (`fnv`) 49.7-53.7 ms |
| power | not measured on the board (no board power session will be done); Vivado on-chip estimates only, `results/power_estimate/SUMMARY.md` |

## 5h. Pipeline v4 (`pipe4`: 6 cycles per LR pixel + PL padding, 142.857 MHz), from `~/Desktop/venkat/sandbox_pipe4` (bitstream `~/Desktop/venkat/pipe4_artifacts/design_1_wrapper_pipe4.bit`, VERSION 0x53529301; board programs against `~/Desktop/venkat/vitis_ws_pipe4_platform`)
**DONE 2026-11-18 (built and board-tested the same day): 22.10 ms = 45.2 fps non-cacheable, 44.1 ms cached, 119/119 byte-exact at a read-back 142.857 MHz; `results/board/2026-11-18/SUMMARY.md` section 1b.**
Same register map and ps7_init as pipe3. Built: WNS +0.038 / WHS +0.004 ns at 142.857 MHz (strategy Performance_ExtraTimingOpt), 24,783 LUT / 213 DSP. Commands: runbook section 13.

| Step | Pass when |
|---|---|
| T1 (padded golden tile) | `version=0x53529301`, stat6 = 20, CYCLES 28,365-28,424 |
| T2 (RAW 960x540) | byte-exact 0x45dd4e2d, frame CYCLES 3,156,214-3,171,995 |
| 119 test images | 119/119 byte-exact |
| negative controls | the pipe3 ELF refuses this bitstream and vice versa |
| frame time | `both` 20.1-24.1 ms, `armpad` 23.4-27.4 ms, `fnv` 42.4-46.4 ms |

## 5b. Merge criteria (PROPOSED, the owner confirms; same text as `docs/STATUS.md`)
A branch goes into `main` only if, with its own bitstream: (1) T1 passes with its own VERSION and T2 is byte-exact with its fnv1a32 (R2q 0x2afbc9ae, R3q 0x45dd4e2d);
(2) all 119 test images are byte-exact against its integer model; (3) the 20-frame mean is within ±2 ms of 1,311.9 ms, max − min ≤ 3 ms and CYCLES per tile are within 926,210-926,241 (R0: 926,217-926,241 in `results/speed/m7_timing_20frames.md` / `m7_t3_20frames_stats.txt`, 926,210-926,216 on T1 of 13 Oct, `docs/paper/rehearsal_2026-10-13_notes.md` section 1; basis: same-design runs differ by up to 1.0 ms in the mean and single frames reach +2.1 ms, `results/speed/m6_board.md:71`); (4) the negative controls behave as expected;
(5) 100 MHz timing stays met (R2q WNS +0.944 ns, R3q +0.683 ns as built). R3q replaces R2q only if its cost (+33 to +45 LUT, +66 FF, no extra cycle) is acceptable for its
gain (+0.26 / +0.20 / +0.13 dB PSNR-Y over R2q, 2-seed means); if R3q fails any item, R2q goes first.

## 6. What to send back
`t1_*.txt`, `t2_*.txt`, `t3_*.txt`, `t7_*.txt`, the `compare_raw.py` lines (including the negative controls), and which bitstream file was used for each run (`SR_BIT`). **Save per-frame times to a file on every board run** (T3/T7 print one line per frame on the UART, `main.c`: `frame N: total ... us`; the stats file only keeps mean/min/max, so the std cannot be computed from it): `run_board.tcl` does **not** store the UART text (it reads the numbers from DDR), so use `software/board/board_run.sh <name> <elf> <in> <out>`: it starts `uart_capture.py` first and writes
`data/board/<date>/<name>.log` (every line timestamped), `<name>_xsdb.log`, `<name>_meta.txt` (git revision, ELF and bitstream md5, command). It is tested on the PC only (`software/board/test_uart_capture.py`, pty + fake xsdb), **not on the board**. Any `FAIL`/`result` other than 0: send the stats file and the last 30 lines of the console.

## 7. Known issues
| Issue | State | What to do on the day |
|---|---|---|
| **`demo.sh` took 961 s instead of ~25 s** on 13 Oct (60 / 360 / 961 s, three times; xsdb finished its work in ~2 s but did not exit until the `timeout` fired). Facts: `docs/paper/rehearsal_2026-10-13_notes.md` section 4. | **Cause reproduced on the PC without the board** (2026-10-24): `timeout N xsdb ...` with the terminal as stdin hangs until the timeout (exit 124 after 25.0 s, `rlwrap: Unexpected error: Input/output error`); `< /dev/null` or `timeout --foreground` exits 0 in 0.93 s. Fix applied in `demo.sh` (both, plus a clear failure message at the hard limit). **UNTESTED ON THE BOARD.** | Run `software/board/demo.sh` once first. If a step prints "xsdb did not exit within N s", the fix did not carry over to the real xsdb call: note which step and use `board_run.sh`/run_board.tcl directly. The scripts `run_testsets.sh`, `fresh_load_soak.sh`, `soak_test.sh`, `stale_test.sh` use the old pattern: start them as `script.sh < /dev/null`. |
| **Per-frame times and UART text were never stored.** The ARM prints `  frame N: total ... us = pad ... + ARM tile copy ... + DMA/compute wait ...` (T3) and `  frame N: total ... us = ... + ARM compute ...` (T7) on the UART (`sr_app/main.c`), `run_board.tcl` keeps only mean/min/max. | Host-side capture written (`uart_capture.py`, `board_run.sh`), PC-tested, **not board-tested**. No firmware change. | Save **every** UART log and per-frame time under `data/board/<date>/` (`board_run.sh` does it). Close picocom first (one reader per port). `/dev/ttyACM0` needs no sudo for the `dialout` group (the user is in it). |
| CYCLES window: the same bitstream gave 926,210-926,216 (Vitis run) and 926,217-926,241 (xsdb runs). | Cause not investigated; the window 926,210-926,241 covers both. | Record which tool ran the test next to every CYCLES number. |
| `run_board.tcl` stops waiting after 900 s (`TIMEOUT_S`); T7 (ARM only) has never run, its time per frame is unknown. | Open. | If T7 reports "no ready marker after 900 s", raise `TIMEOUT_S` and `XSDB_TIMEOUT` and run again. |
