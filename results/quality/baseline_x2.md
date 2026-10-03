# Baseline x2

LR = Pillow bicubic of the even-cropped HR (bit-exact with official LR for even-sized images). 'bicubic' = Pillow bicubic upscale; 'bicubic_cv2' = OpenCV, comparison only.
SSIM = Gaussian 11x11 (sigma 1.5). Y columns: BT.601 luma, 2-px border shaved. Means over all images in the set.

| Set | Method | PSNR RGB (dB) | SSIM RGB | PSNR Y (dB) | SSIM Y |
|---|---|---|---|---|---|
| Set5 (5) | nearest | 29.08 | 0.8783 | 30.86 | 0.9001 |
| Set5 (5) | bicubic | 31.79 | 0.9088 | 33.67 | 0.9303 |
| Set5 (5) | bicubic_cv2 | 32.07 | 0.9121 | 33.97 | 0.9330 |
| Set14 (14) | nearest | 26.72 | 0.8202 | 28.58 | 0.8464 |
| Set14 (14) | bicubic | 28.30 | 0.8426 | 30.32 | 0.8698 |
| Set14 (14) | bicubic_cv2 | 28.51 | 0.8482 | 30.56 | 0.8750 |
| BSD100 (100) | nearest | 27.10 | 0.8117 | 28.42 | 0.8251 |
| BSD100 (100) | bicubic | 28.23 | 0.8299 | 29.56 | 0.8434 |
| BSD100 (100) | bicubic_cv2 | 28.41 | 0.8365 | 29.74 | 0.8495 |
