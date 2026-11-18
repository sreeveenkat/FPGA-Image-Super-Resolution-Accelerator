# Pipeline v3 (`pipe3`): PL padding + 142.86 MHz

Branch `pipe3` (worktree `~/Desktop/venkat/sandbox_pipe3`), started 2026-11-18 from `pipe2p` (commit 0b25e58). VERSION **0x53528301**.
Same network, weights, datapath and output as `pipe2p` (pipeline v2 packed, 8 cycles per LR pixel, 190 DSP). **Not run on a board yet.**

## Why

On the board, `pipe2p` with non-cacheable buffers takes 36.95 ms per 960x540 frame at 125 MHz (`results/board/2026-11-10/SUMMARY.md` in main):
pad 3.32 ms on the ARM + DMA/compute 33.63 ms (= 4,203,125 cycles / 125 MHz). Two things were left to gain without touching the datapath
(`docs/paper/cycle_model.md` Part 7 in main):

* **A. Padding in the PL.** The ARM no longer pads; the DMA sends the raw W x H frame and the core does the 3-pixel replicate padding.
* **B. A faster clock.** The PL clock is the 1000 MHz IO PLL divided by an integer: /8 = 125 MHz (`pipe2p`), **/7 = 142.857 MHz** (this design).

Predicted: 29.4 ms per frame = 34 fps with non-cacheable buffers (model, not measured).

## What changed

| File | Change |
|---|---|
| `hardware/rtl/pipe/sr_pipe_core.v` | new input `pad_en`; PL padding front end (below); three registered flags for timing (`pix_left`, `xin`/`yin`, `u_left`) |
| `hardware/rtl/top/sr_accel_top.v` | register **CONFIG 0x28** (bit0 PAD_EN, RW, reset 0, sampled at start); VERSION 0x53528301; fixed `FREQ_HZ` removed from the clock interface attribute (the block design gives the clock) |
| `hardware/vivado/scripts/build_m6_system.tcl` | optional 3rd argument FCLK0 MHz (default 125); env `SR_DMA_MM64=1` (AXI DMA memory side 64 bit); env `SR_IMPL_STRATEGY` |
| `software/board/` | `sr_regs.h` (CONFIG, raw-frame macros, VERSION); `sr_run_frame_raw()`; frames sent raw by default (`-DSR_ARM_PAD` = the old way); `-DSR_NC_IN` (raw input region non-cacheable) |
| tests | `tb_sr_pipe_top.v +PAD=0/1/2`; raw vectors `<frame>_raw.hex` (`gen_pipe_vectors.py`); `run_tests.sh`, `run_postsynth.sh`, `mutate_pipe.py` (16 new mutants) |

### PL padding (PAD_EN = 1)

* The unpacker (32-bit beats -> 24-bit pixels) is unchanged; with PAD_EN its pixels go into a **2-row buffer** (2 x 1024 x 24 bit, 1.5 BRAM36): raw row r goes into
  half r % 2.
* A reader produces the padded (W+6) x (H+6) stream for L1: padded row py reads raw row clamp(py - 3, 0, H - 1), padded column px reads raw column clamp(px - 3, 0, W - 1).
  It reads a raw row only when it is complete; the writer writes row r only when the reader has moved on to row r - 1 or later. Both rules use one 2-bit counter
  `ahead` = rows written - rows being read (0..2).
* RAM reads take one cycle; a 2-entry queue sits in front of L1.
* L1 therefore receives exactly the stream that PAD_EN = 0 would receive, so every stage output and the final image are identical (checked stage by stage).
* PAD_EN = 0 is the old path, untouched: cycle counts equal `pipe2p` exactly (p13x7 1,717, pramp 2,325, preal2 11,237; the 960x540 frame 4,203,125 in `pipe2p`).
* Cost of PAD_EN = 1 in cycles: 960x540 frame 4,205,054 vs 4,203,125 (+1,929 cycles = 0.014 ms, the first raw row has to arrive before the first padded row).

### Timing at 142.86 MHz (4 builds, all `build_m6_system.tcl`, 2 or 1 jobs)

| Build | Change | WNS / WHS (ns) | Failing endpoints | Worst path |
|---|---|---|---|---|
| a | first RTL | -0.770 / +0.011 | 160 | `rrow` -> 16-bit compare `rrow + 1 >= wrow` -> unpacker -> `ub` (new logic) |
| b | `ahead` counter, registered `u_left` / `rd_left` | -0.244 / +0.006 | 28 | inside Xilinx IP: AXI DMA S2MM realigner, 32->64-bit upsizer of the HP0 interconnect |
| c | b + strategy `Performance_ExplorePostRoutePhysOpt` | 0.000 / +0.019 | 0 | AXI DMA (no margin) |
| **d** | b + **AXI DMA memory side 64 bit** (`SR_DMA_MM64=1`, no upsizers) | **+0.132 / +0.015** | **0** | AXI DMA S2MM realigner |

Build d is the design (`~/Desktop/venkat/pipe3_artifacts/design_1_wrapper_pipe3.bit`, md5 042aa316..., reports in `reports_pipe3/`).
FCLK0 in its XSA `ps7_init.tcl`: `0xF8000170` = 0x00100700 -> IO PLL, DIV0 = 7, DIV1 = 1 -> 142.857 MHz (ps7_init md5 dd869514...).
The 64-bit DMA memory side changes `xparameters.h` (MM2S/S2MM data width 0x40, MM2S burst 8) and the driver's alignment rule (buffers must be 8-byte aligned without DRE):
every DMA buffer is 64-byte aligned or 16 bytes into an aligned region (checked).

Resources (routed, build d): **13,334 LUT (25 %) / 19,938 FF / 29.5 BRAM / 190 DSP**; `pipe2p` 13,323 / 19,688 / 27 / 190. Vivado vectorless power 2.685 W
(`pipe2p` 2.51 W at 125 MHz; estimate, not measured). 12/12 weight files read, PACK = 1, NS = 8, 0 x Synth 8-311; the only critical warnings are the ZedBoard
DDR DQS-skew ones (PSU-1..4), present in every earlier build.

## Verification (PC only)

Full regression 135/135 (incl. mutation 66: 63 caught, 3 equivalent, 0 survived), 960x540 with PL padding bit-exact in xsim (4,205,054 cycles), netlist 7/7. Details: `results/utilization/m6_system_pipe3.md`.

## Predicted board numbers (model, NOT measured)

| Buffers | Frame time at 142.857 MHz | fps |
|---|---|---|
| non-cacheable in + out (`-DSR_NC_IN -DSR_NC_OUT`), PL padding | 29.4 ms (4,205,054 cycles; no pad, no cache maintenance) | 34.0 |
| same bitstream, ARM pads into the non-cacheable pad region (`-DSR_ARM_PAD -DSR_NC_PAD -DSR_NC_OUT`) | 32.7 ms (29.42 + 3.32) | 30.5 |
| cached (production ELF), PL padding | 51.7 ms (29.44 + cache maintenance ~22.3 ms measured on `pipe`) | 19.3 |

The two non-cacheable variants run on the same bitstream, so their difference is the gain of the PL padding alone; `pipe2p` at 125 MHz (36.95 ms) vs the ARM-pad
variant gives the clock gain alone.
