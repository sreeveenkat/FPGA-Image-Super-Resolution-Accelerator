# INT8 integer model vs FP32 vs bicubic, x2

| Set | Method | PSNR RGB | SSIM RGB | PSNR Y | SSIM Y | images better than bicubic (PSNR Y) |
|---|---|---|---|---|---|---|
| Set5 (5) | bicubic | 31.79 | 0.9088 | 33.67 | 0.9303 | - |
| Set5 (5) | fp32 | 33.12 | 0.9244 | 35.21 | 0.9449 | 5 |
| Set5 (5) | int8 | 32.83 | 0.9160 | 35.02 | 0.9420 | 5 |
| Set14 (14) | bicubic | 28.30 | 0.8426 | 30.32 | 0.8698 | - |
| Set14 (14) | fp32 | 29.29 | 0.8688 | 31.51 | 0.8975 | 14 |
| Set14 (14) | int8 | 29.15 | 0.8617 | 31.40 | 0.8948 | 14 |
| BSD100 (100) | bicubic | 28.23 | 0.8299 | 29.56 | 0.8434 | - |
| BSD100 (100) | fp32 | 29.24 | 0.8673 | 30.60 | 0.8785 | 100 |
| BSD100 (100) | int8 | 29.11 | 0.8609 | 30.53 | 0.8756 | 100 |

Per-image drop int8 vs fp32 (PSNR Y, dB):

* Set5: mean 0.182, worst 0.314, best 0.073
* Set14: mean 0.111, worst 0.285, best 0.017
* BSD100: mean 0.076, worst 0.413, best 0.008
