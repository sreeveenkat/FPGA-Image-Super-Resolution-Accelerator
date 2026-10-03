# M2 — Train the CNN in PyTorch (FP32)

**Time:** 1.5–2 weeks | **Where:** PC, Python (GPU helps but a CPU can do this small model, slowly; Google Colab also works)
**Depends on:** M1

---

## 1. Why this milestone exists

The FPGA can only *run* a network; someone has to *teach* it first. Teaching (training) happens on the PC in normal
32-bit floating point (FP32). We do it at full precision first so that, if the result is bad, we know it is a
**network/training problem** and not a **precision problem**. Quantization comes in M3, after this works.

---

## 2. Concepts

### What a CNN layer does
A 3×3 convolution slides a small grid of learned numbers (a *kernel*, 9 weights per input channel) over the image.
At each position it multiplies and adds: `out = Σ weight × pixel + bias`. Many kernels → many output channels
("feature maps"). Stacked layers detect edges, then shapes, then detail.

```
input 3 channels ─► Conv3×3 ─► 16 feature channels ─► ReLU ─► ...
```

- **ReLU**: `max(0, x)`. Cheap in hardware (just clear the value if negative).
- **Depthwise conv**: each channel gets its own 3×3 kernel (channels do not mix). Cheap.
- **Pointwise conv (1×1)**: mixes channels at each pixel. Cheap.
- **Pixel shuffle**: rearranges channels into space. With ×2 scale it turns 12 channels at (H, W) into 3 channels at (2H, 2W). It needs **no maths**, only re-addressing.

### Why we predict 12 channels
Each low-res pixel must produce a 2×2 block of high-res pixels × 3 colours = 4 × 3 = **12 numbers**.
Pixel shuffle puts those 12 numbers into the right place.

### Training
Show the network many `(LR, HR)` pairs. Compare its output to the true HR with a *loss*. Use gradients to nudge the weights
to reduce the loss. Repeat for thousands of steps.

### Overfitting and why we split by image
If a test image was also used for training, the score is fake. Keep train and test images strictly separate.

---

## 3. The network (version 1, ×2)

```
Input  3 ch (RGB)
Conv 3×3,  3 → 16,  ReLU
DepthwiseConv 3×3, 16, ReLU
Conv 1×1, 16 → 16,  ReLU        (pointwise)
Conv 3×3, 16 → 12               (no ReLU)
PixelShuffle(2)  → 3 ch, 2× size
```

| Layer | Parameters (weights + bias) | MACs per low-res pixel |
|---|---|---|
| Conv 3→16, 3×3 | 3·16·9 + 16 = 448 | 432 |
| Depthwise 16, 3×3 | 16·9 + 16 = 160 | 144 |
| Pointwise 16→16 | 16·16 + 16 = 272 | 256 |
| Conv 16→12, 3×3 | 16·12·9 + 12 = 1,740 | 1,728 |
| **Total** | **2,620** | **2,560** |

At 960×540 that is ≈ 1.3 billion MACs per frame. This number drives the hardware design in M4.

The real implementation is `software/ai/models/srnet.py` (all convolutions are **valid**, i.e. `padding=0`):

```python
class SRNet(nn.Module):
    def __init__(self, scale=2, ch=16):
        super().__init__()
        self.conv1 = nn.Conv2d(3, ch, 3)
        self.dw    = nn.Conv2d(ch, ch, 3, groups=ch)      # depthwise
        self.pw    = nn.Conv2d(ch, ch, 1)                 # pointwise
        self.conv4 = nn.Conv2d(ch, 3 * scale * scale, 3)
        self.shuffle = nn.PixelShuffle(scale)

    def forward(self, x):   # x: (N,3,H+6,W+6) in [0,1]  ->  (N,3,2H,2W)
        x = F.relu(self.conv1(x)); x = F.relu(self.dw(x)); x = F.relu(self.pw(x))
        return self.shuffle(self.conv4(x))
```
Input must carry a 3-pixel border (**halo**): replicate-padding for whole images, real neighbouring pixels for tiles.
This is exactly what the FPGA tile engine does, so the trained network matches the hardware.

Keep the design **hardware-friendly**: only ReLU (no PReLU/BatchNorm that cannot be folded), no residual adds across layers
for version 1. If you add BatchNorm during training, fold it into the conv weights before export.

---

## 4. Step-by-step

### Step 1 — Dataset loader
- Take random **LR windows of 38×38** (32×32 core + 3-pixel border on every side, real neighbours) and the matching **HR patch 64×64** of the core.
- Augment: random flips and 90° rotations.
- Pixel values scaled to [0, 1].

### Step 2 — Loss and optimizer
- Start with **L1 loss** (`nn.L1Loss()`).
- Adam optimizer. Used here: learning rate `2e-3` with cosine decay to `2e-5` (the simpler step-halving at `1e-3` would also work).
- Batch size 16–64.
- Later (optional) add an SSIM term: `L1 + 0.2·(1 − SSIM)`.

### Step 3 — Train
- Run 100 epochs of 500 steps each (here an "epoch" = 500 random batches, about 0.14 of a pass over 180 images). Log training loss and **validation PSNR** every epoch.
- Save the best checkpoint by validation PSNR.

### Step 4 — Evaluate on the **full** test images
Run the full LR image through the network (the network is fully convolutional, so any size works). Compute PSNR/SSIM.
Compare with the M1 bicubic table.

| Method | Set5 PSNR | Set14 PSNR | BSD100 PSNR |
|---|---|---|---|
| Bicubic (M1) | … | … | … |
| Your FP32 CNN | … | … | … |

Honest expectation: a 2.6 K-parameter network will give a **modest but real** gain over bicubic (on the order of a few
tenths of a dB up to ~1 dB; this is my estimate, yours may differ). If you see no gain, increase `ch` to 24, train longer,
or check the data pipeline before blaming the architecture.

### Step 5 — Look at the images
Zoom into edges and text. Check for **checkerboard patterns, colour shifts, overall blur**.

### Step 6 — Count and save
- Print parameter count and MACs per pixel (matches the table above).
- Save `software/ai/checkpoints/srnet_fp32.pt` and the exact training command.

---

## 4b. Results achieved (final model, 2026-10-03)

| Set | Bicubic PSNR-Y | FP32 CNN PSNR-Y | Gain | SSIM-Y bicubic -> CNN |
|---|---|---|---|---|
| Set5 | 33.67 | 35.21 | +1.53 | 0.9303 -> 0.9449 |
| Set14 | 30.32 | 31.51 | +1.18 | 0.8698 -> 0.8975 |
| BSD100 | 29.56 | 30.60 | +1.04 | 0.8434 -> 0.8785 |

Better than bicubic on 119 of 119 images. Details, ablations and reproducibility notes: `results/quality/m2_training_summary.md`.
Notes: SSIM loss, a 24-channel model and edge-window sampling were all tried and gave no meaningful gain (see the summary file), so the plain L1 / 16-channel model is the final one.

## 5. Output of this milestone

1. `software/ai/training/train.py`, `software/ai/models/srnet.py`, `software/ai/evaluation/eval_model.py`.
2. A trained checkpoint.
3. A PSNR/SSIM table showing **FP32 CNN vs bicubic**.
4. Output images for a visual check.

## 6. Exit checklist

- [x] Bicubic and FP32 numbers recorded side by side (`results/quality/model_fp32_x2.md`).
- [x] FP32 beats bicubic on held-out test images by a clear margin (+1.04 to +1.53 dB PSNR-Y; 119/119 images).
- [x] No obvious artifacts (visual review of 19 Set5/Set14 zoom crops, 4 BSD100 and 1 full frame recorded in `CLAUDE.md` section 6c; fine random texture is not recovered, which is expected).
- [x] Training is repeatable (fixed seed, saved command, saved checkpoint). Caveat: statistically reproducible only (rerun differs ~0.02 dB), not bit-exact, so the checkpoint is the frozen artifact.
- [x] Parameter count and MACs/pixel recorded (2,620 / 2,560; asserted in `test_model.py`).

## 7. Common problems

| Symptom | Cause / fix |
|---|---|
| Loss does not go down | Learning rate too high/low; input not scaled to [0,1]; LR/HR patches not aligned |
| Output looks grey | Last layer bias/scale problem; train longer; check normalization |
| Checkerboard | Pixel shuffle with too short training; try longer training or lower learning rate |
| Great train PSNR, poor test PSNR | Overfitting; add augmentation and more images |
| Worse than bicubic | Misaligned pairs, or too few epochs |
