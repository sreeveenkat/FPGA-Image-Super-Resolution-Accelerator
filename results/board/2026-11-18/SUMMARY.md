# Board session 2026-11-18 (ZedBoard, JTAG only, no power meter)

All numbers below were measured on the board today; logs in `logs/` (no raw images). Clock = the value READ BACK from the PS clock registers in every run.

## 1. pipe3 (pipeline v2 packed + PL padding, 142.857 MHz, VERSION 0x53528301), first time on a board

`run_125.py pipe3` (`logs/run_125_pipe3.log`), FCLK0 read back 0x00100700: IO PLL 1000 MHz / (7 x 1) = **142.857 MHz** in every run.

| Step | Result | Expected (board_checklist 5g) |
|---|---|---|
| T1 golden tile (padded, PAD_EN = 0) | result 0, 20/20 repeats, CYCLES 37,631-37,634 | 37,621-37,680 |
| T2 960x540 (RAW frame, PAD_EN = 1) | **byte-exact**, fnv 0x45dd4e2d, frame CYCLES 4,205,065 | 4,205,054-4,226,080 (xsim 4,205,054) |
| T3 20 frames, cached buffers | mean **51.37 ms**, pad 0 us | 49.7-53.7 (predicted 51.7) |
| 119 test images | **119/119 byte-exact** | 119/119 |
| die temperature | 38.8 C (after T3) to 47.4 C (after image 119) | below 70 C |

Speed variants, `run_nc.py --design pipe3` (`logs/run_nc_pipe3.log`), 20-frame means, every run byte-exact, order fnv/both/armpad/both/armpad/fnv:

| Variant (same bitstream) | Frame | Pad | DMA + compute | Predicted |
|---|---|---|---|---|
| `both`: non-cacheable in + out, PL padding | **29.44 ms = 34.0 fps** (min = max 29.44) | 0 | 29.44 | 27.4-31.5 (29.4) |
| `armpad`: ARM pads into the non-cacheable pad region | 32.75 ms | 3.32 | 29.43 | 30.7-34.7 (32.7) |
| `fnv`: cached buffers | 51.45 / 51.46 ms | 0 | 51.45 | 49.7-53.7 (51.7) |

* PL padding alone (same bitstream, same clock): 32.75 -> 29.44 ms (-3.31 ms).
* Clock alone: pipe2p at 125 MHz with ARM padding 36.95 ms (2026-11-10) -> pipe3 `armpad` at 142.857 MHz 32.75 ms (-4.20 ms).
* Total vs pipe2p: 36.95 -> 29.44 ms = **1.26x** (27.1 -> 34.0 fps). vs R0 (1,311.9 ms at 100 MHz): 44.6x.
* ARM read of the output after the frame (not part of the frame time): 63.8 ms cached, 620.5 ms non-cacheable (as for pipe2p).
* Production ELF reloaded after the flagged runs: T2 byte-exact at 142.857 MHz.

VERSION refusal (`logs/neg/`): pipe3 bitstream + pipe2p ELF -> "VERSION 0x53528301, expected 0x53527301", result 2; pipe2p bitstream + pipe3 ELF -> "VERSION 0x53527301,
expected 0x53528301", result 2. Both refused before the DMA is touched.

## 1b. pipe4 (6 cycles per LR pixel + PL padding, 142.857 MHz, VERSION 0x53529301), first time on a board

Built the same day (branch `pipe4`, `docs/ARCHITECTURE_PIPELINE_V4.md` there). `run_125.py pipe4` (`logs/run_125_pipe4.log`), FCLK0 read back 142.857 MHz in every run.

| Step | Result | Expected |
|---|---|---|
| T1 golden tile (padded) | result 0, 20/20, CYCLES 28,374-28,384 | 28,365-28,424 (simulation 28,365) |
| T2 960x540 (RAW frame) | **byte-exact**, fnv 0x45dd4e2d, frame CYCLES 3,156,225 | 3,156,214-3,171,995 (xsim 3,156,214) |
| T3 20 frames, cached | mean 44.11 ms | predicted 44.4 |
| 119 test images | **119/119 byte-exact** | 119/119 |
| die temperature | up to 50.4 C (after image 119) | below 70 C |

`run_nc.py --design pipe4` (`logs/run_nc_pipe4.log`), every run byte-exact:

| Variant (same bitstream) | Frame | Pad | DMA + compute | Predicted |
|---|---|---|---|---|
| `both` non-cacheable in + out, PL padding | **22.10 ms = 45.2 fps** (min = max) | 0 | 22.10 | 22.1 |
| `armpad` | 25.41 ms | 3.32 | 22.09 | 25.4 |
| `fnv` cached | 44.11 ms | 0 | 44.11 | 44.4 |

* vs pipe3 (29.44 ms): 1.33x; vs pipe2p (36.95 ms): 1.67x; vs R0 (1,311.9 ms): 59.4x.
* VERSION refusal (`logs/neg/pipe4_neg*`): pipe4 bitstream + pipe3 ELF -> "VERSION 0x53529301, expected 0x53528301", result 2; pipe3 bitstream + pipe4 ELF -> the reverse, result 2.
* Production ELF reloaded after the flagged runs: T2 byte-exact.

## 2. Re-check of every earlier design (same bitstreams and ELFs as recorded in docs/paper/board_expected.md)

`verify_driver_change.py` (T1, T2, T3 20 frames vs the earlier board mean +-2 ms and max-min <= 3 ms; T5 on R0 and pipe) and `run_125.py --only t1,t2,t3` (pipe2, pipe2p).

| Design | Clock (read back) | T1 | T2 | T3 mean (earlier) | T5 |
|---|---|---|---|---|---|
| R0 | 100.000 | OK, 926,217-926,220 | byte-exact 0xcf947f22 | 1,312.51 ms (1,311.7) | PASS |
| R2q | 100.000 | OK | byte-exact 0x2afbc9ae | 1,312.51 ms (1,312.0) | - |
| R3q | 100.000 | OK | byte-exact 0x45dd4e2d | 1,312.70 ms (1,311.6) | - |
| r0_125 | 125.000 | OK | byte-exact 0xcf947f22 | 1,062.20 ms (1,061.85) | - |
| r3q_125 | 125.000 | OK | byte-exact 0x45dd4e2d | 1,062.35 ms (1,061.68) | - |
| pipe | 125.000 | OK, 74,652-74,672 | byte-exact 0x45dd4e2d | 95.20 ms (95.36) | PASS |
| pipe2 | 125.000 | OK, 37,633-37,640 | byte-exact 0x45dd4e2d | 61.6 ms (61.64) | - |
| pipe2p | 125.000 | OK, 37,632-37,635 | byte-exact 0x45dd4e2d | 61.6 ms (61.64) | - |
| pipe3 | 142.857 | section 1 | section 1 | section 1 | - |
| pipe4 | 142.857 | section 1b | section 1b | section 1b | - |

Flags (timing spread only, outputs byte-exact): the FIRST R0 run had one slow frame (max 1,315.15 ms, max-min 3.28 ms > 3 ms rule, `logs/verify_all.log`) and the
first R2q run likewise (max-min 3.11 ms, `logs/verify_rest.log`); because the script stops at the first miss, each design was then run separately: R0 repeat
max-min 1.80 ms + T5 PASS, R2q repeat 1.78 ms, all others <= 2.64 ms. The tiled designs' means are 0.5-1.1 ms above the earlier references (inside +-2 ms). Not
investigated: the cause of single frames +3 ms slower in the tiled designs (seen before: `results/speed/m6_board.md:71`, single frames +2.1 ms).

Not done: power (no meter), the 119-image runs of the earlier designs (done in earlier sessions).
