# Model 'fp32' vs bicubic, x2 (checkpoint QAT step 40000 (weights tuned for INT8: the FP32 forward is not their optimum))

| Set | Method | PSNR RGB | SSIM RGB | PSNR Y | SSIM Y | images better than bicubic (PSNR Y) |
|---|---|---|---|---|---|---|
| Set5 (5) | bicubic | 31.79 | 0.9088 | 33.67 | 0.9303 | - |
| Set5 (5) | fp32 | 6.55 | 0.0432 | 7.77 | 0.2514 | 0 |
| Set14 (14) | bicubic | 28.30 | 0.8426 | 30.32 | 0.8698 | - |
| Set14 (14) | fp32 | 5.96 | 0.0276 | 7.36 | 0.1891 | 0 |
| BSD100 (100) | bicubic | 28.23 | 0.8299 | 29.56 | 0.8434 | - |
| BSD100 (100) | fp32 | 7.04 | 0.0204 | 8.20 | 0.2070 | 0 |
