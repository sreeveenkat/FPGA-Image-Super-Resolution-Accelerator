# software/board - ARM program, register header and board scripts (M6)

**Status: written and tested on the PC only. Nothing here has run on a ZedBoard.** What IS verified: the register header against the Verilog
(`test_regs.py`), the tiling code against the integer model (`test_tiling.py`, bit-exact incl. 960x540), the host tools (`../host_tools/test_host_tools.py`),
and that the program compiles and links with the Vitis ARM compiler against the BSP of the M0 platform (`check_arm_build.sh`). What is NOT verified: the DMA/driver
behaviour, cache handling, timeouts, `run_board.tcl`, the memory map on hardware, any timing.

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
| `run_board.tcl` | xsdb script: program, run, push input, wait for marker, read output (UNTESTED) |

## Memory map (DDR 0x0000_0000 - 0x1FFF_FFFF, 512 MB)
| Region | Address | Size reserved | Used |
|---|---|---|---|
| BSP reserved | 0x0000_0000 - 0x000F_FFFF | 1 MB | - |
| program (code, data, bss, heap, stack) | 0x0010_0000 - | linked image ends at 0x0012_0870 (SR_TEST=0/1) / 0x0011_0870 (2/3) | ~130 KB |
| input image (SRIM) | 0x1000_0000 | 32 MB | 1.5 MB (960x540) |
| output image (SRIM) | 0x1200_0000 | 16 MB | 6.2 MB (1920x1080) |
| status block (ready marker) | 0x1300_0000 | 64 B | 24 B |
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
xsdb software/board/run_board.tcl data/board/set14_baboon_lr_128x128.raw data/board/board_128.raw                      # needs the board
.venv/bin/python software/host_tools/compare_raw.py data/board/board_128.raw data/board/exp_128.raw
```
Image format SRIM: `software/host_tools/srim.py`. The board prints `fnv1a32=...` of the output payload; `compare_raw.py` prints the same checksum for the files.

## Things to know
* In this BSP `COUNTS_PER_SECOND` is `XPAR_CPU_CORE_CLOCK_FREQ_HZ/2` WITHOUT parentheses (xtimer_config.h): the sources wrap it (`TICKS_PER_SEC`). `xtime_l.h` does not exist
  in the SDT platform export; `XTime_GetTime` comes from `xiltimer.h` (the sources use `#if defined(SDT)`).
* The driver arms S2MM first, then MM2S, then writes CONTROL.START (the core accepts no data before START). After any timeout or error it soft-resets the core and the DMA.
* The output buffer is flushed BEFORE the DMA (no dirty line can overwrite DMA data) and invalidated AFTER it. The host reads DDR over JTAG, so the program flushes the output image
  before it writes the ready marker.
