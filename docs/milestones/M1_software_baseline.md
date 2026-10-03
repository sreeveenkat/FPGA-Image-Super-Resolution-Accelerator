# M1 — Software Baseline: Bicubic Upscaling and Quality Metrics

**Time:** ~1 week | **Where:** PC, Python | **Depends on:** nothing (can run in parallel with M0)

---

## 1. Why this milestone exists

Before building any neural network you must answer: **"How good is the simplest method?"**
If your CNN is not clearly better than simple interpolation, the whole project has no point.
So we measure the simple method first. That number is the **floor** every later result is compared with.

You also set up the **measurement tools** (PSNR, SSIM) and the **dataset** you will use for the entire project.

---

## 2. Concepts

### Super-resolution
You have a high-res image `HR`. You shrink it to get a low-res image `LR` (this simulates a "small blurry" input).
The job is to rebuild `HR` from `LR`. Because we *have* the original `HR`, we can measure the error exactly.

```
HR (1920×1080) ──downscale ×2──► LR (960×540) ──upscale ×2──► SR (1920×1080) ──compare──► HR
```

### Nearest-neighbour vs bicubic
- **Nearest-neighbour:** copy each pixel into a 2×2 block. Blocky.
- **Bicubic:** each new pixel is a smooth weighted average of the 4×4 nearest low-res pixels. Smoother, still blurry.

### PSNR (Peak Signal-to-Noise Ratio)
Measures pixel error. Higher is better.

```
MSE  = average((SR − HR)²)
PSNR = 10 · log10(255² / MSE)   dB
```
Measured here (Y-channel): Set5 33.67 dB, Set14 30.32 dB, BSD100 29.56 dB. A gain of **0.5–1 dB** is already visible.

### SSIM (Structural Similarity)
Measures whether edges/texture/contrast look similar. Range 0–1, higher is better (1 = identical).

### Why not just trust your eyes?
Eyes are subjective and tired. Numbers are repeatable. But always look at images too: numbers can hide artifacts.

---

## 3. Step-by-step

### Step 1 — Get a dataset
Download a public SR dataset. Suggested:
- **Training:** DIV2K (800 train images) or General-100 (100 images, smaller)
- **Testing:** Set5, Set14, BSD100 (standard benchmarks)

Rule: **the test images must never be used for training.**

### Step 2 — Make LR/HR pairs
```python
import cv2, numpy as np

def make_pair(path, scale=2):
    hr = cv2.imread(path)                                   # BGR uint8
    h, w = hr.shape[:2]
    h, w = h - h % scale, w - w % scale                     # crop so size divides by scale
    hr = hr[:h, :w]
    lr = np.asarray(Image.fromarray(hr).resize((w // scale, h // scale), Image.BICUBIC))  # Pillow bicubic is anti-aliased, like the official benchmark LR
    return lr, hr
```

### Step 3 — Bicubic and nearest baselines
```python
def upscale(lr, scale=2, mode=cv2.INTER_CUBIC):
    h, w = lr.shape[:2]
    return cv2.resize(lr, (w * scale, h * scale), interpolation=mode)
```

### Step 4 — Metrics
```python
from skimage.metrics import peak_signal_noise_ratio as psnr
from skimage.metrics import structural_similarity as ssim

p = psnr(hr, sr, data_range=255)
s = ssim(hr, sr, channel_axis=2, data_range=255)
```
Use the library functions. Hand-written SSIM is a classic source of silent bugs.

### Step 5 — Evaluate on the whole test set
Loop over every test image, compute PSNR and SSIM for nearest and bicubic, and average. Save a table:

| Method | Set5 PSNR | Set5 SSIM | Set14 PSNR | Set14 SSIM |
|---|---|---|---|---|
| Nearest | … | … | … | … |
| Bicubic | … | … | … | … |

### Step 6 — Look at the pictures
Save `LR`, `bicubic`, `HR` side by side for 3–4 images. Zoom in on edges and text.

### Step 7 — Save the project's data layout
```
data/
  train/HR/*.png      (high-res training images)
  test/HR/*.png
  test/LR/*.png       (generated once, so results are repeatable)
```
Always use the same downscaling method and the same crops every time.

---

## 4. Output of this milestone

1. A script `software/ai/evaluation/eval_baseline.py` that prints the table above.
2. Saved comparison images.
3. **Your floor numbers** (write them into `results.md`).

## 5. Exit checklist

- [x] LR/HR pairs generated; train and test images are different files (checked by `software/ai/dataset/check_dataset.py`).
- [ ] Nearest and bicubic PSNR/SSIM recorded for each test set.
- [ ] Side-by-side images look sensible (bicubic is smooth, not shifted or colour-swapped).
- [ ] The script re-runs and gives identical numbers.

## 6. Common problems

| Symptom | Cause |
|---|---|
| PSNR suspiciously huge (>60 dB) | You compared an image with itself or with a copy |
| PSNR very low (<15 dB) | Size mismatch, shifted by a pixel, or BGR vs RGB mix-up |
| Different results each run | Random crops without a fixed seed |
