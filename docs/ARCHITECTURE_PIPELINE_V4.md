# Pipeline v4 (`pipe4`): 6 cycles per LR pixel

Branch `pipe4` (worktree `~/Desktop/venkat/sandbox_pipe4`), started 2026-11-18 from `pipe3` (commit 0b25e58 + pipe3's uncommitted files). VERSION **0x53529301**.
Same network, weights, output (fnv 0x45dd4e2d), PL padding (CONFIG.PAD_EN) and 142.857 MHz clock as `pipe3`. Every stage now takes **6 cycles per pixel instead of 8**
(`docs/paper/cycle_model.md` Part 7 in main predicted 3.15 M cycles per 960x540 frame; built: 3,156,214).

## What changed (all in `pipe_stage.v` unless noted; NS = 16 and NS = 8 keep their exact cycle counts, checked in every regression)

| Item | Change |
|---|---|
| channels per slot | P = ceil(NCH / NS), NCH = C_OUT (MODE 0/1) or C_IN (MODE 2). NS = 6: L1, L2, L3 get P = 3 (slots walk 18 channels; channels 16, 17 have zero weights and no requantizer result); the MODE 1 window read of a non-existent channel returns 0 |
| L4 | runs in **MODE 0 (output-serial) with P = 2**: 6 slots x 2 = its 12 output channels, 288 lanes (2 trees x 144 terms). The anchor add moved into the MODE 0 requantizer (`ADD_EN`), one anchor pop per pixel when slot 0 reaches the adder (`sr_pipe_core.v`: `.MODE((NS == 6) ? 0 : 2)`) |
| packing | also for an odd tree count (L1/L3 have 3 trees: trees 0+1 packed, tree 2 alone) |
| DSP budget | `NDSP2`: packed pairs of L4 with lane index < 76 on DSP48s, the other 68 pairs on two LUT multipliers each (136 LUT multipliers). 213 of 220 DSPs used |
| borrow count | width $clog2(NT + 1) instead of 6 bits. **Bug found by the random-weight stage test:** with 144 terms per tree the count of packed-product borrows passed 63 and wrapped (1 LSB errors); the network weights stayed below 63 by chance |
| multiplier latency | `MLAT` (default 2). L4 at NS = 6 uses 3: LUT multipliers get two cycles (two 8 x 4 half products, then their sum), DSP multipliers their P register; the stage pipeline follows (`D = MLAT + tree levels`). +1 cycle per frame |
| output word | built only from requantizers with a real channel; sent when channel C_OUT - 1 arrives |
| `anchor_fifo.v` | occupancy kept in its own register (+push - pop) instead of `wp - rp` (timing) |
| `pipe_stage.v` | `in_w - 1`, `in_h - 1` registered (timing) |
| `sr_accel_top.v` | NS default 6, VERSION 0x53529301, frame-size check registered (timing) |
| `export_pipe.py` | 6-slot ROM layout `wpipe6_L*.mem` (L4 in the MODE 0 layout); the 16- and 8-slot files are unchanged |

## Timing at 142.857 MHz (6 builds; all with the AXI DMA memory side 64 bit as in pipe3)

| Build | Change | WNS / WHS (ns) | Failing | Worst path |
|---|---|---|---|---|
| a | first RTL | -0.415 / +0.014 | 326 | anchor FIFO `wp - rp` -> wp enable; L4 LUT multipliers (8-9 levels in one cycle) |
| b | FIFO occupancy register, MLAT = 3 | -0.303 / +0.050 | 22 | AXI DMA S2MM realigner; `in_w` -> L1 column reset |
| c | b + `in_w - 1` registered, strategy Performance_ExplorePostRoutePhysOpt | -0.244 / +0.052 | 9 | AXI DMA realigner, GP0 interconnect |
| d | same RTL, default strategy | -0.178 / +0.051 | 13 | FRAME_H -> size check -> frame-start reset |
| e | + size check registered, ExplorePostRoutePhysOpt | -0.264 / +0.05 | 19 | AXI DMA |
| **f** | same RTL, strategy **Performance_ExtraTimingOpt** | **+0.038 / +0.004** | **0** | core `fw` -> output column reset |

Build f is the design (`~/Desktop/venkat/pipe4_artifacts/design_1_wrapper_pipe4.bit`, md5 608dbad6...; reports `reports_pipe4/`, copies in
`results/utilization/m6_system_pipe4_*.txt`). Margins are thin (setup +0.038, hold +0.004 ns) but met; `build_m6_system.tcl` needs `SR_DMA_MM64=1
SR_IMPL_STRATEGY=Performance_ExtraTimingOpt` and FCLK0 142.857 to reproduce it. XSA ps7_init identical to pipe3 (md5 dd869514..., 0xF8000170 = 0x00100700).

Resources (routed): **24,783 LUT (47 %) / 30,580 FF / 31.5 BRAM / 213 DSP (97 %)**; per stage LUT/DSP: s1 2,436/60, s2 1,575/33, s3 1,521/38, s4 15,227/80.
Model (Part 7) predicted 21,845 LUT: the 3-cycle LUT multipliers and the wider trees cost more. Vivado vectorless power 3.06 W (estimate, not measured).
12/12 weight files read, NS = 6, MLAT = 3, PACK = 1, 0 x Synth 8-311, no critical warnings except the ZedBoard DDR DQS-skew ones (PSU-1..4).

## Verification (PC)

* 960x540 with PL padding: bit-exact in xsim, every stage output exact, **3,156,214 cycles** (pipe3 4,205,054).
* netlist simulation 7/7 (213 DSP48E1, 12/12 weight files), incl. PL padding runs.
* quick regression: 137 of 138 passed on the final RTL; the one failure was `test_regs.py` expecting the old unregistered `wire size_ok` text (test fixed, no
  RTL change). **Full regression 177/177, 0 failed** (incl. mutation 79: 74 caught, 5 equivalent, 0 survived); details in `results/utilization/m6_system_pipe4.md`.

## Board

See `results/board/2026-11-18/SUMMARY.md` in main.
