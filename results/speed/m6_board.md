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
* **Early failures** (first five 960x540 attempts, error 7 / 6 on tile 0): investigated on 2026-10-11, see section 6. Only partly explained.
* Not yet done: running from the Vitis GUI after the timer/driver changes, UART output of T2/T3 (the UART was held by another terminal and I cannot read it).

## 5. Power-cycle test (2026-10-11, BOARD-MEASURED)
The owner switched the board off (SW8, 10 s) and on. Then, with `run_board.tcl` (old script version, `rst -system` included):
| Run | Result |
|---|---|
| T1 golden tile | PASS: 20/20 repeats identical, CYCLES min/max/mean 926,217 / 926,220 / 926,219, tile time 9,520 / 9,523 / 9,521 us |
| T2 960x540 | **byte-exact** vs the integer model, FNV-1a 0xcf947f22 (same as before the power cycle), 135 tiles, 1,311.6 ms (pad 5.9, ARM copy 26.4, DMA+compute 1,279.3 ms), CYCLES 926,217-926,241 |

After the driver changes (section 6), T3 was run again: 5 frames, mean / min / max 1,312.9 / 1,311.9 / 1,314.0 ms, CYCLES per tile 926,217 / 926,220 / 926,241, output byte-exact. Same as before within 1 ms.

## 6. Investigation of the early failures (2026-10-11)
Owner's hypothesis: stale DMA / core state from an interrupted run. What was done, what was found. All on the board, all runs started with xsdb (no Vitis GUI).

### 6.1 Tools added
* `software/board/interrupt_test.tcl`: start a program, stop the CPU after N ms, print the DMA and core registers.
* Stale-state programs (SR_TEST): 9 = MM2S started, core not started (MM2S blocked half-way); 7 = MM2S with 4,000 of 14,700 bytes then START (core stuck in its LOAD
  phase); 6 = S2MM armed for 20,000 of 49,152 bytes (core stuck in its OUTPUT phase); 8 = a tile started and not waited for. Their state, read after the CPU was stopped,
  confirms the intended situation (e.g. SR_TEST=7: STATUS busy+error, ERROR_CODE 1; SR_TEST=6: STATUS busy, S2MM_SR 0x5011 = halted + internal error; SR_TEST=9: MM2S_SR 0 = running).
* `software/board/stale_test.sh [nofpga]`: each stale situation, then a FRESH 128x128 T2 run that must be byte-exact (plus a check that the program image in DDR equals the ELF).
* SR_TEST=5 (T5): deliberate errors inside one program: input too short (TLAST early), input too long (no TLAST), S2MM buffer too short (core stuck -> timeout), both;
  after each, the driver's reset must work and the next normal tile must be byte-exact.
* `software/board/soak_test.sh N`: N rounds of T1 / T2 128x128 / T2 960x540 with every check.
* Stopping the CPU (the owner's cases a and b) does NOT stop the PL: the tile in flight finishes by itself (registers read after the stop always showed DONE, CYCLES 926,220).
  A real "stopped during the output phase" state therefore needs the SR_TEST=6 program; case c = SR_TEST=9.

### 6.2 Finding 1 (proven, fixed): program reload over a running program corrupts the new program
* Loading an ELF with `rst -processor` + `dow` (no system reset) over a previous program: dirty data-cache lines of the OLD program were written back over the NEW one.
  Proof: after T2 -> SR_TEST=9, the new program died in its data-abort handler (DFAR 0x16100000, DFSR 0x805 = translation fault); its MMU table read back physically
  (DAP, no cache) had 519 zero words starting exactly at the cache line of the OLD program's `__bss_start` (0x10c0a0). Reproduced 3 of 3 (T2 -> 9 crashed, 9 -> T2 failed
  with error 7 each time).
* Fix in `run_board.tcl` / `interrupt_test.tcl`: L2 cache off before loading and the ELF loaded twice. A/B with the soak test (T1 / T2 / T2 alternating, so the ELF changes
  every run): loaded once: 6 OK, 3 FAILED (every T1 after a T2 hung); loaded twice: 15 of 15 OK, and 30 more OK later; every run's read-only sections checked against the ELF
  (`verify_load.py`): always intact. I do not know which tool step does the write-back (xsdb's cache maintenance after `dow` is the likely one; not proven).
* This alone can explain failures after switching programs (T1 ELF -> T2 ELF was exactly the situation of the first failures), but it does not explain finding 3.

### 6.3 Finding 2 (fixed): reset order in the driver
* `sr_init` and the recovery after every tile error/timeout now do: core soft reset -> AXI DMA reset (wait for ResetIsDone, ~1 s timeout) -> core soft reset -> check
  STATUS idle and ERROR_CODE 0. Before, init did no explicit DMA reset (only the one inside `XAxiDma_CfgInitialize`) and recovery did core -> DMA.
* With DMA -> core (my first version), T5 case "S2MM buffer too short" was followed by a WRONG next tile (seen once with per-case numbers). With core -> DMA -> core:
  T5 passed 5 of 6 runs (each: 4 bad tiles rejected with error 7 / 7 / 6 / 7, every reset OK, every following tile byte-exact); the 6th failed already on its first NORMAL
  tile, inside a finding-3 episode.
* The core reset first stops the core from pushing output words into the S2MM channel while it is being reset; that is my explanation, not proven.

### 6.4 Owner's cases a, b, c WITHOUT a system reset
| Mode | Runs | Result |
|---|---|---|
| bitstream NOT reloaded (stale PL state really kept), 7 situations (T2 stopped at 300/517/733 ms, SR_TEST 9, 7, 6, 8) | 2 x 7 | **14 of 14 fresh runs byte-exact** |
| bitstream reloaded by the script | 8 x 7 = 56 | 52 of 56 byte-exact; the 4 failures have the finding-3 signature (2 of them in a run where every load was preceded by `rst -system`) |
| T2 stopped at 517 / 733 ms, then fresh run, bitstream reloaded | 8 + 8 | 16 of 16 OK |

So the driver does recover from a DMA blocked half-way, a core stuck in LOAD, a core stuck in OUTPUT and a tile left running, when the PL keeps that state.
The DMA reset finished even with the MM2S channel blocked half-way (SR_TEST=9 then fresh run with the bitstream kept).

### 6.5 Finding 3 (NOT explained, open): first-tile stream errors, sometimes a lasting "bad state"
* Signature (the same as the very first failures): first tile of a program, STATUS busy+error, ERROR_CODE 2 (input word 3,675 without TLAST = the core counted one word more
  than the DMA sent before TLAST) or 1 (TLAST early), CYCLES about 14,850 (end of the load phase), MM2S idle; or (rarer) a timeout with the core still in LOAD and MM2S not
  finished. When a whole tile is processed in that state its output differs in 48,385 of 49,152 bytes (twice the same number: looks like a 1-word shift).
* Sometimes it is a single failure (the next run is fine). Sometimes the board stays in a state where EVERY new program fails, also after reloading the bitstream, also with the data caches disabled (debug build `-DSR_NOCACHE`), also with the
  bitstream not reloaded. It survived 9 consecutive runs. A system reset (`rst -system` / `dap_reset.tcl`) cleared it every time (4 times).
* Seen in about 4 hours: 4 single failures in 56 stale-test fresh runs (2 of them in the run set where every load was preceded by `rst -system`), and 4 lasting episodes
  (the first failures of the day, after normal runs; on the first program after a `dap_reset.tcl` system reset; right after a T5 error-injection run;
  after a T5 single-case run followed by one good T1). I could not make it start on purpose (4 rounds "T5 single case -> 3 x T1" started it once, in the last round, after a T5 case that had not caused it before).
* So it lives in the PS (or in something a PL reload does not reset) and is cleared by a PS reset. Checked and ruled out: CPU data caches (still fails with the data caches off;
  the program-image check was added later and has not yet run in a failing run), the clock structure (one clock, FCLK0 100 MHz, standard proc_sys_reset; no CDC in `report_cdc`), timing (the routed design meets
  setup and hold; the worst hold paths, +0.023 ns, are inside the AXI DMA and the AXI interconnect, normal for these IPs). Reading the HP0 AFI registers hung the debug port.
* Last change, NOT yet proven: `run_board.tcl` now holds the PL in reset and switches the PS-PL level shifters off before reprogramming the PL (Xilinx's procedure for PL
  reconfiguration while the PS runs; `ps7_post_config` switches them on again). Hypothesis: without it, the PL's pins toggling during configuration can create a spurious
  transaction on a PS AXI port (GP0 or HP0) that stays half-open until a PS reset. After this change: 15 of 15 soak runs + T5 + T3 OK, no bad state. That is too few runs to
  call it fixed.
* What would settle it: (1) a long soak (a few hundred program starts) with and without the isolation step; (2) debug counters in `sr_accel_top` (input words since START,
  words accepted before START, START count) so a failure shows exactly which side added the word; (3) an ILA on s_axis. (2) and (3) need an RTL change and a new bitstream.

### 6.6 State at the end of the day
With the final scripts (PL isolation + double load + final driver), after a system reset: T5 PASS, T3 byte-exact (1.313 s per frame), soak 15 of 15. Finding 3 is
open; the M6 checklist item "repeated runs give identical output" is therefore not closed.
