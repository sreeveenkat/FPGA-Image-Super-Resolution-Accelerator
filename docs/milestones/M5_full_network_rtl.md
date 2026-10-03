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

## 5. Output of this milestone

1. `sr_tile_core.v` and sub-modules (sequencer, pixel shuffle, packers).
2. Testbench logs: per-layer PASS, full-tile PASS, seam-test PASS.
3. Synthesis report for the whole core.
4. Cycle count for one tile (and from it, the predicted frame time: `tiles × cycles_per_tile / clock`).

For 960×540 padded to 960×576 there are 15 × 9 = 135 tiles.

## 6. Exit checklist

- [ ] Every intermediate layer matches the integer model bit-exactly on a full tile.
- [ ] Pixel shuffle output matches Python exactly.
- [ ] Seam test passes: tiled == whole-image.
- [ ] Border tiles work (image padded by 3).
- [ ] Core synthesizes and meets timing at the target clock; resource numbers recorded.

## 7. Common problems

| Symptom | Cause |
|---|---|
| Visible seams at 64-pixel lines | Halo too small (must be 3), or tile origin off by one |
| Whole tile slightly wrong | One layer's M/SHIFT or weights mismatched with Python — check layer by layer |
| Colours scrambled after shuffle | Channel order `4c+2dy+dx` vs a different convention |
| Last row/column missing | Valid-conv size arithmetic off by one |
| Simulation takes forever | Use smaller `TILE` in most tests |
