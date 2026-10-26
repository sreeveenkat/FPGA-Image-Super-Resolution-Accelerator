# Board checklist: T1/T2 re-run, T7 ARM baseline, R2q, R3q, r0_125, power

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
ELFs in each tree's `software/board/build/`: `sr_app_t1.elf`, `sr_app_t2.elf`, `sr_app_t11.elf` (T7, 1 frame), `sr_app_t11_20f.elf` (T7, 20 frames, power),
`sr_app_t3_20f.elf` (T3, 20 frames, frame time), `sr_app_t3_200f.elf` (T3, 200 frames, ~4.4 min, power).
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

## 4. Power measurement (every bitstream: R0, R2q, R3q, r0_125, r3q_125, pipe; plus ARM only)

**What to measure:** the ZedBoard's 12 V input power (whole board: Zynq, DDR, regulators, USB-UART, LEDs). The board overhead is the same in every state, so the
**differences** between states are the useful numbers. The synthesis power estimates are 1.913 W (0602) and 1.910 W (R2q, current VERSION 0x53522201 build; `m6_system_R2q.md:45` in branch `r2q`; the 1.912 W on its line 6 is the superseded first build), both "low confidence"; the measurement
replaces them.

**How (owner decision 2026-10-26).**
* **Primary: an inline DC power meter between the 12 V adapter and the barrel jack.** Write down its model, range, stated accuracy, resolution and reading/averaging interval. Use the same meter and range for every state.
* **Cross-check: J21.** J21 is across a **10 mOhm, 1 W** current-sense resistor in series with the 12 V input (forum quotes of the ZedBoard Hardware User's Guide; **page citation to be added by the owner**: until then this value is not cited from the guide itself). Multimeter in mV mode across the J21 pins: I = V_J21 / 0.010 Ohm, P = I x V_in. At about 0.5 A the drop is about 5 mV, so the meter needs at least 0.01 mV resolution. Probe only (voltage mode); never load the header.
* **Measure the actual input voltage** in every state (the inline meter shows it; otherwise a multimeter at the jack); do not assume 12.00 V.
* **Average several readings per state:** wait 30 s after entering the state, then take at least 5 readings (or the meter's log) spread over at least 30 s; report mean, min, max and the number of readings. Inline meter and J21 are read in the same window.
* If the two methods disagree by more than their combined stated accuracy, report both and say so; do not pick one afterwards.

**Board-level power, not comparable to Vivado's on-chip estimate.** This is the whole ZedBoard's 12 V input (Zynq, DDR, regulators, USB-UART, LEDs, conversion losses). The Vivado numbers (1.913 W, 1.910 W) are the on-chip estimate of the Zynq only. Never put the two in one row without saying so, and never compare a board-level absolute with the estimate; compare the **delta** only.

**States: idle and processing for each bitstream** (steady room temperature; averaging as above; note the start and end time of each window):

| # | State | How to get there | Tree |
|---|---|---|---|
| P0 | board on, PL not programmed | power on, do nothing | - |
| P1-R0 / P2-R0 | 0602 programmed, ARM idle / accelerator running | T1 (ends in an idle loop), read after it finished / `sr_app_t3_200f.elf` (200 frames, ~4.4 min), read during the run | R0 |
| P1-R2q / P2-R2q | same for R2q | same ELFs | R2q |
| P1-R3q / P2-R3q | same for R3q | same ELFs | R3q |
| P1-125 / P2-125 | same for r0_125 (125 MHz) | same ELFs (200 frames at ~1.06 s each, predicted, ~3.5 min) | r0_125 |
| P3 | ARM only running (PL programmed with R0) | `sr_app_t11_20f.elf` (20 frames), read during the run | R0 |

Order: P0, then idle/processing for R0, R2q, R3q, r0_125 (each design only after its functional steps passed), P3, then **repeat P1-R0 / P2-R0** at the end (drift check: if the repeat differs by more than the meter accuracy, say so rather than averaging).
R0 and R2q fabrics are logically identical apart from constants, so their P2 should agree within the meter accuracy; R3q adds 33-45 LUT; r0_125 runs at a 25 % higher clock and is expected to draw more (not predicted; the Vivado estimates use different methods).

**Reported per bitstream (owner decision):** idle power P1, processing power P2, accelerator delta P2 - P1, and P1 - P0 (cost of a configured but idle PL); each from the inline meter (primary) with the J21 value beside it.

| Quantity | Formula | Value |
|---|---|---|
| Energy per frame, FPGA, whole board (per bitstream) | P2 x (that design's measured T3 frame time; 1.312 s for R0) | J |
| Energy per frame, FPGA, above idle (per bitstream) | (P2 - P1) x (that design's measured frame time) | J |
| Energy per frame, ARM-only, whole board | P3 x (T7 time per frame) | J |
| Energy per frame, ARM-only, above idle | (P3 - P1) x (T7 time per frame) | J |

PC side for the same table: `sudo .venv/bin/python software/analysis/cpu_baseline.py --md docs/paper/cpu_baseline.md` adds CPU package energy (RAPL); the GPU row
(nvidia-smi) is already measured: 0.55 J per frame, GPU power only.

## 5. Later: R3q (anchor), from `~/Desktop/venkat/sandbox_R3q` (bitstream `~/Desktop/venkat/R3q_artifacts/design_1_wrapper_R3q.bit`, VERSION 0x53523201; the tree's default)
Only after R2q passed section 3. Same steps as section 3 with the R3q tree's ELFs and files; expected values:

| Step | Pass when |
|---|---|
| T1 | `result=0`, **`version=0x53523201`**, stat6 = 20 (as for R0; the golden tile is the R3q one and includes the anchor path), CYCLES 926,210-926,241 (the anchor adds **no** cycles: simulated 926,201 per tile as before) |
| T2 | `BYTE-EXACT: yes`, fnv1a32 **0x45dd4e2d** |
| negative controls | the R3q output compared with the R2q expected file and with the R0 expected file: `BYTE-EXACT: no` for both |
| frame time | 20-frame mean within ±2 ms of 1,311.9 ms, max − min ≤ 3 ms, CYCLES per tile 926,210-926,241 (see section 2 T1 row and `results/speed/m7_timing_20frames.md`); per-frame times saved to a file |
| T7 | `BYTE-EXACT: yes`, fnv 0x45dd4e2d (anchor compiled into `sr_swmodel.c`) |
| power | idle and processing for R3q (P1-R3q, P2-R3q, section 4); expected within meter accuracy of R2q (+33 to +45 LUT, +66 FF, 0 DSP, 0 BRAM in the whole system: simulation/synthesis numbers, `m6_system_R3q.md` in branch `r3q`, not board-measured) |

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
| power | idle and processing for r0_125 (P1-125, P2-125, section 4) |

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
| power | idle and processing (section 4) |

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
| power | idle and processing (section 4); the PL runs with 170 of 220 DSPs busy, so this is the design where the processing - idle difference should be largest |

If T1 fails here but passed for the tiled designs: the driver/register map is new (FRAME_W/H, one transfer per frame), so first check `version=` and ERROR_CODE in the stats
(4 = size refused, 5 = internal FIFO error), and the UART log. Do not retry silently.

## 5b. Merge criteria (PROPOSED, the owner confirms; same text as `docs/STATUS.md`)
A branch goes into `main` only if, with its own bitstream: (1) T1 passes with its own VERSION and T2 is byte-exact with its fnv1a32 (R2q 0x2afbc9ae, R3q 0x45dd4e2d);
(2) all 119 test images are byte-exact against its integer model; (3) the 20-frame mean is within ±2 ms of 1,311.9 ms, max − min ≤ 3 ms and CYCLES per tile are within 926,210-926,241 (R0: 926,217-926,241 in `results/speed/m7_timing_20frames.md` / `m7_t3_20frames_stats.txt`, 926,210-926,216 on T1 of 13 Oct, `docs/paper/rehearsal_2026-10-13_notes.md` section 1; basis: same-design runs differ by up to 1.0 ms in the mean and single frames reach +2.1 ms, `results/speed/m6_board.md:71`); (4) the negative controls behave as expected;
(5) 100 MHz timing stays met (R2q WNS +0.944 ns, R3q +0.683 ns as built). R3q replaces R2q only if its cost (+33 to +45 LUT, +66 FF, no extra cycle) is acceptable for its
gain (+0.26 / +0.20 / +0.13 dB PSNR-Y over R2q, 2-seed means); if R3q fails any item, R2q goes first.

## 6. What to send back
`t1_*.txt`, `t2_*.txt`, `t3_*.txt`, `t7_*.txt` (and the stats of the two power runs), the `compare_raw.py` lines (including the negative controls), the meter readings with the
meter model, and which bitstream file was used for each run (`SR_BIT`). **Save per-frame times to a file on every board run** (T3/T7 print one line per frame on the UART, `main.c`: `frame N: total ... us`; the stats file only keeps mean/min/max, so the std cannot be computed from it): `run_board.tcl` does **not** store the UART text (it reads the numbers from DDR), so use `software/board/board_run.sh <name> <elf> <in> <out>`: it starts `uart_capture.py` first and writes
`data/board/<date>/<name>.log` (every line timestamped), `<name>_xsdb.log`, `<name>_meta.txt` (git revision, ELF and bitstream md5, command). It is tested on the PC only (`software/board/test_uart_capture.py`, pty + fake xsdb), **not on the board**. Any `FAIL`/`result` other than 0: send the stats file and the last 30 lines of the console.

## 7. Known issues
| Issue | State | What to do on the day |
|---|---|---|
| **`demo.sh` took 961 s instead of ~25 s** on 13 Oct (60 / 360 / 961 s, three times; xsdb finished its work in ~2 s but did not exit until the `timeout` fired). Facts: `docs/paper/rehearsal_2026-10-13_notes.md` section 4. | **Cause reproduced on the PC without the board** (2026-10-24): `timeout N xsdb ...` with the terminal as stdin hangs until the timeout (exit 124 after 25.0 s, `rlwrap: Unexpected error: Input/output error`); `< /dev/null` or `timeout --foreground` exits 0 in 0.93 s. Fix applied in `demo.sh` (both, plus a clear failure message at the hard limit). **UNTESTED ON THE BOARD.** | Run `software/board/demo.sh` once first. If a step prints "xsdb did not exit within N s", the fix did not carry over to the real xsdb call: note which step and use `board_run.sh`/run_board.tcl directly. The scripts `run_testsets.sh`, `fresh_load_soak.sh`, `soak_test.sh`, `stale_test.sh` use the old pattern: start them as `script.sh < /dev/null`. |
| **Per-frame times and UART text were never stored.** The ARM prints `  frame N: total ... us = pad ... + ARM tile copy ... + DMA/compute wait ...` (T3) and `  frame N: total ... us = ... + ARM compute ...` (T7) on the UART (`sr_app/main.c`), `run_board.tcl` keeps only mean/min/max. | Host-side capture written (`uart_capture.py`, `board_run.sh`), PC-tested, **not board-tested**. No firmware change. | Save **every** UART log and per-frame time under `data/board/<date>/` (`board_run.sh` does it). Close picocom first (one reader per port). `/dev/ttyACM0` needs no sudo for the `dialout` group (the user is in it). |
| CYCLES window: the same bitstream gave 926,210-926,216 (Vitis run) and 926,217-926,241 (xsdb runs). | Cause not investigated; the window 926,210-926,241 covers both. | Record which tool ran the test next to every CYCLES number. |
| `run_board.tcl` stops waiting after 900 s (`TIMEOUT_S`); T7 (ARM only) has never run, its time per frame is unknown. | Open. | If T7 reports "no ready marker after 900 s", raise `TIMEOUT_S` and `XSDB_TIMEOUT` and run again. |
