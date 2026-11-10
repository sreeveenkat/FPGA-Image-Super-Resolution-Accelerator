# Pipeline v2: 8 cycles per LR pixel (branch `pipe2`)

Status (2026-11-10): BOARD-MEASURED 27.1 fps (36.95 ms non-cacheable, 61.64 ms cached), 119/119 byte-exact. RTL simulated, netlist-simulated, built (125 MHz met, WNS +0.231 ns, 20,651 LUT, 220 DSP;
`results/utilization/m6_system_pipe2.md`); board programs built and run on the board 2026-11-10. Numbers marked *model* are predictions from
`software/analysis/cycle_model.py` Part 6 (main tree), not measurements.

## Why

The built pipeline (branch `pipe`, VERSION 0x53525301, board-measured 95.36 ms at 125 MHz, 70.52 ms with non-cacheable buffers)
is multiplier-bound: 160 lanes x 16 cycles per pixel = 2,560 = the network's MACs per pixel, so its lanes are 100 % busy while
computing. A faster frame needs more lanes. v2 doubles the lanes and halves the cycles per pixel.

## What changes (and what does not)

Same network (R3q weights + anchor), same four stages, same line buffers, FIFOs, anchor FIFO, output banks, AXI top and registers.
Only `pipe_stage.v` is generalised with two parameters:

| Parameter | Meaning |
|---|---|
| `NS` | slots (cycles) per output pixel: 16 = original design (unchanged behaviour and cycle counts), 8 = v2 |
| `NDSP` | lanes `0..NDSP-1` use `pipe_mul` (DSP48), the rest `pipe_mul_lut` (`use_dsp = "no"`, same function and latency) |

With `P = 16 / NS` channels per slot:

| Stage | Mode | Lanes NS=16 -> NS=8 | Trees | Requantizers | Slot s computes |
|---|---|---|---|---|---|
| L1 conv3x3 3->16 | 0 output-serial | 27 -> 54 | P | P | output channels s*P+r |
| L2 dw3x3 16 | 1 output-serial depthwise | 9 -> 18 | P | P | channels s*P+r |
| L3 conv1x1 16->16 | 0 output-serial | 16 -> 32 | P | P | output channels s*P+r |
| L4 conv3x3 16->12 | 2 input-serial | 108 -> 216 | 12 (18 terms each) | ceil(12/NS) = 2 | input channels s*P+q into 12 accumulators, then 12 results requantized 2 per cycle (6 cycles <= 8) |

Total 320 lanes, 8 requantizers (16 DSP). DSP budget: 220 - 16 requantizer - 2 core = 202 lanes on DSP: L1-L3 all
(104), L4 `NDSP4 = 98`, so 118 L4 lanes are LUT multipliers (`sr_pipe_core.v` default for NS = 8).

Weight ROMs: `export_pipe.py` writes `wpipe8_L1..4.mem` (8 lines, lane layout in the file header) next to the unchanged
16-slot `wpipe_L1..4.mem`. The core selects the file by `NS`.

VERSION: 0x53526301 (driver family 0x535263xx; the pipe and tiled drivers refuse it, and this tree's driver refuses them).

## Verification so far

* Every stage at NS = 8: random weights (distinct M per channel, non-square frames) with stalls, slow consumer and reset
  aborts; network weights against each layer's golden output. L4 runs with NDSP = 50 so DSP and LUT lanes are both exercised.
* Accelerator top at NS = 8: whole frames via AXI-Lite + AXI-Stream, every stage's output and every output beat against
  `integer_reference.upscale()`.
* NS = 16 regression: the same tests, plus the top cycle counts must equal branch `pipe` exactly (p13x7 3,241, pramp 4,433,
  preal2 22,089 cycles: they do).
* First simulated speed-up: preal2 (37x29) 22,089 -> 11,236 cycles (1.97x).
* `run_tests.sh quick`: 69/69 passed (2026-11-10).
* **960x540 frame in xsim: bit-exact, 4,203,124 cycles** (branch `pipe` 8,398,481: 2.00x; *model* 4.20 M). At 125 MHz that is
  33.6 ms of compute; with the board-measured overheads *predicted* 61.8 ms cached (16.2 fps) / 37.0 ms non-cacheable (27.1 fps).

## Status of the to-do list

1. Mutation test: done, 41 mutants, 39 caught, 2 equivalent, 0 survived.
2. 960x540 frame in xsim: done (above).
3. Netlist simulation 4/4 PASS; Vivado build at 125 MHz met (3 builds: two timing fixes, see `results/utilization/m6_system_pipe2.md`).
4. Board programs built against a platform from the v2 XSA (t1, t2, t3_20f, t5, + non-cacheable t2/t3); board checklist entry: to do.

Remaining risk: only the board. Timing margin +0.231 ns at 125 MHz (the `pipe` build had +0.267 ns and ran fine on the board).
