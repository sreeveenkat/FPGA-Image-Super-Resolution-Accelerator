# Board session 2026-11-10: pipeline v2 (`pipe2`) and pipeline v2 packed (`pipe2p`)

ZedBoard (XC7Z020), real 125.000 MHz PL clock (each design's own XSA ps7_init, md5 d2a7789c..., FCLK0 read back before every run by `run_125.py` /
`run_nc.py`). Power NOT measured (no meter in this session). Logs in `logs/` (no raw images). Scripts: `software/board/run_125.py`, `run_nc.py --design`,
`board_run.sh`; expected values `docs/paper/board_expected.md` (all md5 matched before the runs).

## 0. Setup check: `pipe` (board-tested 2026-10-28)
T1 20/20, CYCLES 74,655-74,657; T2 byte-exact 0x45dd4e2d, 95.2 ms single frame, CYCLES 8,398,494 (2026-10-28: 8,398,495). Die 36.3 C before.

## 1. Results

| | `pipe` (2026-10-28) | **`pipe2`** (VERSION 0x53526301) | **`pipe2p`** (VERSION 0x53527301) |
|---|---|---|---|
| T1 golden tile, 20 repeats | 74,652-74,681 | **37,631-37,649** (window 37,620-37,679) | **37,632-37,635** (window 37,621-37,680) |
| T2 960x540, frame CYCLES | 8,398,495 | **4,203,137** (sim 4,203,124) | **4,203,138** (sim 4,203,125) |
| T2 output | 0x45dd4e2d byte-exact | 0x45dd4e2d byte-exact | 0x45dd4e2d byte-exact |
| 20-frame mean, cached buffers | 95.36 ms (10.49 fps) | **61.64 / 61.64 / 61.63 ms (16.2 fps)** | **61.64 / 61.63 / 61.64 ms (16.2 fps)** |
| 20-frame mean, non-cacheable buffers | 70.52 ms (14.18 fps) | **36.95 / 36.96 ms (27.1 fps)** | **36.96 / 37.04 ms (27.1 fps)** |
| split, non-cacheable: pad / DMA+compute | 3.32 / 67.19 ms | 3.32 / 33.63 ms | 3.32-3.41 / 33.63 ms |
| 119 test images (Set5/Set14/BSD100) | 119/119 | **119/119 byte-exact** | **119/119 byte-exact** |
| T5 error recovery | PASS | PASS x4 | PASS x4 |
| VERSION negative control | PASS | PASS (section 2) | PASS (section 2) |
| die temperature | 47.7-50.6 C | 46.0-47.7 C | 46.8 C |

Three cached means for each design: `run_125.py` T3 and the two cached (`fnv`) passes of `run_nc.py`; frame-to-frame spread within one 20-frame run <= 0.03 ms.

Predictions (made before the session, `board_checklist.md` 5e/5f): cached 61.8 ms (59.8-63.8), non-cacheable 37.0 ms (35.0-39.0), T1 and T2 cycle windows:
**all measured values inside**. The non-cacheable DMA+compute window (33.63 ms) equals the simulated cycles at 125 MHz (4,203,124 / 125 MHz = 33.62 ms).

## 2. Negative controls (VERSION)
* `pipe2` ELF on the `pipe2p` bitstream: `SR: VERSION 0x53527301, expected 0x53526301`, result 2 (refused).
* `pipe2p` ELF on the `pipe2` bitstream: `SR: VERSION 0x53526301, expected 0x53527301`, result 2 (refused).
(Run through `board_run.sh` / `run_board.tcl`, i.e. at the platform's 100 MHz clock; the VERSION check does not depend on the clock.)

## 3. What this shows
* Pipeline v2 doubles the per-pixel throughput on the board: frame CYCLES 8,398,495 -> 4,203,137 (1.998x).
* End to end at 125 MHz: 95.36 -> 61.64 ms cached (1.55x; the fixed 28 ms of padding + cache maintenance remains) and 70.52 -> 36.95 ms
  non-cacheable (1.91x). Versus R0 at 100 MHz (1,311.7 ms, 2026-10-27): **35.5x**; versus the ARM alone (13.437 s): **364x**.
* The packed design (two multiplies per DSP48) gives the SAME frame times and byte-exact outputs with 13,323 instead of 20,651 LUT and 190 instead
  of 220 DSP (Vivado, `results/utilization/m6_system_pipe2p.md` in branch pipe2p).
* Non-cacheable caveat (as for `pipe`): the ARM's own read of the output takes 620 ms instead of 64 ms; this configuration fits a consumer that reads
  the frame by DMA (display), not the ARM.

## 4. Not done
Power (no meter); the older designs were not re-run except the `pipe` setup check.
