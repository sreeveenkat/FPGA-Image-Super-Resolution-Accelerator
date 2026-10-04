# M3 — INT8 Quantization and the Bit-Accurate Integer Model

**Time:** 1–1.5 weeks | **Where:** PC, Python | **Depends on:** M2

---

## 1. Why this milestone exists

The FPGA's DSP slices are efficient at **small integer** maths, not floating point. Floating-point multipliers on this
FPGA would eat huge area and be slow. So we convert the network to **INT8**: 8-bit whole numbers.

This milestone has two products:
1. An INT8 version of your network (with its quality cost measured).
2. A **pure-integer Python model** that does *exactly* the arithmetic the hardware will do.
   **This is the most important file of the whole project.** In M4/M5 you compare your Verilog against it, bit for bit.

---

## 2. Concepts

### What quantization means
Real value ≈ `scale × integer`.

```
weight = 0.0731  →  scale = 0.001  →  stored integer = 73
```
An INT8 number is in [−128, 127] (signed) or [0, 255] (unsigned).

### Our number types (keep it simple, hardware-friendly)

| Thing | Type | Reason |
|---|---|---|
| Input pixels | uint8 (0–255), scale = 1/255 | They already are 8-bit |
| Weights | int8, **symmetric** (zero point = 0), per-layer or per-output-channel scale | Simplest multiplier |
| Activations after ReLU | uint8 | ReLU output is never negative |
| Last layer output | int8 (signed) or uint8 after clamp to image range | Final pixel is clamped to 0–255 |
| Accumulator | **int32** | 9·16 products of 8×8 bits fit safely |
| Bias | int32, scale = input_scale × weight_scale | Added directly to the accumulator |

### The integer pipeline for one output value
```
acc   = Σ (activation_uint8 × weight_int8)        # int32
acc  += bias_int32
out   = (acc × M + rounding) >> SHIFT             # requantize
out   = clamp(out, 0, 255)                        # saturate (ReLU is the clamp at 0)
```
`M` is an integer multiplier and `SHIFT` an integer shift that together approximate the real number
`input_scale × weight_scale / output_scale`. Example: real ratio 0.0037 → `M = 3891`, `SHIFT = 20` (3891/2²⁰ ≈ 0.00371).
Use the same `M`, `SHIFT`, rounding and clamp in Python and in Verilog. No floating point anywhere in this path.

### QAT vs post-training quantization (PTQ)
- **PTQ**: quantize the finished FP32 model directly. Quick; may lose quality.
- **QAT** (quantization-aware training): insert "fake quantization" during fine-tuning so the network learns to cope with rounding.
Try PTQ first. If the PSNR drop is large (say > 0.3 dB, my rule of thumb), do a short QAT fine-tune from the FP32 checkpoint.

### Why the PyTorch quantized model is not the golden reference
PyTorch's internal rounding and requantization may differ in detail from what you will build in Verilog. Your own NumPy
integer model has complete control, so it is the one that defines "correct".

---

## 3. Step-by-step

### Step 1 — Collect value ranges (calibration)
Run ~100 training images through the FP32 model and record the maximum activation value after each layer.
These maxima decide each layer's activation scale: `act_scale = max_value / 255`.

### Step 2 — Quantize weights
```python
def quant_weights(w):                          # w: float tensor
    scale = np.abs(w).max() / 127.0            # per-layer symmetric
    q = np.clip(np.round(w / scale), -128, 127).astype(np.int8)
    return q, scale
```
(Per-output-channel scales give better quality; start per-layer, upgrade if the quality drop is too big.)

### Step 3 — Bias and requantization constants
```
bias_int32 = round(bias_fp / (in_scale * w_scale))
real_mult  = in_scale * w_scale / out_scale
M, SHIFT   = choose so that M / 2**SHIFT ≈ real_mult, with M fitting in ~16 bits
```

### Step 4 — Write the integer reference model
Pure NumPy, integer dtypes only. Skeleton:

```python
import numpy as np

def conv3x3_int(x, w, bias, M, SHIFT, lo=0, hi=255):
    """VALID 3x3 convolution (no padding): (C_in,H,W) -> (C_out,H-2,W-2). Same convention as the trained PyTorch model.
    x: uint8/int32 activations; w: (C_out,C_in,3,3) int8; bias: int32 per output channel."""
    C_out, C_in = w.shape[:2]
    H, W = x.shape[1] - 2, x.shape[2] - 2
    x = x.astype(np.int32)
    out = np.zeros((C_out, H, W), dtype=np.int32)
    for co in range(C_out):
        acc = np.zeros((H, W), dtype=np.int64) + int(bias[co])
        for ci in range(C_in):
            for ky in range(3):
                for kx in range(3):
                    acc += x[ci, ky:ky+H, kx:kx+W].astype(np.int64) * int(w[co, ci, ky, kx])
        y = (acc * M + (1 << (SHIFT - 1))) >> SHIFT        # round half up; >> on int64 is an arithmetic shift
        out[co] = np.clip(y, lo, hi)                        # ReLU layers: lo=0.  Last layer: lo=0, hi=255 (it outputs pixels)
    return out

# whole network:  x = replicate-pad(img_uint8, 3)  ->  conv1 -> dw -> pw -> conv4 -> pixel_shuffle  ->  uint8 image 2H x 2W
```
Write the same style for depthwise and pointwise, then `pixel_shuffle`, then chain them into `run_network(img_uint8)`.
Be explicit about: rounding rule, arithmetic shift of negatives, clamp limits. **Padding convention (decided in M2): replicate-pad the whole input by 3 pixels, then use VALID convolutions.** The last layer's output *is* the pixel value, so its output scale is 1/255 and its clamp is [0, 255] (no ReLU needed, the clamp does it).

### Step 5 — Unit tests for the integer model
Test by hand-calculated cases:
- all-zero input, all-zero weights
- single non-zero pixel (checks the kernel orientation)
- extremes: `-128 × -128`, `127 × 255`, maximum possible accumulation
- rounding boundary (value exactly at .5), saturation at 0 and 255

### Step 6 — Compare with the float and PyTorch-INT8 models
Run test images through: FP32 → PyTorch quantized → your integer model.

| Model | PSNR | SSIM |
|---|---|---|
| Bicubic | … | … |
| FP32 | … | … |
| Integer model | … | … |

The integer model should match the PyTorch quantized output closely. The drop FP32 → integer is a **real result to report**.

### Step 7 — Export for hardware
Write files that Verilog and C can read:
- `weights_L1.mem` … hexadecimal text, one value per line (for `$readmemh` in Verilog)
- `bias_L1.mem`, plus `M` and `SHIFT` per layer
- `network_params.h` (C header) — optional
- `golden/` folder: a few input tiles and their expected output tiles from the integer model (test vectors for M4/M5)

Fix a **weight layout** (e.g. `[out_ch][in_ch][ky][kx]`) and write it down — layout mismatch between Python and Verilog is a top bug.

---

## 4. Results achieved (2026-10-04)

What was built, in `software/ai/quantization/`:

| File | Purpose |
|---|---|
| `quantize.py` | Calibrates on the first 100 of the 180 *training* images (one random 256x256 LR crop each), quantizes weights/biases, picks `M`/`SHIFT`, writes `qparams.npz` |
| `integer_reference.py` | The golden integer model (pure NumPy, no torch): `upscale`, `upscale_tiled`, `run_tile` (70x70 -> 128x128), `forward_layers` (all intermediates) |
| `export_rtl.py` | Writes `hardware/rtl/weights/{weights,bias,mult}_Ln.mem`, `network_params.vh`, README, and the golden tiles in `data/golden/` |
| `test_integer.py`, `test_export.py` | 21 + 7 tests |
| `check_export_independent.py` | Pure-Python (no numpy) recompute of every golden tile from the exported `.mem`/`.vh`/`.hex` files only |
| `../evaluation/eval_int8.py` | `--sweep` (validation images only) and the final test-set evaluation |

Scheme actually used: uint8 activations (one scale per layer), int8 symmetric weights in [-127, 127] with one scale per layer, int32 bias,
`M` unsigned 16 bit per output channel (identical across channels with per-layer weight scales), `SHIFT` per layer (24, 23, 21, 24),
last layer scale 1/255 and clamp [0, 255]. Worst-case accumulator magnitude fits signed 32 bit (test); `acc*M` needs about 40 bits.

Settings were chosen on the 12 validation images (PSNR-Y, FP32 = 34.954 dB there), `results/quality/m3_ptq_sweep.md`:
percentile 99 -> -5.3 dB (clips far too much), 99.9 -> -0.43, **99.99 -> -0.22**, max -> -0.28; per-channel weights were slightly *worse*
than per-layer (-0.31 at 99.99), so per-layer was kept. Drop is below the 0.3 dB rule of thumb, so PTQ is enough and no QAT was done.

Final test-set numbers (`results/quality/model_int8_x2.md`, PSNR-Y):

| Set | Bicubic | FP32 | INT8 | Drop FP32 -> INT8 | Worst single image |
|---|---|---|---|---|---|
| Set5 | 33.67 | 35.21 | 35.02 | 0.18 | 0.31 |
| Set14 | 30.32 | 31.51 | 31.40 | 0.11 | 0.29 |
| BSD100 | 29.56 | 30.60 | 30.53 | 0.08 | 0.41 |

INT8 beats bicubic on 119/119 images. SSIM-Y drops by 0.003 (Set5/Set14: 0.9449 -> 0.9420, 0.8975 -> 0.8948) and 0.003 on BSD100.

Verification notes (honest limits):
* The "PyTorch quantized model" comparison in step 6 was **not** done with `torch.ao.quantization` (its rounding is not ours and it is not
  the reference). Instead `test_layerwise_matches_independent_float64_torch_with_real_scales` runs each layer through torch `conv2d` in
  float64 on exact integers with the *exact* real multiplier: it differs from the integer model by at most 1 LSB on 0.004-0.06 % of values
  (only where the 16-bit `M` flips a rounding tie). The integer output is 48 dB PSNR from the FP32 output on a test image.
* Tiled == whole image holds **exactly** (synthetic sizes including non-multiples of 64, a small 16 px core, and a real image).
* 22 deliberate breakages (rounding, shift, clamps, shuffle order, kernel flip, bias, padding mode, int32 overflow, scale and export
  mistakes) were all caught by the tests.

## 5. Output of this milestone

1. `quantize.py`, `integer_reference.py`, `export_rtl.py` + tests (above).
2. Exported weight/bias/multiplier files in `hardware/rtl/weights/` (layout documented in its `README.md`).
3. Golden tiles in `data/golden/` (git-ignored, regenerate with `export_rtl.py`): zeros, full255, noise, pixel, ramp, small12, three real tiles, one border tile.
4. FP32 vs INT8 table (above).

## 6. Exit checklist

- [x] INT8 quality drop vs FP32 measured and acceptable (0.08-0.18 dB mean PSNR-Y per set).
- [x] Integer model uses only integer types (NumPy int64/int32 in the inference path; float scales in `qparams.npz` are documentation only).
- [x] Integer model matches an independent float64 reference within 1 LSB layer by layer (see the note above for why torch.ao was not used).
- [x] Edge-case unit tests pass (zero input, single pixel orientation, +-extremes, rounding ties, saturation, overflow).
- [x] Weight/bias/M/SHIFT files exported and the file layout is documented and round-trip tested.
- [x] Golden test vectors saved (regenerable, deterministic).

## 7. Common problems

| Symptom | Cause |
|---|---|
| Big quality drop | Bad activation scales (outliers); use percentile (99.99 % worked best here, 99 % is far too low) or QAT |
| Overflow | Using int8/int16 accumulation in NumPy; use int32/int64 |
| Output off by 1 | Rounding rule differs (floor vs round-to-nearest) |
| Colours flipped | RGB vs BGR (OpenCV) mismatch between scripts |
