# Next compute architecture: whole-frame layer pipeline (design doc)

Status: chosen 2026-10-26, implemented and verified on the PC 2026-10-27 in the sandbox branch `pipe` (worktree `~/Desktop/venkat/sandbox_pipe`):
960x540 frame bit-exact in simulation (8,398,481 cycles), routed at 125 MHz (WNS +0.267 ns), 170 DSP, 27 BRAM, 9,888 LUT (`results/utilization/m6_system_pipe.md`
in that branch). **Not on the board.**
Main's deployed design (four folded engines over 64x64 tiles, `hardware/` on main) is unchanged.

## 1. Choice and why

Two candidates were compared in the cycle model (`software/analysis/cycle_model.py` Part 5, report `docs/paper/cycle_model.md`).
Every number below is a **model prediction**:

| | (i) one shared engine, all DSPs | (ii) layer pipeline with line buffers |
|---|---|---|
| fps at 100 / 125 MHz | 4.0 / 4.7 with today's tile I/O, 6.5 / 7.4 with fully overlapped I/O | **11.0 / 13.6** |
| DSP | 208 | 168 |
| BRAM36 | ~70 + banking | ~27 |
| LUT (accelerator) | ~4-6k | ~6-8k |
| Risk | high (operand mux on the fmax path, multi-pixel reads, tiles stay) | medium (new: line buffers, flow control, raster output buffer) |

**Choice: (ii).** It is ~2x faster than the best case of (i), with fewer DSPs and fewer BRAMs, and it removes three costs of
the tiled design at once:
* the 17 % halo recomputation, because there are no tiles;
* the ARM tile copy (26.4 ms per frame measured today), because the DMA writes the 1920x1080 frame in place;
* the 4x engine idle time, because all four layers run at once.

Each layer stage has one fixed operand pattern, so no MAC input gets a per-layer mux.

## 2. Structure

```
DMA MM2S -> unpack 32b->24b px -> [L1 stage] -> FIFO -> [L2 stage] -> FIFO -> [L3 stage] -> FIFO -> [L4 stage] -> output banks -> pack 24b->32b -> DMA S2MM
                         \-> anchor FIFO (interior input pixels, 4096 x 24 b) ---------------------------> L4 requantizer `add`
```

* Input: the replicate-padded LR frame (W+6) x (H+6) x 3 bytes in raster order (the ARM pads, as today). The last 32-bit beat
  may carry 1-3 unused bytes. Output: the 2W x 2H x 3 HR frame in raster order, exactly the bytes of `integer_reference.upscale`.
* Frame size is set at run time (FRAME_W, FRAME_H registers); W <= MAXW - 6 = 1018 (line-buffer depth 1024), H < 65536.
* Every stage needs **16 cycles per output pixel** (the slot count is 16 for every layer):

| Stage | Layer | Mapping | Lanes (DSP) | Per slot s = 0..15 |
|---|---|---|---|---|
| L1 | conv3x3 3->16 | output-serial | 27 | output channel s = bias + sum over 27 taps x channels |
| L2 | depthwise3x3 16 | output-serial, depthwise | 9 | channel s = bias + sum over 9 taps of channel s |
| L3 | conv1x1 16->16 | output-serial | 16 | output channel s = bias + sum over 16 input channels |
| L4 | conv3x3 16->12 (+anchor) | input-serial | 108 = 12 x 9 | input channel s: 12 accumulators += sum over 9 taps |

  Plus one requantizer (2 DSP) per stage: 160 + 8 = 168 DSP; as built **170** (2 more for the frame-size products in the core).
* A stage = line buffer (2 rows in one simple dual-port RAM, K=3 only) + 3x3 window shift register + a window snapshot (so the
  next window loads while the current one computes) + MAC lanes (DSP) + pipelined adder trees + accumulator + `requant.v` (unchanged,
  `ADD_EN` for the anchor) + output word assembly. Weights per slot come from a 16-entry ROM (`wpipe_Ln.mem`, generated from the
  canonical `weights_Ln.mem`).
* Flow control is per pixel, never inside a pixel. A stage starts a pixel (snapshot) only when a window is ready AND the consumer
  has reserved room for the result: the FIFOs count reservations, and the L4 output bank must be free at the start of a row.
  Once started, a pixel runs its 16 slots without stalls. The input side stops accepting when a produced window is not yet taken.
* Output: two banks of W x 96 bits (one LR row of L4 results each). A reader turns each bank into HR rows 2y and 2y+1 (k = 4c+2dy+dx)
  and a 24->32-bit packer sends them to the DMA. One bank fills while the other drains. Draining takes ~6W cycles per LR row,
  filling takes 16W.
* Anchor: the L4 output (x,y) adds input pixel (x+3, y+3). Interior input pixels go into a FIFO in raster order and L4 pops one per
  output pixel. Bound: when L4 is at (x,y), the input can be at most ~3 rows + ~30 pixels ahead of the anchor it needs
  (the line buffers hold 2 rows per 3x3 layer, the FIFOs 8 pixels each). So the 4096-entry FIFO cannot fill for W <= 1018: measured highest
  occupancy 3,066 at W = 1018, 2,892 at W = 960. The simulation checks overflow and underflow on every run. **Bug found 2026-10-26:** the first
  version computed the occupancy in 32 bits and reported full after the pointer wrap (8,192 pushes); see `docs/STATUS.md` and
  `docs/PIPELINE_COUNTER_AUDIT.md` in the branch.

## 3. Registers (top module keeps the name `sr_accel_top`, so the block design is unchanged)

| Offset | Name | Access | Meaning |
|---|---|---|---|
| 0x00 | CONTROL | W | bit0 start (ignored while busy), bit1 soft reset |
| 0x04 | STATUS | R | bit0 busy, bit1 done (sticky), bit2 error (sticky) |
| 0x08 | FRAME_W | RW | LR frame width W (1..1018) |
| 0x0C | CYCLES | R | cycles from start to the last output beat of the frame |
| 0x10 | ERROR_CODE | R | 1 TLAST early, 2 TLAST missing, 3 TKEEP != F, 4 frame size out of range (start refused) |
| 0x14 | VERSION | R | 0x53525301 (pipeline, R3q weights + anchor, 125 MHz) |
| 0x18 | FRAME_H | RW | LR frame height H (1..4096) |
| 0x1C | MAX_W | R | 1018 |
| 0x20 / 0x24 | DBG_IN_BEATS / DBG_OUT_BEATS | R | beats accepted / sent since the last start |

## 4. Verification plan (same standard as before)

* Golden reference: `integer_reference.upscale(net, lr)` on whole frames, and `forward_layers()` for each stage's output stream.
* Unit tests: stage-level testbench per mode with random weights, distinct M per channel, non-square random frames, and every stage
  output compared value by value. The FIFO, the packer/unpacker, and the anchor bound are checked by assertions.
* Whole-core tests: several frame sizes (1x1 up to 64x48 real crops), random input and output stalls, back-to-back frames of
  different sizes, reset/abort sweeps, error codes, and a 960x540 frame (full suite).
* Seam test equivalent: there are no tiles. The whole-frame result must equal `upscale()` on every pixel, including the borders
  (replicate padding), on odd sizes.
* Mutation study on the new RTL, netlist simulation of the synthesized core, and full-system place and route at 125 MHz.

## 5. Not done on purpose (owner decision 2026-10-26)

Clock enables on idle engines (no idle engines here), runtime weight loading, DSP packing of two INT8 multiplies.
