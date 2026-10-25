# Board checklist: T1/T2 re-run, T7 ARM baseline, R2q, power, and later R3q

Prepared 2026-10-19, updated for the per-design VERSION values. **Nothing below has been run on the board.** Everything on the PC side (simulation, builds, byte-exact C model) is done and listed in
`results/utilization/m6_system_R2q.md` (branch `r2q`) and `results/utilization/m6_system_R3q.md` (branch `r3q`).
Board on the PROG/JTAG USB (J17), boot jumpers on JTAG. Run every `xsdb` command from the project root of the tree named in the heading.

Companion files (2026-10-24): `docs/paper/board_session_runbook.md` (the order of the day and every command), `docs/paper/board_expected.md` (what the board must print for each design, generated from each tree's integer model), `software/board/board_run.sh` (run + UART log capture, PC-tested only).

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

## 4. Power measurement (current design and R2q)

**What to measure:** the ZedBoard's 12 V input power (whole board: Zynq, DDR, regulators, USB-UART, LEDs). The board overhead is the same in every state, so the
**differences** between states are the useful numbers. The synthesis power estimates are 1.913 W (0602) and 1.910 W (R2q, current VERSION 0x53522201 build; `m6_system_R2q.md:45` in branch `r2q`; the 1.912 W on its line 6 is the superseded first build), both "low confidence"; the measurement
replaces them.

**How (owner decision 2026-10-25): the 12 V input current-sense resistor, read with a multimeter.**
* Measure the millivolts across the sense resistor (header J21 on the ZedBoard, per the owner; the board's own markings and schematic decide), then I = V / R and P = I x V_in.
* **Also measure the actual input voltage** (multimeter on the 12 V rail / adapter output) in every state: do not assume 12.00 V.
* **R and the header are NOT verified here.** The Hardware User Guide was not readable from this machine (the PDF URLs tried returned errors on 2026-10-25), so there is no page number to cite. Secondary sources only, not authoritative: element14 community posts say the guide describes a 10 mOhm, 1 W resistor in series with the 12 V input and J21 across it (https://community.element14.com/products/devtools/avnetboardscommunity/avnetboard-forums/f/zedboard-hardware-design/34032/zedboard-power-consumption); a worked example elsewhere uses 0.01 Ohm (https://www.openwall.com/lists/john-dev/2014/07/20/3). **Before the first reading: open the ZedBoard Hardware User's Guide, find the section on the 12 V input / J21, and write the resistor value, its tolerance, the guide version and the page number into `$D/power_readings.txt`** (and replace this paragraph with the citation). If the guide and the board disagree, the board wins and the difference is reported.
* Expected size (from the secondary value only, a plan not a measurement): at 10 mOhm and about 0.5 A the drop is about 5 mV, so the meter needs mV resolution (0.01 mV is better). Record the meter model, range, stated accuracy and resolution.
* Probe on the J21 pins only with the meter in voltage mode; an extra load across the header skews the reading (the header contact resistance is far above the sense resistor, as the second source notes), so do not use it to power anything.

**Board-level power, not comparable to Vivado's on-chip estimate.** This is the whole ZedBoard's 12 V input (Zynq, DDR, regulators, USB-UART, LEDs, conversion losses). The Vivado numbers (1.913 W, 1.910 W) are the on-chip estimate of the Zynq only. Never put the two in one row without saying so, and never compare a board-level absolute with the estimate; compare the **delta** only.

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

**Reported deltas (owner decision):** accelerator delta = P(accelerator running T3) - P(PL configured, idle) (P2 - P1); also report P1 - P0 (cost of a configured but idle PL). All three states are measured with the same meter, range and input voltage reading.

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
| T1 | `result=0`, **`version=0x53523201`**, stat6 = 20 (as for R0; the golden tile is the R3q one and includes the anchor path), CYCLES 926,210-926,241 (the anchor adds **no** cycles: simulated 926,201 per tile as before) |
| T2 | `BYTE-EXACT: yes`, fnv1a32 **0x45dd4e2d** |
| negative controls | the R3q output compared with the R2q expected file and with the R0 expected file: `BYTE-EXACT: no` for both |
| frame time | 20-frame mean within ±2 ms of 1,311.9 ms, max − min ≤ 3 ms, CYCLES per tile 926,210-926,241 (see section 2 T1 row and `results/speed/m7_timing_20frames.md`); per-frame times saved to a file |
| T7 | `BYTE-EXACT: yes`, fnv 0x45dd4e2d (anchor compiled into `sr_swmodel.c`) |
| power | repeat P1/P2 for R3q (P1c, P2c); expected within meter accuracy of R2q (+33 to +45 LUT, +66 FF, 0 DSP, 0 BRAM in the whole system: simulation/synthesis numbers, `m6_system_R3q.md` in branch `r3q`, not board-measured) |

Seam and halo alignment are covered in simulation (20-tile and 4-tile seam tests, 26 anchor mutants); the board T2 on a real 960x540 frame (135 tiles) is the first
real-hardware check of the anchor's halo-aligned read.

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
