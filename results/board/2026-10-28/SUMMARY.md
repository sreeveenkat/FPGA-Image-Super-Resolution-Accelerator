# Board session 2026-10-28 (no power meter): pre-flight, VERSION-refusal controls, real 125 MHz runs

JTAG loading only (xsdb); no QSPI, SD or eFuse access. Every bitstream, ELF and XSA init script was checked against `docs/paper/board_expected.md` (49 recorded md5s, all matched) before loading. Die temperature = XADC read through Vivado's hardware manager (`software/board/xadc_temp.tcl`), read only between runs, never during a transfer. Test image for T1-T3: DIV2K img0193, 960x540 -> 1920x1080. Files: `step0/`, `step1/`, `step2/<design>/`.

## Step 0: pre-flight (100 MHz, platform init)
JTAG saw APU (2 x Cortex-A9) and xc7z020 (PL not configured), UART opened, 39.0 C at start. R0 bitstream + R0 ELF: T1 PASS (CYCLES 926,217-926,234, 20/20 repeats), T2 960x540 byte-exact (fnv 0xcf947f22, VERSION 0x53520602, 1,311.4 ms). `step0/`.

## Step 1: VERSION-refusal controls (100 MHz; `step1/`)
Before each mismatched run, four DDR regions were filled with seeded random patterns (output image buffer 7,340,032 B, first 2 MB of the pad buffer, tile in and tile out buffers) by `dow -data`; read back by `mrd` before and after the run; compared with `cmp`.

| Control | Bitstream + ELF | UART message | Marker | DDR (8 dumps) | DMA / accelerator registers | UART tile/frame lines |
|---|---|---|---|---|---|---|
| a | pipe (VERSION 0x53525301) + R3q T2 ELF | `SR: VERSION 0x53525301, expected 0x53523201 (wrong SR_BASE 0x40000000 or wrong bitstream)`, `sr_init failed: 2` | result=2, 0 bytes, 0 tiles | all identical to the patterns | MM2S/S2MM SA, DA, LENGTH = 0, DMASR unchanged (0x1, halted, never idle), STATUS = 0, CYCLES = 0 before and after | none (`init ok` never printed) |
| b | R2q (0x53522201) + R0 T2 ELF | `SR: VERSION 0x53522201, expected 0x53520602 (...)`, `sr_init failed: 2` | result=2 | all identical | same as a | none |

Healthy board afterwards: (a) pipe + pipe T2 ELF: VERSION 0x53525301, fnv 0x45dd4e2d, BYTE-EXACT, 111.998 ms (100 MHz); (b) R2q + R2q T2 ELF: VERSION 0x53522201, fnv 0x2afbc9ae, BYTE-EXACT, 1,311.4 ms. **PASS both.** Caveat: `sr_init` resets the DMA (`XAxiDma_CfgInitialize`) BEFORE it reads VERSION, so the evidence is "no transfer started, nothing written to DDR", not "the DMA IP was never touched". Details: `step1/refusal_ddr_and_registers.txt`.

## Step 2: real 125 MHz runs (`step2/`)
Each design with its OWN XSA's `ps7_init.tcl` (md5 d2a7789c85395e17649026335f23d938, identical for the three; differs from the platform script `86bd78c7...` only in `mask_write 0XF8000170` 0x00200500 -> 0x00200400, in all three silicon-revision blocks). Implementation timing (Vivado, 125 MHz): r0_125 WNS +0.632 / WHS +0.032 / TNS 0; r3q_125 +0.393 / +0.025 / 0; pipe +0.267 / +0.014 / 0; 0 failing endpoints in all.

**Clock readback on the board before every run (every T1, T2, T3 and image run; the 119 images x 3 designs alone are 357 runs):** `FPGA0_CLK_CTRL = 0x00200400` (SRCSEL = 0 IO PLL, DIVISOR0 = 4, DIVISOR1 = 2), `IO_PLL_CTRL = 0x0001e008` (FDIV = 30), `PLL_STATUS = 0x3f` (IO PLL locked): FCLK0 = 33.3333 MHz x 30 / (4 x 2) = **125.000 MHz**. The script refuses to run otherwise (script test at 100 MHz read 0x00200500 -> 100.000 MHz).

| Design | VERSION | T1 | T2 byte-exact (fnv) | T3 20 frames mean / min / max (ms) | fps | 119 images byte-exact | die temp (C) before / 40 / 80 / end |
|---|---|---|---|---|---|---|---|
| r0_125 | 0x53524201 | PASS, CYCLES 926,222-926,225 | yes (0xcf947f22) | **1,061.85 / 1,061.26 / 1,062.96** | 0.9418 | **119/119** | 47.9 / 48.5 / 48.8 / 48.7 |
| r3q_125 | 0x53524301 | PASS, CYCLES 926,222-926,225 | yes (0x45dd4e2d) | **1,061.68 / 1,061.26 / 1,063.29** | 0.9419 | **119/119** | 48.4 / 49.0 / 49.2 / 48.5 |
| pipe | 0x53525301 | PASS, CYCLES 74,652-74,681 | yes (0x45dd4e2d) | **95.36 / 95.19 / 96.79** | 10.487 | **119/119** | 48.8 / 48.0 / 47.9 / 47.9 |

(T3 temperature also read after T3: 48.5 / 49.1 / 48.1.) Highest die temperature of the session 49.2 C; limit used 70 C. No failure, no hang, no recovery to 100 MHz needed. Every image was within 1.014 x its expected time (limit 3 x).

Model comparison (960x540, T3 means):
| Design | Predicted | Measured | Difference | Cycle part (predicted -> measured) | Overhead (predicted -> measured) |
|---|---|---|---|---|---|
| r0_125 | 1,061.8 ms (model; 1,000.3 + 61.0) | 1,061.85 ms | +0.05 ms (+0.005 %) | 926,205 x 135 / 125 MHz = 1,000.3 ms -> CYCLES 926,225 -> 1,000.3 ms | 61.0 -> 61.5 ms (pad 5.97 + copy 26.41 + DMA wait 29.1) |
| r3q_125 | about 1,062 ms (same cycles) | 1,061.68 ms | -0.1 ms | same | 61.4 ms |
| pipe | 95.2 ms (67.2 + 28.0) | 95.36 ms | +0.16 ms (+0.17 %) | 8,398,481 / 125 MHz = 67.19 ms -> CYCLES 8,398,495 -> 67.19 ms | 28.0 -> 28.2 ms (pad 5.79 + 22.4 DMA/cache) |
All within 3 %; the small differences are in the overhead (0.2-0.5 ms), not in the cycle counts (a few tens of cycles per tile = 0.02 ms per frame). The pipeline's ~22.4 ms of DMA/cache overhead is the same as at 100 MHz (106.4 - 84.0 = 22.4 ms): it does not scale with the PL clock, so it is not PL time (not yet separated into cache flush / DMA set-up / invalidate: step 3).

119 images (per-frame totals; the images have different sizes, 1,473 tiles in total, so the mean is not comparable with the 960x540 figure):
| Design | mean / min / max (ms per image) | ms per tile (sum) | CYCLES (per tile; pipe: per frame) |
|---|---|---|---|
| r0_125 | 96.65 / 31.31 / 235.04 | 7.808 | 926,223-926,252 |
| r3q_125 | 96.65 / 31.31 / 235.03 | 7.808 | 926,223-926,252 |
| pipe | 7.66 / 3.21 / 19.46 | (0.619 ms per tile-equivalent) | 279,965-1,703,646 per frame |
Per set (mean ms): tiled Set5 68.67, Set14 128.05, BSD100 93.66 (all 100 images 93.64-93.67); pipe 5.45, 10.90, 7.32.

## Speed-ups, all MEASURED
* 125 MHz tiled vs the same design at 100 MHz (R0 1,311.7 ms): 1.235x (clock ratio 1.25, +4 cycles per tile, unchanged ARM overhead).
* Pipeline at 125 MHz vs at 100 MHz (112.1 ms): 1.176x (core part 84.0 -> 67.2 ms, overhead unchanged).
* Pipeline at 125 MHz vs R0 at 100 MHz: 13.76x; vs the ARM alone (about 13.4 s, host-timed): about 140x. Throughput 1.33 G MAC x 2 / 95.36 ms = about 27.8 GOPS end to end.

Not done this session (as agreed): step 3 (overhead timing), step 4 (T7 timer fix), power (no meter). New scripts of this session (committed with this summary): `software/board/{xadc_temp.tcl, run_board_clk.tcl, run_125.py, refusal_test.tcl, refusal_run.sh}`; `software/analysis/board_expected.py` and `docs/paper/board_expected.md` gained a ps7_init section.
