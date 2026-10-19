# INT8 integer model vs FP32 vs bicubic, x2

| Set | Method | PSNR RGB | SSIM RGB | PSNR Y | SSIM Y | images better than bicubic (PSNR Y) |
|---|---|---|---|---|---|---|
| Set5 (5) | bicubic | 31.79 | 0.9088 | 33.67 | 0.9303 | - |
| Set5 (5) | fp32 | 32.37 | 0.9195 | 35.15 | 0.9459 | 4 |
| Set5 (5) | int8 | 33.62 | 0.9271 | 35.84 | 0.9480 | 5 |
| Set14 (14) | bicubic | 28.30 | 0.8426 | 30.32 | 0.8698 | - |
| Set14 (14) | fp32 | 28.91 | 0.8670 | 31.46 | 0.8987 | 14 |
| Set14 (14) | int8 | 29.60 | 0.8725 | 31.89 | 0.9003 | 14 |
| BSD100 (100) | bicubic | 28.23 | 0.8299 | 29.56 | 0.8434 | - |
| BSD100 (100) | fp32 | 28.77 | 0.8648 | 30.51 | 0.8801 | 92 |
| BSD100 (100) | int8 | 29.45 | 0.8678 | 30.87 | 0.8806 | 100 |

Per-image drop int8 vs fp32 (PSNR Y, dB):

* Set5: mean -0.681, worst -0.172, best -1.657
* Set14: mean -0.424, worst -0.071, best -1.444
* BSD100: mean -0.358, worst -0.007, best -3.305
