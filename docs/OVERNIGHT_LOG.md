# OVERNIGHT LOG - single source of truth for the M6-finish / M7 plan (started 2026-10-12)

Plan: phases 1-8 given by the owner on 2026-10-12 (final 0602 bitstream, PC regression, board regression, M7 board quality row, M7 PC side,
reproducibility, docs, final report). Update after EVERY finished step; commit the log with that step.
Number labels: **sim** = simulation, **est** = Vivado estimate, **board** = measured on the ZedBoard.

## Current position
- 2026-10-12 afternoon: owner's recovery plan after the crash. STEP A DONE (0601 restored + board-verified). STEP B DONE (0602 built in m6_sr_0602, checks pass). STEP C interrupted by a power loss at 15:20, redone from C1 15:21-15:29: ALL PASS on 0602. Demo prep D done, rehearsal PASS (24.8 s). Demo bitstream: 0602 (fallback 0601). Phases 4-8 paused.
- Then STEP B (rebuild 0602 in a COPY m6_sr_0602, -jobs 2), STEP C (board regression on 0602). Phases 4-8 paused until the owner asks.
- Demo (review) 2026-10-13 15:00: a working demo comes first.

## Starting state (Step 1 orientation, 2026-10-12)
- git clean at `bc2c566`. No earlier overnight run (this file did not exist).
- `~/Desktop/venkat/vitis/m6_sr`: bitstream `m6_sr.runs/impl_1/design_1_wrapper.bit` 2026-10-11 18:21, XSA `design_1_wrapper.xsa` 18:25; no backup.
  Routed WNS +0.239 / WHS +0.023 ns, 5,146 LUT, 7,605 FF, 72 BRAM, 68 DSP (est). The sr_accel_top IP synth (18:19) predates the 0602 commit (22:48)
  -> the bitstream is VERSION 0x53520601. Repo RTL: 0x53520602.
- Board: answers on JTAG (APU, 2 x A9, xc7z020); PL **not configured** (fresh power-up), level shifters off -> VERSION not readable without programming.
- Vivado GUI: not running. Vitis IDE: open (its xsdb process is alive; it is the owner's, not touched).
- Stale docs noticed: HANDOFF.md header + sections 2/11 still say "M6 prep NEXT"; run_board.tcl takes the bitstream from the Vitis sr_app `_ide/bitstream`.

## Crash 2026-10-12 ~12:02 (PC froze; owner restarted it and power-cycled the board)
- Step 1.1 (pre-build regression) was never logged as finished; step 1.2 was started but not logged: backup `m6_sr_backup_20261012_112709` (11:27, complete,
  has the 0601 bitstream), then a batch rebuild at 11:59 with `rebuild_m6_bitstream.tcl` default **-jobs 8**: 8 out-of-context IP synth runs in parallel.
  All of them stop at 12:01:54 without an end marker (only xbar_0 finished). The run reset had emptied `impl_1/` and `synth_1/` -> m6_sr had NO bitstream.
- Likely cause (inferred from timestamps, not proven): 8 parallel Vivado jobs on a 15 GB / 16-thread PC -> memory exhaustion.
- Not logged before the crash but present: `results/quality/table_a_x2.*` (11:28), `software/ai/evaluation/run_all.py` (11:38), `docs/REPORT/sr_report.pdf` (13:15),
  `docs/REPORT.zip` (13:24); all checked complete after the crash. No .git/index.lock, git fsck clean, no .lck files, no leftover processes.
- Board after the power cycle: JTAG OK (APU, 2 x A9, xc7z020), PL not configured.
- New resource rules (owner): at most ONE heavy job at a time, Vivado -jobs 2 (STEP B), no soak tests / simulations / board runs while Vivado builds.

## Steps
| Step | Status | Evidence | Commit |
|---|---|---|---|
| A.1-A.3 restore 0601 project | DONE | `vitis/m6_sr` -> `m6_sr_broken_crash_20261012` (kept); `cp -a m6_sr_backup_20261012_112709 m6_sr` (backup kept). `impl_1/design_1_wrapper.bit` md5 8b5fe08f... == Vitis `sr_app/_ide/bitstream` copy; XSA 2026-10-11 18:25 | - |
| A.4 board check 0601 | DONE | **board**: VERSION 0x53520601 (TILE_SIZE 64). T1 golden tile + 20 repeats PASS, CYCLES 926,217-926,225, 9,521-9,523 us. T2 DIV2K img0193 960x540 byte-exact, fnv 0xcf947f22, 135 tiles, 1,313.1 ms. Default run_board.tcl (isolation on, ELF loaded twice). Found + fixed: run_board.tcl VERSION read returned 0 (xsdb blocks PL addresses: "not added to the memory map") -> read with force-mem-accesses; re-verified in the T2 run (version=0x53520601) | see A.5 |
| B.1 rebuild script default -jobs 2 | DONE | commit fa587a5 | fa587a5 |
| B.2/B.3 rebuild 0602 in copy `vitis/m6_sr_0602` | DONE, Vivado session 15:13:30-15:19:04 (5 min 34 s), exit 0 | before start: `free -h` total 15 Gi, used 5.0 Gi, available 10 Gi, swap 4 Gi free; `nproc` 16. `cp -a m6_sr m6_sr_0602`; `vivado -mode batch -source rebuild_m6_bitstream.tcl -tclargs m6_sr_0602/m6_sr.xpr 2` (nice 10). Nothing else running. Memory watchdog (20 s samples, kill below 1 GB): lowest available 6.5 GB, never triggered | - |
| B.4 checks 0602 build | PASS | **est** (Vivado, routed): WNS +0.503 ns, WHS +0.016 ns, 23,943 endpoints, 0 failing; 5,296 LUT, 7,831 FF, 72 BRAM, 68 DSP; 12/12 .mem "read successfully" (bias/mult/wrom L1-4); 0 CRITICAL WARNING, 0 ERROR in all run logs; impl_1 "write_bitstream Complete". Bitstream `m6_sr_0602/m6_sr.runs/impl_1/design_1_wrapper.bit` 15:18, XSA `m6_sr_0602/design_1_wrapper.xsa` 15:19; reports `m6_sr_0602/reports_final/`. m6_sr (0601) untouched | - |
| C (board regression 0602) | INTERRUPTED 15:20 | runner `data/board/stepC/run_stepC.sh` (SR_BIT = m6_sr_0602 bitstream). **board** C1 PASS: VERSION 0x53520602, T1 20/20, CYCLES 926,217-926,231, 9,520-9,523 us. Then power was lost (owner) during C2: C2..C4 lines show 'no targets found' = board unreachable, NOT test failures. Runner + xsdb stopped by hand. STEP C must be redone from C1 after power is back | - |
| C (board regression 0602), rerun after power loss | **PASS** 15:21-15:29 | **board**, SR_BIT = m6_sr_0602 bitstream, default safe loading (isolation on, ELF x2); log `data/board/stepC/stepC.log` (interrupted run kept in `stepC/interrupted_1520/`). C1 VERSION 0x53520602, T1 20/20, CYCLES 926,217-926,220. C2 T2 128x128 byte-exact (fnv 0x91a4506d). C3 T2 960x540 x3 byte-exact, fnv 0xcf947f22, 1,311.4-1,311.5 ms. C4 T5 x10: all 10 PASS (bad rc 7/7/6/7, resets 0, next tile exact). C5 T6: 1000/1000 both driver orders, 0 dumps. C6 fresh-load soak 50/50, VERSION 0602 every time. C7 T3 3x5 frames: mean 1,311.9 / 1,311.8 / 1,311.7 ms (min 1,311.4, max 1,313.3), pad 5.9, ARM copy 26.4-26.8, DMA+compute 1,279.1-1,279.4 ms, CYCLES 926,217-926,241, byte-exact | - |
| D demo prep (owner's list 1-7) | DONE | 1 `results/utilization/m6_system_0602.md` (clean). 2 run_board.tcl default = 0602, 0601 via SR_BIT. 3 `software/board/demo.sh` (+ jtag_check.tcl, side_by_side.py). 4 **board** Set14 zebra (test image) on 0602 byte-exact (fnv 0x29cfeaa9, 20 tiles, 193 ms) -> `docs/demo/compare_zebra.png`, PSNR-Y bicubic 30.65 / FPGA 32.57 dB (= model_int8 CSV). 5 `hardware/verification/demo_sim.sh`: quick 36/36 (180 s) + HC=6 tile bit-exact with VCD (10,962 cycles: LOAD 433, L1 2,726, L2 1,043, L3 1,050, L4 5,206, OUT 504); GTKWave NOT installed (layout signals checked against the VCD). 6 `docs/DEMO.md`. 7 REHEARSAL after owner power-cycle (SW8): demo.sh PASS in 24.8 s (VERSION 0602, T1 20/20 CYCLES 926,219, frame byte-exact 0xcf947f22 1,311.4 ms, viewer opened) | see git log |
| E M7 table A FPGA row (owner request) | **PASS** 18:23-18:34 | **board**, 0602, `software/board/run_testsets.sh` (default safe loading, one xsdb run per image): **119/119 test images (Set5 5, Set14 14, BSD100 100) byte-exact** vs the integer model, 0 failed, 0 retries; log `results/quality/m7_board_testsets_run.log`. Then `run_all.py`: nearest/bicubic/FP32/INT8 equal published CSVs (max diff 0); FPGA row == INT8 row (Set5 35.02 / Set14 31.40 / BSD100 30.53 dB PSNR-Y, wins 5/5, 14/14, 100/100) -> `results/quality/table_a_x2.{md,csv}` | see git log |
| F M7 power estimate (owner request) | DONE | **est** Vivado `report_power` on `m6_sr_0602/.../design_1_wrapper_routed.dcp` (opened read-only, nothing else running), `power_estimate_m6.tcl`, toggle 6.25/12.5/25 %: 1.911/1.913/1.915 W, confidence Low; PS7 1.563, sr_accel_top 0.176, DMA+interconnect 0.016-0.018, static 0.155 W. Energy/frame ~2.5 J (chip), ~0.23 J (accelerator) with the board 1.312 s. `results/utilization/m7_power.md` | see git log |
| A.5 commit pending files | DONE | 4 commits (board scripts, rebuild script, M7 table A, report) + this log | see git log |

## Open problems
- 2 single first-tile failures in the earlier `rst -system` run set (results/speed/m6_board.md 6.4): unexplained.
