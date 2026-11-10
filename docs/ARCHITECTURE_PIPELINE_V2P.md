# Pipeline v2 packed: two multiplies per DSP48 (branch `pipe2p`)

Status (2026-11-10): BOARD-MEASURED: same frame times as pipe2 (36.96 ms non-cacheable, 61.64 ms cached), 119/119 byte-exact; full regression 124/124.
Base: pipeline v2 (`docs/ARCHITECTURE_PIPELINE_V2.md`: 8 cycles per LR pixel). Speed unchanged; only the multipliers change.

## Idea
In v2 two adder trees often multiply the SAME activation by different weights (L1 and L3 at NS = 8: trees r = 0, 1 of one slot;
L4: the 12 output-channel trees all use the same 18 window values). The DSP48E1 multiplier is 25 x 18 bits, our product is 8 x 8,
and the products are summed OUTSIDE the DSP (adder trees, no accumulation inside), so two products fit in one DSP:

    A = (w2 << 17) + w1   (25-bit signed),  B = a (uint8 as 9-bit signed),  P = A * B,  |P| < 2^32
    a * w1 = signed P[16:0]                  (lo, exact)
    a * w2 = signed P[33:17] + P[16]         (hi_raw + borrow b)

Checked for all 16,646,400 input combinations (a 0..255, w1, w2 -127..127). The borrow bits of a tree are counted and added as ONE extra
adder-tree term (`bor` / `bc` in `pipe_stage.v`), so there is no per-pair adder. The weight add (w2 << 17) + w1 comes from the ROM and
folds into the ROM logic.

## RTL
* `hardware/rtl/pipe/pipe_mul2.v`: the packed multiplier (latency 2, like `pipe_mul`).
* `pipe_stage.v` parameter `PACK`: packing where two trees share activations (MODE 2; MODE 0 with 2 trees). MODE 1 (depthwise L2) is never
  packed: its trees read different channels. PACK = 0 gives exactly the `pipe2` hardware (tested: same cycle counts).
* `sr_pipe_core.v` / `sr_accel_top.v` parameter `PACK` (default 1), VERSION 0x53527301.

## Result (Vivado, 125 MHz; `results/utilization/m6_system_pipe2p.md`)
| | pipe2 | pipe2p |
|---|---|---|
| LUT | 20,651 | **13,323 (-35 %)** |
| FF | 21,612 | 19,688 |
| DSP | 220 | **190** |
| LUT multipliers | 118 | 0 |
| WNS / WHS | +0.231 / +0.019 ns | **+0.450** / +0.007 ns |
| Power (Vivado vectorless, estimate) | 2.90 W | 2.51 W |
| 960x540 cycles (xsim) | 4,203,124 | 4,203,125 |

DSP count 190 vs the 187 estimated (169 multiplier + 16 requantizer + 2 core): per stage s1 32, s2 23, s3 21, s4 112 (estimate 29 / 22 / 20 / 112);
the 3 extra are in s1-s3, not investigated (likely the borrow-count/adder mapping or requantizer splitting).

## Verification
quick 99/99 (stages packed and unpacked at NS = 8 and 16, tops NS = 8 packed / unpacked / NS = 16 packed and unpacked); 960x540 bit-exact in
xsim; netlist 4/4 (190 DSP48E1); mutation 48: 45 caught, 3 equivalent (V4, C4, P3 = p[33] always equals p[32]), 0 survived.
