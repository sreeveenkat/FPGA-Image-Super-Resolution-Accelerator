# Model 'fp32' vs bicubic, x2 (checkpoint QAT step 30000 (weights tuned for INT8: the FP32 forward is not their optimum))

| Set | Method | PSNR RGB | SSIM RGB | PSNR Y | SSIM Y | images better than bicubic (PSNR Y) |
|---|---|---|---|---|---|---|
| Set5 (5) | bicubic | 31.79 | 0.9088 | 33.67 | 0.9303 | - |
| Set5 (5) | fp32 | 32.37 | 0.9195 | 35.15 | 0.9459 | 4 |
| Set14 (14) | bicubic | 28.30 | 0.8426 | 30.32 | 0.8698 | - |
| Set14 (14) | fp32 | 28.91 | 0.8670 | 31.46 | 0.8987 | 14 |
| BSD100 (100) | bicubic | 28.23 | 0.8299 | 29.56 | 0.8434 | - |
| BSD100 (100) | fp32 | 28.77 | 0.8648 | 30.51 | 0.8801 | 92 |
