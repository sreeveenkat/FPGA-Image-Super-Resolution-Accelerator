# OVERNIGHT LOG - single source of truth for the M6-finish / M7 plan (started 2026-10-12)

Plan: phases 1-8 given by the owner on 2026-10-12 (final 0602 bitstream, PC regression, board regression, M7 board quality row, M7 PC side,
reproducibility, docs, final report). Update after EVERY finished step; commit the log with that step.
Number labels: **sim** = simulation, **est** = Vivado estimate, **board** = measured on the ZedBoard.

## Current position
- 2026-10-12 afternoon: owner's recovery plan after the crash. STEP A (restore working 0601 system) running.
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
| A.5 commit pending files | DONE | 4 commits (board scripts, rebuild script, M7 table A, report) + this log | see git log |

## Open problems
- 2 single first-tile failures in the earlier `rst -system` run set (results/speed/m6_board.md 6.4): unexplained.
