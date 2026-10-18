# Anchor (nearest-neighbour residual) - hardware cost estimate

**Status: ESTIMATE, nothing synthesized.** The software side is measured (`results/quality/image_quality_ladder.md`, `software/ai/quantization/test_anchor.py`).
No RTL has been changed. Numbers marked "est." come from reading `conv_engine.v`, `sr_tile_core.v` and `requant.v`, not from Vivado.

## What the anchor does
`out[c*4 + 2dy + dx] = clamp(L4_residual[k] + centre_input_pixel[c], 0, 255)` before the pixel shuffle: the three input channels (R, G, B) of the
input pixel at the output position are repeated into the 4 sub-pixel channels of each colour and added to the last layer's output.
The integer model (`integer_reference.py`) and the QAT simulation (`qat.py`) do exactly this and are bit-exact with each other.

## Measured software gain (INT8, integer model, 2 seeds, mean ± half-range; `image_quality_ladder.md`)
| | Set5 | Set14 | BSD100 | val42 |
|---|---|---|---|---|
| R2q rep + QAT (no RTL change) | 35.794 ± 0.043 | 31.845 ± 0.042 | 30.832 ± 0.039 | 33.878 ± 0.039 |
| R3q plain + anchor + QAT | 36.051 ± 0.146 | 32.048 ± 0.074 | 30.962 ± 0.049 | 34.116 ± 0.089 |
| gain R3q - R2q | +0.258 | +0.203 | +0.130 | +0.238 |

## What changes in the datapath
1. **Last layer output becomes signed.** L4 currently clamps to [0,255] (uint8). With the anchor the residual is signed: clamp to [-256, 255] (9-bit signed;
   `test_anchor.py` proves clamping to [-255,255] or no clamp gives the same final pixel). `requant.v` needs a signed-output clamp mode for L4 only
   (lower bound -256 instead of 0, one more output bit); the L4 engine's output word grows from 8 to 9 bits per channel (12 x 9 = 108 bits, was 96) **or** the
   residual is added inside the engine so that the stored word stays 8 bits (Option A below, recommended).
2. **Adder + final clamp**: 12 parallel or 1 shared (the requantizer is shared and produces one channel per cycle, so a single 10-bit adder + clamp to 0..255 suffices). est. ~20-40 LUT.
3. **Halo-aligned read of the centre input pixel.** The output pixel (x,y) of the core tile corresponds to input position (x+3, y+3) of the 70x70 padded tile
   (HALO = 3, valid convs). `ram0` (24-bit words, the loaded RGB tile) stays valid through L4 and the output phase (it is not overwritten), so the centre
   pixel can be read from it. A halo offset error would shift the image by up to 3 px: the alignment test and a halo-offset mutant (offset 2 instead of 3) in
   `test_anchor.py` catch this in software; the RTL needs the same test (a tile with a single bright pixel, and the existing seam test at HC=8 and HC=64).
   - **Option A (recommended): in the L4 engine's output stage.** The L4 engine already walks the output pixels in raster order; add a second read port or time-share
     `ram0`'s read port (L4 reads the L3 buffer, not ram0, during its run, so ram0's read port is free): address = (y+3)*70 + (x+3), a small counter
     est. ~30-50 LUT + ~20-30 FF. The stored ram4 word stays 96 bits (already clamped 0..255), the pixel-shuffle/packer is unchanged.
   - **Option B: in the packer after ram4.** ram4 would have to hold the signed residual (108 bits instead of 96) and the packer adds the centre pixel: more BRAM width, rejected.
4. **Colour selection**: output channel k = 4c + 2dy + dx adds input colour c (3:1 mux, 2 bits of the channel counter): est. ~10 LUT.
5. **Timing**: +1 or 2 pipeline stages (read address -> data -> add); L4 period is 144 cycles per pixel, so the add is hidden; +1-2 cycles per tile, no change in
   the per-tile cycle count in practice (est.).
6. **No quantization-scale alignment needed.** Input scale is 1/255 and the last layer's output scale is 1/255 (it is the pixel), so the residual and the input pixel are in
   the same units; no extra multiplier or shift.

## Cost summary (est.)
| | est. |
|---|---|
| LUT | ~80-120 |
| FF | ~60-70 |
| DSP | 0 |
| BRAM | 0 (Option A) |
| cycles / tile | +1-2 |
| register map | unchanged (VERSION would change) |
| verification | new golden vectors (the anchor flag changes the integer model's last layer), new RTL tests (alignment, saturation at -256 / 255, seam), new bitstream, board regression |

The anchor also forces a **bitstream rebuild** (as any new weights do, since the weights are read with `$readmemh` at synthesis and the SHIFT values change).
Because new weights need a rebuild anyway, the extra work of the anchor is the RTL edit and its verification, not an additional build.
