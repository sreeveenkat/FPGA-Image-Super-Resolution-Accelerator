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

# Part 2 (same day): driver change, refusal re-test, timing split, T7 timer, A/B (`driver_change/`)

Approved changes (patch: `driver_change/proposed_driver_change/`, applied to the five tiled trees and the pipeline tree, committed in main and in each sandbox branch on 2026-10-28): (1) VERSION check before `XAxiDma_CfgInitialize`; (2) `sr_timer_init()` at the start of T7; (3) `-DSR_TIMING_SPLIT` timing split, compiled out otherwise. With the flag off the compiled objects are identical to the old ones except `sr_init` (and `main` for SR_TEST=11); 0 warnings from our code.

## New production ELFs on all six designs (`verify/`)
T1, T2 byte-exact, T3 20 frames, all inside +-2 ms of the old-ELF means, max - min <= 3 ms; T5 PASS on R0 and the pipeline. Clock read back: 100.000 MHz (R0, R2q, R3q), 125.000 MHz (r0_125, r3q_125, pipe).
| Design | VERSION | T2 | T3 mean new ELF (old ELF) ms |
|---|---|---|---|
| R0 | 0x53520602 | byte-exact | 1,312.45 (1,311.7) |
| R2q | 0x53522201 | byte-exact | 1,312.29 (1,312.0) |
| R3q | 0x53523201 | byte-exact | 1,312.35 (1,311.6) |
| r0_125 | 0x53524201 | byte-exact | 1,062.21 (1,061.85) |
| r3q_125 | 0x53524301 | byte-exact | 1,062.35 (1,061.68) |
| pipe | 0x53525301 | byte-exact | 95.36 (95.36) |
The paper reports the new-ELF numbers (the production ELF).

## Refusal re-test with a DMA marker (`refusal_retest/`)
Guard: both channels halted (DMASR.Halted = 1, DMACR.RS = 0, read only) before the write; only `MM2S_SA` and `S2MM_DA` were written (0xA5A5A5A0 / 0x5A5A5A50), read back equal. Old ELF (control) -> marker cleared to 0 (the DMA reset ran): the test discriminates. New ELF -> marker intact: **the DMA is not touched on a VERSION mismatch.** Both pairs (pipe bitstream + R3q ELF; R2q bitstream + R0 ELF), same result; DDR patterns unchanged; UART shows only the VERSION message and `sr_init failed: 2`. Healthy pair afterwards byte-exact (R2q 0x2afbc9ae, pipe 0x45dd4e2d).

## Where the DMA-wait overhead goes (`split/`, 125 MHz, flagged ELFs, 20-frame means, us per frame)
| Part | pipe (1 transfer) | r0_125 (135 tiles) | r3q_125 (135 tiles) |
|---|---|---|---|
| busy check + registers | 0.0 | 32.8 | 32.8 |
| flush input | 2,855.6 | 6,171.2 | 6,170.9 |
| flush output | 9,570.2 | 11,301.5 | 11,386.1 |
| DMA set-up + START | 2.5 | 366.6 | 366.8 |
| wait loop | 67,188.0 | 1,000,739.6 | 1,000,819.1 |
| check + invalidate output + CYCLES | 9,870.3 | 10,628.8 | 10,628.9 |
| sum (= the DMA/compute window, -1.3 / -71 us) | 89,489.3 | 1,029,242.9 | 1,029,406.8 |
| core cycles / clock | 67,188.0 (wait - core = 0.0) | 1,000,323.0 (wait - core = +416.6) | same (+496.1) |
The pipeline's wait equals its core cycles to the microsecond, so **cache maintenance is the whole ~22.3 ms of overhead** (flush in 2.86 + flush out 9.57 + invalidate 9.87 ms; DMA set-up 2.5 us). For the tiled designs the non-core part of the window is 28.9 ms, of which 28.1 ms is cache maintenance. Per byte: flush in 1.80 ns, flush out 1.54 ns, invalidate 1.59 ns (pipeline). Flagged T3 means 1,061.71 / 1,061.96 / 95.20 ms, byte-exact (within +-2 ms of the production ELF). Not done: any change to the cache handling (it would be a driver change needing approval and the full byte-exact re-verification). Observation only: the output-buffer flush plus invalidate are 19.4 ms of the pipeline's 95.2 ms.

## T7 with the timer fixed (`split/R0_t7/`)
R0 tree, 100 MHz, byte-exact (0xcf947f22). ARM timer: total **13,433,337 us** = pad 5,971 + ARM tile copy 21,234 + ARM compute 13,406,098; host timestamps of the UART lines 13.423 s (agree within 10 ms; the 27 Oct host-timed 13.4 s +-0.2 s is confirmed). Two more runs the same afternoon (`split/t7_run2`, `split/t7_run3`, both byte-exact 0xcf947f22): 13,434,953 us and 13,442,844 us (host timestamps 13.418 s each). **3-run mean 13,437,045 us (13.437 s)**, min 13.433, max 13.443 s, spread 9.5 ms, standard deviation 5.1 ms. Baseline definition: one Cortex-A9 core (core 0) at 650 MHz, caches on, `arm-none-eabi-gcc` 12.2.0 `-O2 -mcpu=cortex-a9 -mfpu=vfpv3 -mfloat-abi=hard`, plain C integer model (`sr_swmodel.c`), no NEON (no SIMD instruction in the ELF), no threads, no loop tuning; so the speed-ups below are against this simple baseline. Speed-ups with the mean: pipeline at 125 MHz 140.9x, r0_125 12.65x, R0 at 100 MHz 10.24x.

## A/B of the ARM tile-copy shift, R0 at 100 MHz, 20-frame T3 (`ab/`)
| Run | frame mean ms | ARM tile copy ms | DMA+compute ms | pad ms | die C before |
|---|---|---|---|---|---|
| old 1 | 1,312.151 | 26.564 | 1,279.668 | 5.888 | 50.9 |
| new 1 | 1,312.322 | 26.909 | 1,279.494 | 5.887 | 51.7 |
| old 2 | 1,311.702 | 26.400 | 1,279.382 | 5.888 | 51.9 |
| new 2 | 1,312.505 | 26.910 | 1,279.589 | 5.974 | 52.2 |
Tile-copy gap (new - old): +0.345 ms (pair 1), +0.510 ms (pair 2); every new run is above every old run (26.909, 26.910 vs 26.564, 26.400). Frame-mean gap +0.17 / +0.80 ms. The script's pre-registered rule (gap > 3 x the old-ELF run-to-run difference of 0.164 ms) was NOT met and printed "drift"; that rule was the right test. Temperature rose 50.9 -> 52.2 C over the four runs but the hottest old run (old 2) had the lowest copy time. **Label (owner, 2026-10-28): unresolved, <= 0.5 ms (< 0.04 % of the frame).** The tile-copy code is unchanged at object level; the cause (code placement or something else) was not isolated.

# Part 3 (same day): non-cacheable DMA buffers, pipeline tree only (`driver_change/nc/`, `driver_change/verify2/`)

Owner-approved change, pipeline branch only (`-DSR_NC_OUT`, `-DSR_NC_PAD`, both OFF by default; diff `driver_change/proposed_driver_change/applied_nc_pipe_tree.diff`). Checks before building: (1) linker map: all sections, heap, stacks and the MMU table lie in 0x00100000-0x00112150 (T5 build up to 0x0012E1D0, MMU table 0x00108000 / 0x00118000), nothing in 0x12000000-0x12FFFFFF or 0x14000000-0x15FFFFFF; (2) `NORM_NONCACHE` = 0x11DE2 decodes as short-descriptor section, TEX=001, C=0, B=0, S=1, XN=0 = Normal memory, outer and inner non-cacheable (not Device, not Strongly-ordered; Device is TEX 000 C0 B1, Strongly-ordered TEX 000 C0 B0), so unaligned LDR/STR in `sr_pad_image` are legal as before (LDM/STM/LDRD need word alignment in any memory type and are unchanged). With both flags off the compiled `sr_driver.c` and `main.c` (SR_TEST 2, 3) are identical to the committed ones (all functions identical); the production ELFs differ from the committed build only by the 20-byte GNU build-id note.

Regions: output 0x12000000 + 16 MB (sections 0x120-0x12F), padded input 0x14000000 + 32 MB (sections 0x140-0x15F), all 1 MB aligned (static assert); marker block, IN buffer, tile buffers, program stay cacheable.

Re-verification before the flagged runs (patched tree, flags off): all six designs T1/T2 byte-exact, T3 means 1,312.48 / 1,312.38 / 1,312.47 / 1,062.36 / 1,062.33 / 95.28 ms (all inside +-2 ms of the old-ELF means), T5 PASS on R0 and pipe (`verify2/`).

## Flagged runs, pipeline, REAL 125 MHz, 20-frame means (all byte-exact 0x45dd4e2d, T1 and T5 PASS in every variant)
`fnv` = cached reference build (only adds the timing print of the ARM's output read). A/B/A/B order, then OUT-only and PAD-only.
| Run | Frame time ms (min / max) | Pad ms | DMA+compute ms | ARM output read ms (flush or drain + FNV-1a) | Wall per frame (frame + read) ms | NC set-up (once) |
|---|---|---|---|---|---|---|
| fnv 1 (cached) | 95.36 (95.18 / 96.93) | 5.70 | 89.65 | 63.66 | 159.02 | - |
| both 1 | **70.52** (70.52 / 70.53) | 3.32 | 67.19 | 620.48 | 690.99 | 87.1 ms |
| fnv 2 (cached) | 95.36 (95.18 / 96.92) | 5.78 | 89.58 | 63.65 | 159.01 | - |
| both 2 | **70.52** (70.52 / 70.53) | 3.32 | 67.19 | 620.52 | 691.04 | 87.1 ms |
| out only | 75.85 (75.76 / 77.33) | 5.71 | 70.14 | 620.36 | 696.21 | 29.0 ms |
| pad only | 89.96 (89.96 / 89.97) | 3.32 | 86.64 | 64.07 | 154.03 | 58.1 ms |
Predictions (model, made before the run): both 73.0 + dpad (dpad -1..+4) = 72-77 ms; out only 75.8; pad only 92.3 + dpad. Measured: out only 75.85 (+0.05), pad only 89.96 = 92.3 - 2.4, both 70.52. **The padding got faster, not slower (5.70 -> 3.32 ms, -2.4 ms)**: writes to non-cacheable memory skip the write-allocate line fills. With both buffers non-cacheable the DMA+compute window equals the core cycles (67.19 ms = 8,398,495 cycles / 125 MHz): all the cache-maintenance overhead is gone. Frame 95.36 -> 70.52 ms (-24.8 ms, -26 %), 14.2 fps; vs R0 at 100 MHz 18.6x, vs the ARM-only baseline (13.437 s) 190x, about 37.6 GOPS end to end; the core is 95.3 % of the frame time.

**Frame time excludes the ARM's read of the output, on purpose:** the frame window runs from the start of the ARM padding to the end of the DMA/compute wait (`process_frame`). The checksum over the output (FNV-1a, byte-wise) is verification work of the test program, done after the window; a pipeline that hands the output buffer to something else does not read it. But a design where the ARM must read the output pays for it: **a byte-wise ARM read of the 6.2 MB output is about 10x slower from non-cacheable memory (620 ms vs 63.7 ms, which includes the flush)**, so the wall time of frame + checksum read goes UP (159 ms -> 691 ms). Not measured: a word-wise read (a wider read would be faster), or invalidating a cacheable buffer once instead of per frame. Side effects measured: padding faster (above), ARM output read 10x slower, one-time set-up 29-87 ms (clean + invalidate of 16 / 32 MB then 16 / 32 section updates).

Board returned to its normal state: production pipeline ELF reloaded at 125 MHz, one T2 byte-exact (0x45dd4e2d), VERSION 0x53525301, FCLK0 125.000 MHz. Die temperature 49.6-50.0 C during the runs. Committed 2026-10-28 (main and `sandbox_pipe`). Second reported configuration (not the default; flags off by default): **70.52 ms (14.2 fps) with non-cacheable DMA buffers, applicable when the output goes to another DMA master such as a display; ARM output reads become ~10x slower (620 vs 64 ms).** Headline stays 95.4 ms / 10.49 fps (default build).
