# Board session 2026-10-27: results (no power measured)

Board: ZedBoard on JTAG, boot mode JTAG (SLCR BOOT_MODE = 0), die temperature 42 to 50.3 C (XADC, `xadc_temperature.log`; limit 80 C never approached). Every bitstream and ELF was checked against its recorded md5 before use (`docs/paper/board_expected.md`). Test image: DIV2K img0193, 960x540 -> 1920x1080. **Power: not measured yet.**

**All six designs ran with the PL clock at 100.000 MHz** (FPGA0_CLK_CTRL read back as DIV0=5, DIV1=2): `run_board.tcl` sources the platform's `ps7_init.tcl`, which sets the 100 MHz divisors after the bitstream is loaded. The three '125 MHz' bitstreams therefore did NOT run at 125 MHz; their frame times below are 100 MHz numbers. (Evidence: r3q and r3q_125 have the same tile time, 9.52 ms, and the same frame time.)

| Design | Built for (MHz) | VERSION read | VERSION expected | T2 fnv1a32 | Expected | byte-exact | T1 CYCLES min-max | CYCLES per tile / frame (T3 min-max) | PL compute per frame (ms) | End-to-end frame mean / min / max (ms) | fps | Speed-up vs R0 | Speed-up vs T7 |
|---|---|---|---|---|---|---|---|---|---|---|---|---|---|
| R0 (0602) | 100 | 0x53520602 | 0x53520602 | 0xcf947f22 | 0xcf947f22 | yes | 926,218-926,232 | 926,217-926,241 | 1,279.4 | 1,311.7 / 1,311.4 / 1,313.1 | 0.762 | 1.00x | 10.2x |
| pipe | 125 | 0x53525301 | 0x53525301 | 0x45dd4e2d | 0x45dd4e2d | yes | 74,651-74,654 | 8,398,491-8,398,508 | 106.4 | 112.1 / 112.0 / 113.6 | 8.923 | 11.70x | 119.7x |
| R3q | 100 | 0x53523201 | 0x53523201 | 0x45dd4e2d | 0x45dd4e2d | yes | 926,217-926,229 | 926,217-926,241 | 1,279.3 | 1,311.6 / 1,311.4 / 1,312.2 | 0.762 | 1.00x | 10.2x |
| r3q_125 | 125 | 0x53524301 | 0x53524301 | 0x45dd4e2d | 0x45dd4e2d | yes | 926,222-926,240 | 926,221-926,245 | 1,279.5 | 1,311.8 / 1,311.4 / 1,313.2 | 0.762 | 1.00x | 10.2x |
| R2q | 100 | 0x53522201 | 0x53522201 | 0x2afbc9ae | 0x2afbc9ae | yes | 926,217-926,220 | 926,217-926,236 | 1,279.7 | 1,312.0 / 1,311.4 / 1,314.2 | 0.762 | 1.00x | 10.2x |
| r0_125 | 125 | 0x53524201 | 0x53524201 | 0xcf947f22 | 0xcf947f22 | yes | 926,222-926,224 | 926,221-926,245 | 1,279.6 | 1,311.9 / 1,311.4 / 1,313.0 | 0.762 | 1.00x | 10.2x |

T7 (ARM only, Cortex-A9, C integer model, one frame, byte-exact, fnv 0xcf947f22): **about 13.4 s per frame** (0.075 fps) Note: the ARM-side timer was not running in the T7 build (it prints 0 us), so this is derived from the host timestamps of the T7 start and done lines in `r0_t7.log` (7.812 s and 21.231 s after capture start) and agrees with the xsdb wall clock (13 s); precision about +-0.2 s. R0 is 10.2x faster than the ARM alone; the pipeline 120x.


## Pass / fail per step (window = the pass criteria of `docs/paper/board_checklist.md` / `board_expected.md`)
| Design | T1 (VERSION, golden tile, 20/20 repeats, CYCLES window) | T2 (checksum, byte-exact) | T3 (20 frames, CYCLES) | Other steps |
|---|---|---|---|---|
| R0 | PASS (926,218-926,232 in 926,210-926,241) | PASS | PASS | **T7 ARM-only PASS** (byte-exact, 13.4 s per frame, host-timed) |
| pipe | PASS (74,651-74,654 in 74,641-74,700) | PASS (frame CYCLES 8,398,493 in 8,398,481-8,440,473) | PASS (frame CYCLES 8,398,491-8,398,508) | **T5 error recovery PASS** (4 bad frames, each followed by a byte-exact good one); **119/119 test images byte-exact** (`pipe_testsets.log`); negative control (b): output vs the R0 expected file is NOT byte-exact (77.8 % of bytes differ) as required; negative control (a) VERSION refusal: **not run** (see below) |
| R3q | PASS | PASS | PASS | - |
| r3q_125 | PASS (926,222-926,240 in 926,214-926,245) | PASS | PASS | frame time 1,311.8 ms is outside the predicted 1,033-1,064 ms **because the PL ran at 100 MHz** (see below), so this does not test the 125 MHz claim |
| R2q | PASS | PASS | PASS | negative control (b): output vs R0 expected NOT byte-exact (80.1 %) as required; negative control (a) VERSION: not run |
| r0_125 | PASS | PASS | PASS | same clock remark as r3q_125 |

Not run today: power (no meter), the 119 test images and T5 for the four tiled designs (not requested in the priority list), the VERSION-refusal negative controls (they load a bitstream
with an ELF of another tree, which is not a "matching ELF"; I did not do it without asking), the drift check (needs power).

## What the numbers say
* **Every bitstream is byte-exact on the board** with its own expected checksum (R0/r0_125 0xcf947f22, R3q/r3q_125/pipe 0x45dd4e2d, R2q 0x2afbc9ae), and every VERSION read back correctly. No hang, no timeout, no retry.
* **Pipeline: 112.1 ms per frame (8.92 fps), 11.7x faster than R0 and about 120x faster than the ARM alone**, while computing the same bytes as R3q. Mean/min/max over 20 frames 112.1 / 112.0 / 113.6 ms.
* **That was at 100 MHz, not 125 MHz.** 8,398,494 cycles at 100 MHz = 84.0 ms; the measured PL-side time per frame (DMA + compute, 106.4 ms) leaves about 22 ms outside the core cycles
  (cache flush/invalidate of the 1.6 MB input and 6.2 MB output buffers, DMA set-up; not separated today). **Estimate, not measured:** at 125 MHz the same overhead gives about 67.2 + 22.4 + 5.7 = 95 ms.
* **The 125 MHz claim is untested.** The three 125 MHz bitstreams were built with FCLK0 = 125 MHz, but `run_board.tcl` runs the platform's `ps7_init.tcl` (generated 2026-10-11 for 100 MHz) after loading the bitstream
  and sets the 100 MHz divisors (read back: FPGA0_CLK_CTRL = 0x00200500, DIV0 = 5, DIV1 = 2). I did not change it (your rule on clocks). To test 125 MHz, the init script of the 125 MHz XSA must be used
  (`ps7_init.tcl` from `~/Desktop/venkat/R*_125_artifacts/*.xsa` / `pipe_artifacts`), a change of the FPGA0 clock setting that I need your approval for.
* R2q/R3q/R0 have the same speed (same cycles per tile); the quality differences are in the images, not the time.
* Power, energy per frame: **not measured yet.**
