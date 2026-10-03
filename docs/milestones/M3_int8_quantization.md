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

## 4. Output of this milestone

1. `software/ai/quantization/quantize.py` and `software/ai/quantization/integer_reference.py` (+ tests).
2. Exported weight/bias/requant files.
3. Golden input/output test vectors.
4. Table: FP32 vs INT8 PSNR/SSIM.

## 5. Exit checklist

- [ ] INT8 quality drop vs FP32 measured and acceptable.
- [ ] Integer model uses only integer types (no float anywhere in the inference path).
- [ ] Integer model matches PyTorch-quantized output within a small tolerance.
- [ ] Edge-case unit tests pass.
- [ ] Weight/bias/M/SHIFT files exported and the file layout is documented.
- [ ] Golden test vectors saved.

## 6. Common problems

| Symptom | Cause |
|---|---|
| Big quality drop | Bad activation scales (outliers); use percentile (99.9 %) instead of max, try per-channel weights, or QAT |
| Overflow | Using int8/int16 accumulation in NumPy; use int32/int64 |
| Output off by 1 | Rounding rule differs (floor vs round-to-nearest) |
| Colours flipped | RGB vs BGR (OpenCV) mismatch between scripts |
