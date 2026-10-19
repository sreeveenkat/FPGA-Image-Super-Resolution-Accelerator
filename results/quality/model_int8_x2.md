# INT8 integer model vs FP32 vs bicubic, x2

| Set | Method | PSNR RGB | SSIM RGB | PSNR Y | SSIM Y | images better than bicubic (PSNR Y) |
|---|---|---|---|---|---|---|
| Set5 (5) | bicubic | 31.79 | 0.9088 | 33.67 | 0.9303 | - |
| Set5 (5) | fp32 | 34.11 | 0.9336 | 36.20 | 0.9518 | 5 |
| Set5 (5) | int8 | 34.11 | 0.9332 | 36.20 | 0.9515 | 5 |
| Set14 (14) | bicubic | 28.30 | 0.8426 | 30.32 | 0.8698 | - |
| Set14 (14) | fp32 | 29.87 | 0.8786 | 32.12 | 0.9037 | 14 |
| Set14 (14) | int8 | 29.87 | 0.8782 | 32.12 | 0.9035 | 14 |
| BSD100 (100) | bicubic | 28.23 | 0.8299 | 29.56 | 0.8434 | - |
| BSD100 (100) | fp32 | 29.65 | 0.8734 | 31.01 | 0.8836 | 100 |
| BSD100 (100) | int8 | 29.65 | 0.8730 | 31.01 | 0.8833 | 100 |

Per-image drop int8 vs fp32 (PSNR Y, dB):

* Set5: mean 0.002, worst 0.035, best -0.041
* Set14: mean 0.001, worst 0.084, best -0.034
* BSD100: mean 0.001, worst 0.062, best -0.034
