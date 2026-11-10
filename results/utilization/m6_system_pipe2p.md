# Pipeline v2 packed (branch `pipe2p`, VERSION 0x53527301): Vivado system build

Built 2026-11-10, `build_m6_system.tcl` (2 jobs), Vivado 2024.1, xc7z020clg484-1, FCLK0 125 MHz. Project `~/Desktop/venkat/vitis/m6_sr_pipev2p`;
copies in `~/Desktop/venkat/pipe2p_artifacts/` (bit md5 07dd0689d625..., XSA ps7_init md5 d2a7789c...). Post-implementation numbers, NOT board measurements.

| | pipe2 | pipe2p |
|---|---|---|
| WNS / WHS at 125 MHz | +0.231 / +0.019 ns | **+0.450 / +0.007 ns**, all endpoints met |
| Slice LUT | 20,651 (39 %) | **13,323 (25 %)** |
| Slice registers | 21,612 | 19,688 (19 %) |
| BRAM tiles | 27 | 27 |
| DSP48E1 | 220 | **190 (86 %)** |
| Vivado vectorless power (low confidence) | 2.900 W | 2.510 W |
| Critical path | LUT multiplier in s4 | core `pcnt` -> anchor FIFO RAM enable (6 levels) |

Per stage (LUT / FF / DSP): s1 1,655 / 1,849 / 32, s2 1,017 / 3,201 / 23, s3 1,057 / 1,374 / 21, s4 5,539 / 8,348 / 112.
Synthesis log: 12/12 weight files (`wpipe8_*`, `bias_*`, `mult_*`), PACK bound to 1, 0 x Synth 8-311, 0 critical warnings.
Board programs: platform `~/Desktop/venkat/vitis_ws_pipe2p_platform` (xparameters.h identical to pipe's), 12 ELFs (t1/t2/t5/t3_20f x production/fnv/both),
VERSION check compiled as 0x53527300; T1 golden tile simulated 37,621 cycles. Predicted board times as `pipe2` (61.8 ms cached / 37.0 ms non-cacheable).

## Board result (2026-11-10)
Measured at a read-back 125.000 MHz: T1 20/20, T2 byte-exact (0x45dd4e2d), 119/119 test images, T5 PASS x4, VERSION refusal both ways; 20-frame means 61.64 ms cached and 36.96 ms non-cacheable (27.1 fps). Full regression: 124/124. Details in main: `results/board/2026-11-10/SUMMARY.md`.
