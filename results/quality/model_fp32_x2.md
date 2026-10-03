# Model 'fp32' vs bicubic, x2 (checkpoint epoch 99)

| Set | Method | PSNR RGB | SSIM RGB | PSNR Y | SSIM Y | images better than bicubic (PSNR Y) |
|---|---|---|---|---|---|---|
| Set5 (5) | bicubic | 31.79 | 0.9088 | 33.67 | 0.9303 | - |
| Set5 (5) | fp32 | 33.12 | 0.9244 | 35.21 | 0.9449 | 5 |
| Set14 (14) | bicubic | 28.30 | 0.8426 | 30.32 | 0.8698 | - |
| Set14 (14) | fp32 | 29.29 | 0.8688 | 31.51 | 0.8975 | 14 |
| BSD100 (100) | bicubic | 28.23 | 0.8299 | 29.56 | 0.8434 | - |
| BSD100 (100) | fp32 | 29.24 | 0.8673 | 30.60 | 0.8785 | 100 |
