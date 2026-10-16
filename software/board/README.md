# software/board - ARM program, register header and board scripts (M6)

**Status: runs on the board since 2026-10-11 (T1, T2 at 128x128 and 960x540, T3, T5 pass, byte-exact vs the integer model, also after a power cycle; one open intermittent problem): `results/speed/m6_board.md`.**
Before that it was tested on the PC only. PC-side checks: the register header against the Verilog
(`test_regs.py`), the tiling code against the integer model (`test_tiling.py`, bit-exact incl. 960x540), the host tools (`../host_tools/test_host_tools.py`),
and that the program compiles and links with the Vitis ARM compiler against the BSP of the M0 platform (`check_arm_build.sh`). Still NOT verified on the board: runs from the Vitis GUI
after the timer/driver changes.

| File | What |
|---|---|
| `sr_regs.h` | register offsets, bits, error codes, tile sizes of `sr_accel_top` (pure constants). Document: `docs/REGISTER_MAP.md` |
| `sr_app/sr_tiling.c/.h` | pad / cut / place / checksum / tile loop - portable C, no Xilinx headers |
| `sr_app/sr_driver.c/.h` | DMA + register driver: `sr_init`, `sr_soft_reset`, `sr_run_tile`, timeouts, `sr_dump` |
| `sr_app/sr_memmap.h` | DDR memory map (static asserts) |
| `sr_app/main.c` | T1 golden tile, T2 full image, T3 timing (UART menu or `-DSR_TEST=n`) |
| `sr_app/golden_tile.h` | GENERATED (git-ignored): `python software/host_tools/golden_tile_h.py` |
| `pc_test/tiling_tool.c`, `test_tiling.py` | PC proof of the tiling code |
| `test_regs.py` | header == Verilog == docs |
| `check_arm_build.sh` | compile + link of all four `SR_TEST` variants with the Vitis ARM gcc against the zed_platform BSP |
| `build_elf.sh` | builds `build/sr_app_t<N>.elf` (git-ignored) against the m6_platform BSP, without touching the Vitis project |
| `run_board.tcl` | xsdb script: program the PL, init the PS, load the ELF (twice, L2 off), push input, run, wait for the marker, read output + numbers. Before reprogramming the PL it holds the PL in reset and switches the PS-PL level shifters off. Env: `SR_SYSRST=1` system reset first, `SR_NO_ISOLATE=1` skip the PL isolation (test only), `SR_NOFPGA=1` keep the loaded bitstream, `SR_DOW2=0` load once (test only), `SR_VERIFY_DUMP`/`SR_VERIFY_BYTES` dump the program image after the run |
| `interrupt_test.tcl` | xsdb: start a program, stop the CPU after N ms, print DMA/core registers (stale-state tests) |
| `stale_test.sh` | board test: leave the DMA/core half-way (stopped T2, SR_TEST=6..9 programs), then a fresh 128x128 run must be byte-exact; `nofpga` = without reloading the bitstream |
| `../../hardware/verification/tb/tb_sr_accel_top.v +OFFSWEEP` | (simulation) START-vs-first-beat offset sweep, part of `run_tests.sh full` |
| `soak_test.sh` | board test: N rounds of T1 / T2 128x128 / T2 960x540, every run checked (result, byte-exact, program image intact) |
| `verify_load.py` | compares the program image read back from DDR (physically) with the ELF |
| `dap_reset.tcl` | xsdb: system reset when the debug port is stuck ("AHB AP transaction error") |

## Memory map (DDR 0x0000_0000 - 0x1FFF_FFFF, 512 MB)
| Region | Address | Size reserved | Used |
|---|---|---|---|
| BSP reserved | 0x0000_0000 - 0x000F_FFFF | 1 MB | - |
| program (code, data, bss, heap, stack) | 0x0010_0000 - | linked image ends at 0x0012_0870 (SR_TEST=0/1) / 0x0011_0870 (2/3) | ~130 KB |
| input image (SRIM) | 0x1000_0000 | 32 MB | 1.5 MB (960x540) |
| output image (SRIM) | 0x1200_0000 | 16 MB | 6.2 MB (1920x1080) |
| status block (ready marker + stats) | 0x1300_0000 | 256 B | 6 words + 32 stat words (below) |
| padded input image | 0x1400_0000 | 32 MB | 1.7 MB |
| tile input buffer | 0x1600_0000 | 64 KB | 14,700 B |
| tile output buffer | 0x1610_0000 | 64 KB | 49,152 B |

Regions are 64-byte aligned and checked by `_Static_assert` (`sr_memmap.h`); `main()` also checks that the program image (symbol `_stack`, the top of the stack in
this linker script) ends below 0x1000_0000. Image limits: 16 + 12*w*h <= 16 MB (w*h <= 1,398,100).

## Building in Vitis 2024.1 (SDT flow) - when the block design exists
1. Vivado: block design with `sr_accel_top` (module reference, `s_axi` on GP0, `s_axis`/`m_axis` to the AXI DMA, DMA memory ports to HP0) -> bitstream -> export `.xsa`.
2. Vitis: platform from the new `.xsa` (Switch XSA in `vitis-comp.json`, build), new application `sr_app` (empty), copy `sr_app/*.c *.h`, `golden_tile.h` and `sr_regs.h` into its `src`.
3. Base addresses (block design `m6_sr`, Address Editor): `SR_BASE` = **0x40000000** (`sr_accel_top_0/s_axi`, 4K) and `SR_DMA_BASE` = 0x40400000 (`axi_dma_0`) are the defaults in `sr_driver.h`.
   Override with `-DSR_BASE=0x...` if the design changes (a WRONG value can hang the bus). Full address map: `docs/REGISTER_MAP.md`.
4. Check the app's `_ide/launch.json`: the init file must be `ps7_init.tcl` (M0 trap).
5. UART: `sudo picocom -b 115200 /dev/ttyACM0` (menu) - or build with `-DSR_TEST=1|2|3`.
6. First tests, in this order: T1 (one golden tile) -> `128x128` image via T2 (`run_board.tcl`, compare with `compare_raw.py`) -> 960x540 -> T3.

## Host side (PC)
```
.venv/bin/python software/host_tools/make_test_images.py            # data/board/*.png + .raw  (the DIV2K image is a TRAINING image: no quality numbers!)
.venv/bin/python software/host_tools/expected_output.py data/board/set14_baboon_lr_128x128.raw data/board/exp_128   # integer-model result
software/board/build_elf.sh 2                                                                                          # -> software/board/build/sr_app_t2.elf
xsdb software/board/run_board.tcl software/board/build/sr_app_t2.elf data/board/set14_baboon_lr_128x128.raw data/board/board_128.raw [stats.txt]   # needs the board
.venv/bin/python software/host_tools/compare_raw.py data/board/board_128.raw data/board/exp_128.raw
```
Image format SRIM: `software/host_tools/srim.py`. The board prints `fnv1a32=...` of the output payload; `compare_raw.py` prints the same checksum for the files.

## Things to know
* TIMER: `XTime_GetTime()` gave 0 on the board (the first run printed "tile time 0 us"; cause not isolated). The driver now enables and reads the A9 global timer itself
  (`sr_timer_init`, `sr_now_ticks`). Its 1 s timeouts depend on it.
* LOADING A NEW PROGRAM OVER A RUNNING ONE (no system reset): `rst -processor` does not clear the CPU caches. Dirty lines of the old program were written back
  over the new one on the board (proven: zeros from the old program's .bss inside the new program's MMU table -> data abort; old T2 -> T9 crashed 3 of 3,
  T9 -> T2 failed 3 of 3). run_board.tcl therefore disables the L2 cache and loads the ELF twice; with that, 0 failures in the stale and soak tests
  (results/speed/m6_board.md). This is a measured workaround, not a documented xsdb feature. `SR_SYSRST=1` (system reset, what Vitis does) also avoids it.
* The driver (`sr_init`, and after every tile error/timeout) resets: core soft reset -> AXI DMA reset (wait, ~1 s timeout) -> core soft reset -> check STATUS idle
  and ERROR_CODE 0. Core first: with the DMA reset first, a tile after an "S2MM buffer too short" error came out wrong on the board.
* If xsdb says "AHB AP transaction error" / no ARM targets: `xsdb software/board/dap_reset.tcl` (seen after interrupting programs and after reading AFI registers).
* PL RELOAD RULE (found 2026-10-11, results/speed/m6_board.md 6.7): reprogramming the PL while a DMA transfer is in flight, without holding the PL in reset and
  switching the PS-PL level shifters off first, broke the board after exactly 16 such reloads (every tile then fails, until `rst -system` / `dap_reset.tcl`).
  `run_board.tcl` and `interrupt_test.tcl` do this isolation by default (`SR_NO_ISOLATE=1` only for tests). Vitis' Run does a system reset first, which also avoids it.
  If a run fails with result 7 and stat25 = 2 or 1, or with wrong data: `xsdb software/board/dap_reset.tcl`, then repeat.
* T6 (`build_elf.sh 10`): 1000 x (init reset + one golden tile) for both driver orders; every failure is counted by kind (stats in main.c).
* VERSION 0x53520602 (board bitstream since 2026-10-12, `results/utilization/m6_system_0602.md`) adds debug registers; the driver reads them into its first error dump (stat32..38) when present.
* In this BSP `COUNTS_PER_SECOND` is `XPAR_CPU_CORE_CLOCK_FREQ_HZ/2` WITHOUT parentheses (xtimer_config.h): the sources wrap it (`TICKS_PER_SEC`). `xtime_l.h` does not exist
  in the SDT platform export; `XTime_GetTime` comes from `xiltimer.h` (the sources use `#if defined(SDT)`).
* The driver arms S2MM first, then MM2S, then writes CONTROL.START (the core accepts no data before START). After any timeout or error it soft-resets the core and the DMA.
* The output buffer is flushed BEFORE the DMA (no dirty line can overwrite DMA data) and invalidated AFTER it. The host reads DDR over JTAG, so the program flushes the output image
  before it writes the ready marker.

## Stats block (read by `run_board.tcl`; the UART is not needed)
Words at `SR_MARK_ADDR + 32 + 4*i` (`stat<i>` in the stats file). Times in microseconds (A9 global timer, 325 MHz = CPU 650 MHz / 2; clock registers read on the board).
* T1: stat0..2 CYCLES min/max/mean over 21 runs, stat3..5 tile time min/max/mean, stat6 number of repeats identical to the first run (of 20).
* T2: stat0 total, stat1 padding, stat2 ARM tile copy (cut + place), stat3 DMA + compute wait, stat4..6 CYCLES min/max/mean.
* T3: stat0 frames, stat1..3 frame total mean/min/max, stat4 pad mean, stat5 ARM copy mean, stat6..8 DMA+compute wait mean/min/max, stat9..11 CYCLES min/max/mean.
* T5 (error recovery, SR_TEST=5): stat0 number of cases (4), then per case i: stat(1+3i) rc of the bad tile, stat(2+3i) rc of the reset after it, stat(3+3i) 1 = next tile byte-exact.
* stat24..29 = FIRST register dump of the run (all 0 = none): STATUS, ERROR_CODE, CYCLES, MM2S_SR, S2MM_SR, number of dumps.
