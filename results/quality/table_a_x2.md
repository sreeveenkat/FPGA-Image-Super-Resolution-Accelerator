# Table A - image quality x2 (Set5 / Set14 / BSD100)

Recomputed by `software/ai/evaluation/run_all.py`; nearest/bicubic/FP32/INT8 equal the published M1-M3 CSVs (max difference 0); FPGA = the outputs read back from the ZedBoard (board-measured), each byte-identical to the INT8 integer model.
PSNR in dB. Y = BT.601 luma, 2-px border shaved. SSIM = Gaussian 11x11, sigma 1.5. Means over all images of a set.

| Set | Method | PSNR RGB | SSIM RGB | PSNR Y | SSIM Y | better than bicubic (PSNR Y) |
|---|---|---|---|---|---|---|
| Set5 (5) | nearest | 29.08 | 0.8783 | 30.86 | 0.9001 | - |
| Set5 (5) | bicubic | 31.79 | 0.9088 | 33.67 | 0.9303 | - |
| Set5 (5) | fp32 | 33.12 | 0.9244 | 35.21 | 0.9449 | 5/5 |
| Set5 (5) | int8 | 32.83 | 0.9160 | 35.02 | 0.9420 | 5/5 |
| Set5 (5) | fpga | 32.83 | 0.9160 | 35.02 | 0.9420 | 5/5 |
| Set14 (14) | nearest | 26.72 | 0.8202 | 28.58 | 0.8464 | - |
| Set14 (14) | bicubic | 28.30 | 0.8426 | 30.32 | 0.8698 | - |
| Set14 (14) | fp32 | 29.29 | 0.8688 | 31.51 | 0.8975 | 14/14 |
| Set14 (14) | int8 | 29.15 | 0.8617 | 31.40 | 0.8948 | 14/14 |
| Set14 (14) | fpga | 29.15 | 0.8617 | 31.40 | 0.8948 | 14/14 |
| BSD100 (100) | nearest | 27.10 | 0.8117 | 28.42 | 0.8251 | - |
| BSD100 (100) | bicubic | 28.23 | 0.8299 | 29.56 | 0.8434 | - |
| BSD100 (100) | fp32 | 29.24 | 0.8673 | 30.60 | 0.8785 | 100/100 |
| BSD100 (100) | int8 | 29.11 | 0.8609 | 30.53 | 0.8756 | 100/100 |
| BSD100 (100) | fpga | 29.11 | 0.8609 | 30.53 | 0.8756 | 100/100 |
