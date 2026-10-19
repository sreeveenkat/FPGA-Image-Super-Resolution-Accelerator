# Board checklist: T1/T2 re-run, T7 ARM baseline, R2q, power, and later R3q

Prepared 2026-10-19, updated for the per-design VERSION values. **Nothing below has been run on the board.** Everything on the PC side (simulation, builds, byte-exact C model) is done and listed in
`results/utilization/m6_system_R2q.md` (branch `r2q`) and `results/utilization/m6_system_R3q.md` (branch `r3q`).
Board on the PROG/JTAG USB (J17), boot jumpers on JTAG. Run every `xsdb` command from the project root of the tree named in the heading.

## 0. The three designs and how to tell them apart

| Name | Weights | Bitstream (outside the repo) | Tree to run from | 960x540 expected fnv1a32 | 128x128 baboon fnv1a32 |
|---|---|---|---|---|---|
| **R0 / 0602** (deployed) | `main` | `~/Desktop/venkat/vitis/m6_sr_0602/m6_sr.runs/impl_1/design_1_wrapper.bit` (default of `run_board.tcl`; fallback copy `~/Desktop/venkat/TESTED_0602.bit`) | `~/Desktop/venkat/sem_project_all` | 0xcf947f22 | 0x91a4506d |
| **R2q** (re-param + QAT, SHIFT 22/22/21/22) | branch `r2q` | `~/Desktop/venkat/R2q_artifacts/design_1_wrapper_R2q.bit` | `~/Desktop/venkat/sandbox_R2q` | 0x2afbc9ae | 0x272bafbb |
| **R3q** (plain + anchor + QAT, SHIFT 22/22/21/25, RTL change) | branch `r3q` | `~/Desktop/venkat/R3q_artifacts/design_1_wrapper_R3q.bit` | `~/Desktop/venkat/sandbox_R3q` | 0x45dd4e2d | 0xa1d2f75c |

**Each design has its own VERSION register value** (read by the ARM driver and printed as `version=` in the stats of every run):

| Design | VERSION |
|---|---|
| R0 / 0602 | `0x53520602` |
| R2q | `0x53522201` |
| R3q | `0x53523201` |

Each tree's driver accepts only its own family (`VERSION & 0xFFFFFF00`), so an ELF built in the R2q tree **refuses** to run on any other bitstream (`SR: VERSION 0x..., expected 0x53522201`, result != 0): a loud, free negative control. `run_board.tcl`, `demo.sh`, `run_testsets.sh` and `fresh_load_soak.sh` of the R2q/R3q trees default to their own bitstream and VERSION (override with `SR_BIT` / `SR_EXPECT_VERSION`). The golden tile (T1) and the checksum of the 960x540 output (T2) still prove the weights: each tree has its own `golden_tile.h`, `sr_weights.h` and `data/board/*expected*` made from its own weights. As a second negative control, the first R2q T2 output should also be compared against the R0 expected file: `compare_raw.py` must say `BYTE-EXACT: no`.

`SR_BIT=<path> xsdb software/board/run_board.tcl ...` selects another bitstream (the script reprograms the PL every run, with PS-PL isolation).

## 1. On the PC, before connecting (the ELFs are already built; rebuild only if a source changes)
```bash
source ~/Desktop/vivado_install/Vitis/2024.1/settings64.sh
cd <tree>; .venv/bin/python software/host_tools/golden_tile_h.py; .venv/bin/python software/host_tools/weights_h.py
for n in 1 2 11; do software/board/build_elf.sh $n; done          # T1, T2, T7 (1 frame)
software/board/test_swmodel.sh                                      # T7 code on the PC: 4x PASS byte-exact vs the tree's expected output
```
ELFs in each tree's `software/board/build/`: `sr_app_t1.elf`, `sr_app_t2.elf`, `sr_app_t11.elf` (T7, 1 frame), `sr_app_t11_20f.elf` (T7, 20 frames, power),
`sr_app_t3_20f.elf` (T3, 20 frames, frame time), `sr_app_t3_200f.elf` (T3, 200 frames, ~4.4 min, power).
Input files `data/board/div2k_img0193_lr_960x540.raw` (R2q/R3q trees have it; expected output in the same folder).

## 2. Current design (R0 / 0602), from `~/Desktop/venkat/sem_project_all` (main.c changed on 2026-10-16: T1/T2 must be re-run)

| Step | Command | Pass when |
|---|---|---|
| T1 | `xsdb software/board/run_board.tcl software/board/build/sr_app_t1.elf - - t1_r0.txt` | `result=0`, `version=0x53520602`, stat6 = 20, CYCLES 926,217-926,241 |
| T2 | `xsdb software/board/run_board.tcl software/board/build/sr_app_t2.elf data/board/div2k_img0193_lr_960x540.raw t2_r0.raw t2_r0.txt` then `.venv/bin/python software/host_tools/compare_raw.py t2_r0.raw data/board/div2k_img0193_expected_1920x1080.raw` | `BYTE-EXACT: yes`, fnv1a32 0xcf947f22, stat0 about 1,311,000 us |
| T7, 1 frame (never run before) | `xsdb software/board/run_board.tcl software/board/build/sr_app_t11.elf data/board/div2k_img0193_lr_960x540.raw t7_r0.raw t7_r0.txt` then the same `compare_raw.py` with `t7_r0.raw` | `result=0`, `BYTE-EXACT: yes`; record stat1 (time per frame), stat4 pad, stat5 ARM copy, stat6 ARM compute. Expect seconds per frame (scalar C -O2, no NEON, 650 MHz Cortex-A9; not predicted). The PC runs the same C code in 0.9 s. If it exceeds the 900 s timeout of `run_board.tcl`, raise `TIMEOUT_S`. |

## 3. R2q, from `~/Desktop/venkat/sandbox_R2q` (bitstream `~/Desktop/venkat/R2q_artifacts/design_1_wrapper_R2q.bit`, VERSION 0x53522201; this is the tree's default, no `SR_BIT` needed)

| Step | Command | Pass when |
|---|---|---|
| T1 | `xsdb software/board/run_board.tcl software/board/build/sr_app_t1.elf - - t1_r2q.txt` | `result=0`, **`version=0x53522201`**, stat6 = 20 (as for R0; the golden tile is the R2q one), CYCLES 926,217-926,241 (same as R0: only constants changed) |
| T2 (byte-exact) | `xsdb software/board/run_board.tcl software/board/build/sr_app_t2.elf data/board/div2k_img0193_lr_960x540.raw t2_r2q.raw t2_r2q.txt`, then `compare_raw.py t2_r2q.raw data/board/div2k_img0193_expected_1920x1080.raw` | `BYTE-EXACT: yes`, fnv1a32 **0x2afbc9ae**, stat0 about 1,311,000 us |
| negative control (VERSION) | run `sr_app_t1.elf` of the R2q tree once with `SR_BIT=~/Desktop/venkat/vitis/m6_sr_0602/m6_sr.runs/impl_1/design_1_wrapper.bit` | the driver prints `SR: VERSION 0x53520602, expected 0x53522201`, `result` != 0, then run T1 normally again (reprograms the right bitstream) |
| negative control (output) | `compare_raw.py t2_r2q.raw ~/Desktop/venkat/sem_project_all/data/board/div2k_img0193_expected_1920x1080.raw` | `BYTE-EXACT: no` (R2q output differs from R0, as it must) |
| frame time | `xsdb software/board/run_board.tcl software/board/build/sr_app_t3_20f.elf data/board/div2k_img0193_lr_960x540.raw t3_r2q.raw t3_r2q.txt` | mean frame time within 1 ms of R0's 1,311.9 ms (identical cycle count: 926,201 per tile in simulation); output byte-exact (fnv 0x2afbc9ae) |
| 119 test images (optional, 11 min) | first `.venv/bin/python software/host_tools/board_testsets.py prep` in the R2q tree (writes the R2q expected outputs, a few minutes on the PC), then `software/board/run_testsets.sh` (M7 script; `SR_BIT` as above, results in `data/board/testsets/`), then `board_testsets.py eval` | 119/119 byte-exact against the R2q integer model |
| T7 | T7 with the R2q tree's `sr_app_t11.elf` | `BYTE-EXACT: yes`, fnv 0x2afbc9ae (the C model has the R2q weights compiled in) |

If T1 fails on R2q: check that the right bitstream was loaded (`SR_BIT`), then run `SR_BIT=~/Desktop/venkat/TESTED_0602.bit` with the R0 T1 to prove the board and
the tooling are fine; then report the failing tile and the `t1_r2q.txt` stats.

## 4. Power measurement (current design and R2q)

**What to measure:** the ZedBoard's 12 V input power (whole board: Zynq, DDR, regulators, USB-UART, LEDs). The board overhead is the same in every state, so the
**differences** between states are the useful numbers. The synthesis power estimates are 1.913 W (0602) and 1.912 W (R2q), both "low confidence"; the measurement
replaces them.

**How (choose one, write down which):**
* an inline DC power meter between the 12 V adapter and the barrel jack (simplest; note the model and its stated accuracy), or
* a multimeter on the ZedBoard's current-sense point of the 12 V rail (I = V_sense / R_sense). **Check the header and the resistor value in the ZedBoard Hardware User
  Guide first** (not verified here).

**States** (steady room temperature, wait 30 s in each state, read the meter at least 5 times or log it, note the time):

| # | State | How to get there |
|---|---|---|
| P0 | board on, PL not programmed | power on, do nothing |
| P1a | 0602 programmed, ARM idle | R0 T1 (ends in an idle loop), read after it finished |
| P2a | 0602 accelerator running | R0 `sr_app_t3_200f.elf` (200 frames, ~4.4 min), read during the run |
| P1b | R2q programmed, ARM idle | R2q T1 |
| P2b | R2q accelerator running | R2q `sr_app_t3_200f.elf` |
| P3 | ARM only running | `sr_app_t11_20f.elf` (20 frames), read during the run |

Order: P0, P1a, P2a, P1b, P2b, P3, then **repeat P1a, P2a, P1b, P2b** once more in the opposite order (drift check). The 0602 and R2q fabrics are logically identical
apart from constants, so P2a and P2b should agree within the meter's accuracy: if they differ by more than that, say so rather than averaging.

| Quantity | Formula | Value |
|---|---|---|
| Energy per frame, FPGA, whole board | P2 x 1.312 s | J |
| Energy per frame, FPGA, above idle | (P2 - P1) x 1.312 s | J |
| Energy per frame, ARM-only, whole board | P3 x (T7 time per frame) | J |
| Energy per frame, ARM-only, above idle | (P3 - P1) x (T7 time per frame) | J |

PC side for the same table: `sudo .venv/bin/python software/analysis/cpu_baseline.py --md docs/paper/cpu_baseline.md` adds CPU package energy (RAPL); the GPU row
(nvidia-smi) is already measured: 0.55 J per frame, GPU power only.

## 5. Later: R3q (anchor), from `~/Desktop/venkat/sandbox_R3q` (bitstream `~/Desktop/venkat/R3q_artifacts/design_1_wrapper_R3q.bit`, VERSION 0x53523201; the tree's default)
Only after R2q passed section 3. Same steps as section 3 with the R3q tree's ELFs and files; expected values:

| Step | Pass when |
|---|---|
| T1 | `result=0`, **`version=0x53523201`**, stat6 = 20 (as for R0; the golden tile is the R3q one and includes the anchor path), CYCLES 926,217-926,241 (the anchor adds **no** cycles: simulated 926,201 per tile as before) |
| T2 | `BYTE-EXACT: yes`, fnv1a32 **0x45dd4e2d** |
| negative controls | the R3q output compared with the R2q expected file and with the R0 expected file: `BYTE-EXACT: no` for both |
| frame time | 20-frame mean within 1 ms of 1,311.9 ms |
| T7 | `BYTE-EXACT: yes`, fnv 0x45dd4e2d (anchor compiled into `sr_swmodel.c`) |
| power | repeat P1/P2 for R3q (P1c, P2c); expected within meter accuracy of R2q (+45 LUT, +66 FF in the whole system) |

Seam and halo alignment are covered in simulation (20-tile and 4-tile seam tests, 26 anchor mutants); the board T2 on a real 960x540 frame (135 tiles) is the first
real-hardware check of the anchor's halo-aligned read.

## 6. What to send back
`t1_*.txt`, `t2_*.txt`, `t3_*.txt`, `t7_*.txt` (and the stats of the two power runs), the `compare_raw.py` lines (including the negative controls), the meter readings with the
meter model, and which bitstream file was used for each run (`SR_BIT`). Any `FAIL`/`result` other than 0: send the stats file and the last 30 lines of the console.
