# M2 training summary

Recipe (all runs): SRNet x2, 2,620 params (ch=16), L1, Adam 2e-3 cosine -> 2e-5, 100 epochs x 500 steps x batch 32, LR patch 32 (+3 px halo),
flips/rot90, seed 0, CPU. One *epoch* = 16,000 patches (~0.45 pass over 55 images, ~0.14 pass over 180 images).

## Reproducibility (same recipe, 55 train / 5 val images)
| Run | Threads | Best epoch | Val PSNR-Y |
|---|---|---|---|
| original v1 | 10 | 99 | 32.288 |
| rerun | 6 | 96 | 32.309 |
Weights are NOT bit-identical (thread count changes float summation order) but quality agrees within 0.02 dB.
=> training is statistically reproducible; the exported weights (M3) are the frozen artifact.

## Controlled comparison (180 train / 12 val images; selection on validation only)
| Variant | Params | Best val PSNR-Y (dB) | vs bicubic (33.719) |
|---|---|---|---|
| **A: L1, ch16 (chosen)** | 2,620 | **34.954** | +1.235 |
| B: L1 + 0.2*(1-SSIM) | 2,620 | 34.908 | +1.189 |
| C: edge-touching windows (replicate pad) | 2,620 | 34.891 | +1.172 |
| D: ch24 | ~5.5k | 34.869 | +1.150 |
All variants within ~0.09 dB (run-to-run noise ~0.02-0.05 dB): no variant is meaningfully better, so the simplest/cheapest (A) is kept.

## Border effect (test sets, Y channel, outer 8 HR px vs interior)
| Model | interior gain | outer-band gain |
|---|---|---|
| A (final) | +0.98 dB | +0.83 dB |
| C (edge windows, info only) | +0.93 dB | +0.79 dB |
Replicate padding costs ~0.15 dB inside an 8-px band (a few % of pixels); training on edge windows does not fix it, so it is not padding-induced. No action needed.

## Final model (srnet_fp32.pt = A) on test sets, PSNR-Y: Set5 35.21 (+1.53), Set14 31.51 (+1.18), BSD100 30.60 (+1.04); better than bicubic on 119/119 images
(BSD100 per-image gain: min +0.46, median +0.98, max +2.46 dB). Curves: training_curves.png.

## Seed spread (final recipe A, 180 train / 12 val)
| Seed | Val PSNR-Y | Set5 | Set14 | BSD100 (test PSNR-Y) |
|---|---|---|---|---|
| 0 (shipped) | 34.954 | 35.205 | 31.508 | 30.602 |
| 1 | 34.873 | 35.115 | 31.432 | 30.571 |
| difference | 0.081 | 0.090 | 0.077 | 0.031 |
Seed 1 still beats bicubic by +1.45 / +1.11 / +1.01 dB. Quote results as "about +1.0 to +1.5 dB, +/-0.1 dB between seeds". Seed 0 was the pre-chosen
recipe run (not picked after looking at test results).

## Target-resolution and tiling check (`check_target_res.py`)
960x540 -> 1920x1080 on a validation image: model 41.31 dB vs bicubic 40.38 dB (PSNR-Y); whole image runs in ~0.1 s on CPU.
135 tiles (64x64 core + 3 px halo) match the whole-image output to 6.6e-7 in float; 98 of 6.2M uint8 values differ by 1 (float summation order only).

## Training data check
180 train + 12 val = 192 genuine DIV2K photos (contact sheet reviewed): varied content, 168 landscape / 24 portrait, no grayscale or low-contrast
images, no exact or near duplicates (max train-test thumbnail correlation 0.835, duplicate threshold 0.98).
