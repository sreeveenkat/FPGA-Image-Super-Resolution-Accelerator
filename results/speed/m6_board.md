# M6 on the board: first results (BOARD-MEASURED, 2026-10-11)

Hardware: ZedBoard, bitstream `design_1_wrapper.bit` of the Vivado project `m6_sr` (PS7 + AXI DMA + `sr_accel_top`, 100 MHz PL clock, WNS +0.239 ns, see `results/utilization/m6_system.md`).
Program: `software/board/sr_app` (bare metal, -O2), SR_TEST=1/2/3. PS clocks read from the board registers: CPU 650 MHz, A9 global timer 325 MHz, FCLK0 100 MHz.
All times are measured by the program with the A9 global timer. Runs below were started from the PC with `software/board/run_board.tcl` (xsdb), numbers read back from DDR
(`stat<i>` words, see `software/board/README.md`). Test image: DIV2K img0193 960x540 (a TRAINING image: bit-exactness and speed only, no quality statement), and the Set14
baboon 128x128 crop.

## 1. T1: one golden tile (real0)
| | Value | Source |
|---|---|---|
| First board run (Vitis Run, UART text pasted by the owner) | all 49,152 bytes identical to the golden output; 20/20 repeats identical; CYCLES = 926,217; the old "tile time 0 us" was the timer bug | owner |
| Rerun with the fixed timer (xsdb, 21 runs) | CYCLES min / max / mean = 926,217 / 926,220 / 926,219; tile time min / max / mean = 9,520 / 9,523 / 9,521 us; 20/20 repeats identical | measured |

Simulation says 926,202 CYCLES; the board shows +15 to +18 cycles (0.002 %). Not investigated (a few cycles of DMA / AXI handshake latency are the obvious suspect, not proven).
Tile time 9,521 us = 9,262 us of core cycles at 100 MHz + about 259 us for cache maintenance, DMA setup and polling (not broken down further).

## 2. T2: whole image, byte-exact comparison
Expected output = `software/ai/quantization/integer_reference.upscale` on the whole image (`software/host_tools/expected_output.py`); compared with `compare_raw.py`.
| Image | Tiles | Result | FNV-1a 32 (board = expected) | Total time | pad / ARM copy / DMA+compute |
|---|---|---|---|---|---|
| Set14 baboon crop 128x128 -> 256x256 | 4 | **byte-exact** (196,608 bytes) | 0x91a4506d | 38.7 ms | 0.19 / 0.65 / 37.9 ms |
| DIV2K img0193 960x540 -> 1920x1080, run 1 | 135 | **byte-exact** (6,220,800 bytes) | 0xcf947f22 | 1,311.4 ms | 5.9 / 26.4 / 1,279.1 ms |
| same, run 2 | 135 | byte-exact | 0xcf947f22 | 1,312.7 ms | 5.9 / 26.6 / 1,280.3 ms |
| same, run 3 | 135 | byte-exact | 0xcf947f22 | 1,313.0 ms | 5.9 / 26.4 / 1,280.7 ms |

The three 1920x1080 outputs are identical to each other (`cmp`) and to the integer model. CYCLES per tile over the 135 tiles: min 926,217, max 926,234 (run 1), mean 926,220.
Files (git-ignored): `data/board/*_board_*.raw/.png`, stats `data/board/*stats*.txt`.

## 3. T3: timing of the whole 960x540 frame (3 invocations x 5 frames, 15 frames)
Per frame = pad the image (ARM) + for each of 135 tiles: cut (ARM copy) -> DMA -> compute -> place (ARM copy).
| Invocation | Frame mean / min / max (ms) | pad (ms) | ARM tile copy (ms) | DMA+compute wait mean / min / max (ms) | CYCLES per tile min / mean / max |
|---|---|---|---|---|---|
| 1 | 1,312.4 / 1,311.5 / 1,312.9 | 5.89 | 26.42 | 1,280.0 / 1,279.1 / 1,280.6 | 926,217 / 926,220 / 926,236 |
| 2 | 1,312.2 / 1,311.5 / 1,313.0 | 5.89 | 26.47 | 1,279.8 / 1,279.1 / 1,280.6 | 926,217 / 926,220 / 926,236 |
| 3 | 1,312.4 / 1,311.5 / 1,313.2 | 5.89 | 26.79 | 1,279.7 / 1,279.1 / 1,280.6 | 926,217 / 926,220 / 926,241 |

All 15 frames gave the same output checksum, and the output read back after each invocation is byte-exact vs the integer model.

**Frame time about 1.312 s = 0.762 frames per second at 1920x1080 output (measured, 960x540 input).** Spread between frames is under 2 ms.

| | Time | Share |
|---|---|---|
| Prediction (simulation): 135 x 926,202 cycles / 100 MHz | 1,250.4 ms | |
| Measured: DMA + compute wait | 1,279.9 ms (9.48 ms per tile) | 97.5 % |
| Measured: ARM tile copy (cut + place) | 26.5 ms | 2.0 % |
| Measured: padding | 5.9 ms | 0.4 % |
| Measured: frame total | 1,312.3 ms | |

The measurement is +4.9 % above the simulation prediction: +29.5 ms in the DMA + compute wait (about 0.22 ms per tile, from cache flush/invalidate, DMA arming, polling; the extra
CYCLES are negligible), plus 32.4 ms of ARM work (copy + pad) that the prediction did not include. Load, compute and output inside the core are still not overlapped (known, M5).
The ARM copies and the DMA are also not overlapped (the ARM waits). Both are possible speed-ups; nothing was tried.

## 4. How far to trust these numbers
* The timer: `XTime_GetTime()` of the SDT BSP gave 0 (cause not isolated); the driver now reads the global timer itself. The tick rate comes from the CPU clock read from the
  board's PLL registers (ARM_PLL_CTRL / ARM_CLK_CTRL: 33.33 MHz x 39 / 2 = 650 MHz, timer = CPU/2). Cross-checks: tile time 9,521 us vs 9,262 us of CYCLES at 100 MHz (FCLK0 read
  back as 1000/5/2 = 100 MHz), and the xsdb wall clock for 5 frames (7-8 s, integer seconds, includes the image upload and two FNV passes per frame) is consistent with 5 x 1.31 s.
  There is no oscilloscope-grade check.
* One image, one board, one bitstream build. The DIV2K image is a training image: speed and bit-exactness do not depend on that, quality numbers would.
* Time per tile does not depend on the data (the core is data-independent), so other images should give the same frame time; not run.
* **Unexplained failures.** Right after the first successful xsdb runs (T1, 128x128 T2) the first five attempts at 960x540 failed: error code 7 (core reported ERROR_CODE 1 = TLAST
  at the wrong input word, STATUS 0x5, MM2S idle, CYCLES 14,806 or 14,824) or 6 (timeout, once), at the first tile, and the debug port then stayed stuck ("AHB AP transaction error")
  until `rst -system`. After that reset the same program, same image and same script gave 14 correct runs in a row (3 T2, 3 T3 invocations, 5 more T2 runs without `rst -system`
  in the script, repeated 128/960 alternation). I do not know what caused the early failures. It was a real error in the board/PL state, not a data error (the stream length is
  data independent). If it comes back, the register dump is in `stat24..29`. The recovery path of the driver (soft reset + DMA reset after an error) was exercised only by these accidents and its
  outcome was not checked.
* Not yet done: power-cycle test, running from the Vitis GUI after the timer change, UART output of T2/T3 (the UART was held by another terminal and I cannot read it).
