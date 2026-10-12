# M7 table B - speed, 20-frame timing run (board-measured)

Run 2026-10-12 18:38-18:39 on the ZedBoard, bitstream **0602** (`m6_sr_0602`, VERSION 0x53520602, 100 MHz), program T3 built with
`software/board/build_elf.sh 3 -DSR_T3_FRAMES=20` (default build keeps 5 frames), loaded with `run_board.tcl` default safe loading (PL isolation on, L2 off,
ELF loaded twice). Input: DIV2K img0193 960x540 (`data/board/div2k_img0193_lr_960x540.raw`) -> 1920x1080, 135 tiles of 64x64, the same frame 20 times.
Times: ARM global timer (325 MHz) around the whole tile loop, per frame. Raw values: `m7_t3_20frames_stats.txt` (stat0..11), xsdb log `m7_t3_20frames_xsdb.log`.

**Correctness:** all 20 frames gave the same output (checked on the ARM), and the frame read back is **byte-exact** vs the integer model
(6,220,800 bytes, fnv1a32 0xcf947f22).

| Metric | Value | How |
|---|---|---|
| Time per frame, mean of 20 | **1,311.9 ms** | stat1 = 1,311,895 us |
| Spread (min / max) | 1,311.4 / 1,313.2 ms (max - min 1.7 ms = 0.13 %) | stat2 / stat3 |
| FPS | **0.762 fps** | 1 / mean |
| Input pixels per second | 395 k px/s (960x540 / 1.312 s) | |
| Output pixels per second | 1.58 M px/s (1920x1080 / 1.312 s) | |
| CYCLES per tile (hardware counter) | min 926,217, max 926,241, mean 926,220 (2,700 tiles) | stat9..11; simulation 926,202 |
| Data moved by the DMA per frame | 8,620,020 B (135 x (14,700 in + 49,152 out)) | |
| Effective DMA throughput | 6.7 MB/s over the DMA+compute time (not the DMA's raw speed: the DMA waits for the core, which streams 1 byte per cycle and computes in between) | bytes / stat6 |

## Where the time goes (mean per frame)
| Part | ms | % of frame |
|---|---|---|
| Padding the input (ARM) | 5.9 | 0.4 % |
| ARM tile copies (cut + place) | 26.4 | 2.0 % |
| DMA + compute wait | 1,279.6 | 97.5 % |
| - of which core cycles (135 x 926,220 / 100 MHz) | 1,250.4 | 95.3 % |
| - of which DMA set-up + handshakes + driver (rest) | 29.2 | 2.2 % |
| Loop overhead | 0.03 | 0.0 % |

DMA+compute per frame min/max: 1,279.1 / 1,280.8 ms (stat7/8).

**Bottleneck:** the accelerator core itself (95 % of the frame). Inside the core, the engines take 854,149 of the 926,201 cycles per tile (92 %, from
simulation), and L4 alone 589,844 (64 %). The ARM side and the DMA are small. A faster design needs more parallel MACs in L4 and overlapping
load / compute / output, not a faster ARM loop.

**Prediction check:** `tiles x cycles / f` = 135 x 926,220 / 100 MHz = 1,250.4 ms; measured 1,311.9 ms (+4.9 %, the ARM copies, padding and DMA handshakes).

Agrees with the earlier board runs (15 frames on 0601, 3 x 5 frames on 0602: 1,311.4-1,313.3 ms; `m6_board.md`, `../utilization/m6_system_0602.md`).
