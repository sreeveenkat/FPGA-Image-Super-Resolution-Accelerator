# Demo rehearsal of 2026-10-13: facts recorded

Source of the statements below: the "Demo Run Sheet" PDF written on 2026-10-13 (`docs/ZedBoard SR Accelerator — Demo Run Sheet.pdf`, untracked, local only,
section "What we found on 13 Oct" and Step 3) and the stored demo log `data/board/demo/demo_20261013_134005.log` (local, `data/` is git-ignored).
Statements are marked **[PDF]** when only the PDF has them and **[log]** when a stored file has them. Nothing here was re-run on 2026-10-24.

## 1. Vitis T1 run from the new workspace (UART text)  [PDF]
Workspace `~/Desktop/venkat/vitis_ws_demo_0602`, bitstream 0602, `SR_TEST=1`, first run from this workspace. UART lines as printed:

```
init ok: VERSION 0x53520602, TILE_SIZE 64
T1: CYCLES = 926210 (expected 926202 in simulation), tile time 9524 us (DMA + compute)
T1: first run: all 49152 bytes identical to the golden output
T1: 20 of 20 repeated runs identical to the first
T1: CYCLES over 21 runs: min 926210, max 926216, mean 926215 (simulation: 926202)
T1: tile time over 21 runs (DMA + compute + cache ops): min 9521 us, max 9524 us, mean 9522 us
T1 PASS
```

This is the only record of **CYCLES 926,210**. No UART log of it was stored on disk. Every other stored R0 run is 926,217 or higher
(`results/speed/m7_timing_20frames.md`, `m7_t3_20frames_stats.txt` stat9..11: 926,217-926,241).

## 2. T1 through `demo.sh` / xsdb on the same day  [log]
`data/board/demo/demo_20261013_134005.log`: `stat0=926217 stat1=926220 stat2=926219` (T1 CYCLES min / max / mean), `stat3=9521 stat4=9523 stat5=9521` (tile time, us),
`stat6=20` repeats, `version=0x53520602`. The full frame (T2) in the same log: `fnv1a32=0xcf947f22`, `stat0=1311436` us, compare_raw "board == expected".
So the same bitstream gave CYCLES 926,210-926,216 in the Vitis run (section 1) and 926,217-926,220 through xsdb (this section). Cause not investigated.

## 3. Bitstream file changed on 13 Oct  [PDF]
- The Vivado project's `impl_1/design_1_wrapper.bit` was rewritten at 11:15 (md5 `a44744b2...` instead of `d48ef9ea...`). Synthesis did not re-run (checkpoint of 12 Oct).
  Timing unchanged (WNS 0.503 ns, WHS 0.016 ns). `cmp` showed 5 bytes differing, at positions 94-106 (build date and time in the header).
- The tested file is saved read-only as `~/Desktop/venkat/TESTED_0602.bit`. md5 checked on 2026-10-24: `d48ef9ea1b1b4e513ad9b6b52e90c8a9`.

## 4. `demo.sh` took 961 s instead of about 25 s  [PDF], per-step times visible in the log  [log]
- Seen three times, always with step times of 60 s, 360 s and 961 s in total. The log header shows `OK FPGA is configured ( 60.0 s)` for step 1/5 and `( 360.0 s)` for step 3/5.
  These equal the timeouts used for the xsdb calls (`timeout 60 / 300 / 600`, PDF).
- Each xsdb call finished its work in about 2 s but did not exit, so the script waited for its timeout. Results were correct each time
  (BYTE-EXACT, 0xcf947f22, 1,311-1,313 ms per frame).
- Run directly at the prompt, the same xsdb exits in 1.2 s. A running `hw_server` did not fix it.
- The log shows `rlwrap: warning: your $TERM is 'xterm-256color' but rlwrap couldn't find it in the terminfo database ... Inappropriate ioctl for device`
  at the start of every xsdb call, so xsdb ran through its `rlwrap` wrapper.
- The PDF's suspected cause (not proven): inside a script, `timeout` puts xsdb in the terminal background and `rlwrap` stops when it touches the terminal. Proposed fix:
  run with `< /dev/null`. **Not tested on the board** (the PDF says the quick test had not been run).
- **Reproduced on the PC on 2026-10-24, no board involved** (pty from `script -qec`, `stty cols 120 rows 40`, trivial Tcl script `puts HELLO; exit 0` run by the Vitis 2024.1 `xsdb`):

  | Call | Result |
  |---|---|
  | `xsdb t.tcl` | exit 0, 0.94 s |
  | `timeout 25 xsdb t.tcl` (stdin is the terminal; the form `demo.sh` used) | `rlwrap: Unexpected error: Input/output error`, **exit 124 after 25.0 s** |
  | `timeout 25 xsdb t.tcl < /dev/null` | exit 0, 0.93 s |
  | `timeout --foreground 25 xsdb t.tcl` | exit 0, 0.92 s |

  So the hang is `timeout` (background process group) plus `rlwrap` touching the terminal; the work of the script is not involved. `demo.sh` now uses `timeout --foreground -k 5 N xsdb ... < /dev/null`
  and stops with a clear message if the hard timeout fires. This was checked only for the trivial script, for the no-board failure path (the JTAG step ends in 1.2 s with its normal "does not answer" message)
  and for the timeout message (a fake `sleep 30` in place of xsdb, stops at 2.0 s). **The fix is UNTESTED ON THE BOARD.**
  Other scripts that call `timeout N xsdb ...` with a terminal as stdin (`run_testsets.sh`, `fresh_load_soak.sh`, `soak_test.sh`, `stale_test.sh`) have the same pattern;
  they inherit stdin, so start them as `script.sh < /dev/null` (the runbook does).

## 5. Not done in the rehearsal  [PDF]
The "run your own image" recipe was not rehearsed (its `png2raw.py` arguments were a guess).
