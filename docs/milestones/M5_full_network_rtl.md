# M5 — Full Network in RTL: Layer Sequencer, Pixel Shuffle and Tiles

**Time:** 2–3 weeks | **Where:** PC simulation, then Vivado | **Depends on:** M4 (verified conv engine)

---

## 1. Why this milestone exists

M4 gave you a verified single-layer engine. Now you:
1. Run **all four layers** back to back using that engine.
2. Rearrange 12 channels into a 2× bigger RGB image (**pixel shuffle**).
3. Handle the **image in tiles** (the whole image does not fit in BRAM) without visible seams.

At the end you have a block that takes **one tile in** and gives **one upscaled tile out**, matching the golden model exactly.

---

## 2. Concepts

### Why tiles?
A 960×540 image with 16 channels per pixel is ~8 MB of intermediate data. The chip has ~630 KB of BRAM. So we process the
image in small pieces (**tiles**), e.g. 64×64 pixels, and keep only the tile's data on chip.

### The halo (the most important idea in this milestone)
A 3×3 convolution needs the neighbours of each pixel. At the edge of a tile, the neighbours belong to *another* tile.
So each tile is loaded with extra border pixels from its neighbours — the **halo** — then those extra pixels are discarded.

Our network has **three** 3×3 layers (L1 conv, L2 depthwise, L4 conv). The 1×1 pointwise layer needs no neighbours.
Each 3×3 layer eats 1 pixel from each side, so the halo is **3 pixels**.

Use **valid convolutions** (no padding inside the tile; each 3×3 layer shrinks the tile by 2):

```
input tile with halo   70×70  (64 + 3 + 3)
after L1 (3×3 valid)   68×68
after L2 (3×3 valid)   66×66
after L3 (1×1)         66×66
after L4 (3×3 valid)   64×64   ← exactly the core tile, 12 channels
pixel shuffle ×2      128×128 RGB
```
No cropping logic is needed: the shrinking does it for you.

### Image borders
At the true edge of the whole image there is no neighbouring tile. Pad the **input image** by 3 pixels (replicate the edge
pixels — the project choice, decided in M2) before tiling. Then every tile, including border tiles, is a full 70×70 window.

> **Decision (already applied in M2):** the network is trained with valid convolutions and the golden integer model (M3) must be
> defined the same way: "replicate-pad the whole input by 3, then run valid convolutions". Replicate padding is the project
> choice (verified in M2: tiled output == whole-image output up to float rounding, checked on a real 960x540 image with 135 tiles; edge band loses only ~0.15 dB vs the interior).

### The key correctness test
> **Tiled output must be identical to whole-image output.**
If tile seams exist, this test fails. It is a perfect automatic check.

### Pixel shuffle (×2), exactly
Network output channel index `k = 4·c + 2·dy + dx` (c = colour 0..2, dy,dx ∈ {0,1}) at low-res pixel (y, x) becomes
high-res pixel `(2y + dy, 2x + dx)`, colour `c`. (This is PyTorch's `PixelShuffle` convention — check yours.)
In hardware it is only an **address calculation** when writing out; no multipliers.

---

## 3. Design

### Top-level block: `sr_tile_core`

```
 pixel stream in (70×70×3 bytes)
        │
   ┌────▼─────┐   ┌──────────────────────────────────────────┐
   │ input    │   │                                          │
   │ loader   ├──►│ BRAM A ─► conv engine ─► BRAM B ─► ...   │
   └──────────┘   │        (layer sequencer: L1→L2→L3→L4)    │
                  └───────────────────┬──────────────────────┘
                                      │ 64×64×12 results
                              ┌───────▼────────┐
                              │ pixel shuffle  │ addressing only
                              │ + output packer│
                              └───────┬────────┘
                                      ▼
                    pixel stream out (128×128×3 bytes)
```

### Layer sequencer
A small FSM with a table of per-layer settings:

| Layer | C_in | C_out | Kernel | Depthwise | Input size | Output size | Reads | Writes |
|---|---|---|---|---|---|---|---|---|
| L1 | 3 | 16 | 3 | no | 70 | 68 | A | B |
| L2 | 16 | 16 | 3 | yes | 68 | 66 | B | A |
| L3 | 16 | 16 | 1 | no | 66 | 66 | A | B |
| L4 | 16 | 12 | 3 | no | 66 | 64 | B | out |

The sequencer sets the engine's parameters, pulses `start`, waits for `done`, swaps the buffers, and goes to the next layer.
Weights for each layer come from a ROM region selected by the layer number.

### Output ordering
Decide what order the output bytes leave in. Simplest for the ARM: **row-major RGB of the 128×128 tile**
(`R,G,B` per pixel, left to right, top to bottom). The shuffle writes into a small output BRAM at the shuffled address, and
the packer reads it out in raster order. (64×64×12 bytes = 48 KB; 128×128×3 = 48 KB. Same size.)

---

## 4. Step-by-step

### Step 1 — Chain two layers
Run L1 then L2 on a small tile (e.g. 12×12 input) and compare the intermediate and final result with Python.
Then add L3, then L4. **Compare after every layer** — dump each layer's BRAM and check against the integer model's intermediates.

### Step 2 — Add pixel shuffle and the output packer
Test with the golden 64×64 core tile: output must equal `pixel_shuffle(L4_out)` from Python exactly.

### Step 3 — Full tile test (70×70 → 128×128)
Take real image tiles from the golden vectors (M3) and compare.

### Step 4 — The seam test (in Python + simulation)
1. Pick a 128×128 image area. Run it **whole** through the Python integer model.
2. Cut it into tiles with halo, run each tile through the **RTL simulation**, assemble the pieces.
3. Compare: assembled result == whole-image result, **bit-exact**.

Simulation of a 70×70 tile at ~196 cycles per pixel takes ~1 M clock cycles. Use Verilator or reduce the tile size for quick
tests (make `TILE` a parameter), and only run the full size occasionally.

### Step 5 — Synthesize
Check: DSP, LUT, BRAM, timing at 100 MHz. Remove or fix any timing violations (long combinational paths in requant are typical).

---

## 4b. Results achieved (2026-10-04)

What was built:

| File | Purpose |
|---|---|
| `hardware/rtl/sr_core/sr_tile_core.v` | The tile core: byte-stream loader, 4 conv engines + sequencer, 5 activation RAMs, pixel shuffle + packer, byte-stream output |
| `hardware/rtl/common/tile_ram_split.v` | Activation RAM split into a power-of-two part and a remainder (block-RAM friendly) |
| `hardware/verification/tb/tb_sr_tile.v`, `tb_tile_ram_split.v` | Self-checking testbenches |
| `software/ai/quantization/seam_test.py` | Generates the seam test (real image region, tiles with halo, whole-image result) and assembles/compares the RTL result |
| `hardware/vivado/scripts/synth_sr_tile_core.tcl` | Synthesis / place and route / post-synthesis netlist of the whole core |

Design decisions:
* **One activation RAM per layer boundary** (ram0 24 bit, ram1-3 128 bit, ram4 96 bit), no ping-pong: simplest to verify. Cost: 70 of 140 BRAM tiles for
  the whole core. Ping-pong would save about one buffer (about 16 tiles, an ESTIMATE from the measured 16.5-tile buffer) but needs read/write muxes; not worth it now.
* **Byte-wide streams** (valid/ready, `out_last`), one byte per transfer, so M6 can attach a width converter/DMA without changing the core.
  The load (14,700 cycles) and the output (about 57,000 cycles) are not overlapped with the compute: 926,197 cycles per tile in total, 7.8 % of it I/O.
* **`tile_ram_split`**: Vivado rounds the cascade depth of a block-RAM array up to a power of two, so a 4624x128-bit buffer cost 32 RAMB36 (M4 finding).
  Splitting the address range into a 4096-deep part and the rest maps it to 18.5 tiles. Verified by synthesis, 3 sizes tested incl. the boundary.
* The core's default SHIFT parameters equal the exported ones (a testbench check); `WDIR` is the directory of the exported .mem files.

Verification (`hardware/verification/run_tests.sh quick|full`, `run_postsynth.sh`):
* **Layer by layer inside the chained core:** after each tile the contents of ram1..ram4 are compared with `data/golden/<tile>_L1..L4.hex`
  (every byte), and the output stream with `<tile>_out.hex` (every byte, byte count, `out_last` position). All 9 real-size golden tiles
  (zeros, full255, noise, single pixel, ramp, 3 real tiles, border tile) pass; two of them again with random stalls on BOTH streams.
* **Robustness (small tiles, every run):** the layer buffers are poisoned with 0xA5 before each tile; the same tile is re-run; a different tile follows
  without reset (no stale data); a sweep of 60 ONE-cycle-reset aborts at moments spread over load, each layer and output, after each of which the
  core must stay quiet (no busy/valid/ready/done) for 300 cycles; then a fresh tile must be exact again.
* **Seam test:** a real LR region whose size is not a multiple of the core is run whole through the integer model and, cut into tiles with a 3 px halo
  (replicated at the image border), tile by tile through the RTL; the assembled RTL output equals the whole-image result bit for bit:
  20 tiles at HC=8 (74x58 output) in `quick`, 4 tiles at HC=64 (200x180 output) in `full`.
* **Post-synthesis simulation:** the synthesized netlist of the core (HC=6) passes the stream-level test with the identical cycle count.
* **Breakage checks:** 21 deliberate breakages of the core and the split RAM (byte order, write phase, load length, `in_ready`, layer launch, shuffle
  order, row base, re-fetch, `out_last`, row count, address, output valid, buffer wiring, reset, counters, split-RAM select/boundary/offset) are all
  caught. One breakage (wrong *default* SHIFT parameter) first SURVIVED because the testbench overrides the parameters; a default-parameter check
  was added and now catches it. Checks that could pass vacuously were closed (missing/short golden files fail), and the seam checker was shown to
  catch a single flipped byte.
* Re-audit fix (2026-10-04): `cycles` is now cleared by reset and `out_last` is only high together with `out_valid` (both were X/undefined while idle);
  the testbench now fails on any X in the control/status outputs after reset (checked to catch the old behaviour: 10,455 violations).
* Test totals: `quick` 29 runs (about 2 min), `full` 73 runs (about 20 min); the M1-M4 suites still pass.

Synthesis and implementation (`results/utilization/m5_tile_core.md`): whole core 1,900 LUT, 3,337 FF, 68 DSP, 70 BRAM tiles after place and route;
routed setup slack at 100 MHz only **+0.234 ns** (critical path: an engine's requantizer feed (res mux -> DSP)), hold +0.081 ns, no failing endpoints (out-of-context).
Cycles per tile 926,197 (simulated) = about 1.25 s per 960x540 frame at 100 MHz, compute plus byte-wide I/O, no DMA/ARM (not a board measurement).

## 5. Output of this milestone

1. `sr_tile_core.v` and its sub-modules (table above); the sequencer is inside `sr_tile_core.v`.
2. Testbench logs: per-layer buffer PASS, full-tile PASS, seam-test PASS (`run_tests.sh`).
3. Synthesis and place-and-route reports: `results/utilization/m5_core_*`.
4. Cycle count for one tile (926,197) and the predicted frame time (about 1.25 s at 100 MHz).

For 960x540 padded to 960x576 there are 15 x 9 = 135 tiles.

## 6. Exit checklist

- [x] Every intermediate layer matches the integer model bit-exactly on a full tile (ram1..ram4 compared byte for byte on all 9 real-size golden tiles).
- [x] Pixel shuffle output matches Python exactly (output stream compared with `<tile>_out.hex`, every byte).
- [x] Seam test passes: tiled == whole-image (20 tiles at HC=8, 4 tiles at HC=64, bit-exact).
- [x] Border tiles work (image padded by 3): the `real_corner` tile and the border tiles of both seam tests.
- [x] Core synthesizes and meets timing at the target clock (routed WNS +0.234 ns at 100 MHz, out-of-context); resource numbers recorded.

## 7. Common problems

| Symptom | Cause |
|---|---|
| Visible seams at 64-pixel lines | Halo too small (must be 3), or tile origin off by one |
| Whole tile slightly wrong | One layer's M/SHIFT or weights mismatched with Python — check layer by layer |
| Colours scrambled after shuffle | Channel order `4c+2dy+dx` vs a different convention |
| Last row/column missing | Valid-conv size arithmetic off by one |
| Simulation takes forever | Use smaller `TILE` in most tests |
