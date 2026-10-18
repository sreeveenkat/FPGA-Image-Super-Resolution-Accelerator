# Image-quality ladder (x2; PSNR-Y / SSIM-Y, Y = BT.601, 2-px shave, Gaussian SSIM)

Mean ± half-range over seeds. Every choice (checkpoint, QAT step) was made on the 42 clean DIV2K validation images; Set5/Set14/BSD100 are reporting only.
INT8 = the NumPy integer model (bit-exact with the RTL).  QAT checkpoints are only meaningful quantized, so they have no FP32 row.

## FP32

| Row | Set5 PSNR | Set5 SSIM | Set14 PSNR | Set14 SSIM | BSD100 PSNR | BSD100 SSIM | val42 PSNR |
|---|---|---|---|---|---|---|---|
| **R0 baseline (deployed: 180 imgs, 50k steps)** (n=2) | 35.160 ± 0.045 | 0.9445 ± 0.0004 | 31.470 ± 0.038 | 0.8971 ± 0.0005 | 30.587 ± 0.015 | 0.8783 ± 0.0003 | 33.565 ± 0.034 |
| &nbsp;&nbsp;seed `baseline` | 35.205 | 0.9449 | 31.508 | 0.8975 | 30.602 | 0.8785 | 33.598 |
| &nbsp;&nbsp;seed `baseline_s1` | 35.115 | 0.9441 | 31.432 | 0.8966 | 30.571 | 0.8780 | 33.531 |
| **R1 plain, DIV2K-800+Flickr2K, 8-fold aug, cosine, 300k steps** (n=2) | 35.647 ± 0.013 | 0.9482 ± 0.0002 | 31.795 ± 0.018 | 0.9005 ± 0.0003 | 30.770 ± 0.016 | 0.8807 ± 0.0003 | 33.862 ± 0.016 |
| &nbsp;&nbsp;seed `plain_s0` | 35.659 | 0.9484 | 31.813 | 0.9008 | 30.786 | 0.8810 | 33.878 |
| &nbsp;&nbsp;seed `plain_s1` | 35.634 | 0.9481 | 31.777 | 0.9002 | 30.754 | 0.8804 | 33.846 |
| **R2 rep (re-parameterized training blocks, merged)** (n=2) | 36.060 ± 0.067 | 0.9509 ± 0.0003 | 32.052 ± 0.047 | 0.9026 ± 0.0004 | 30.946 ± 0.048 | 0.8824 ± 0.0004 | 34.120 ± 0.070 |
| &nbsp;&nbsp;seed `rep_s0` | 35.993 | 0.9506 | 32.004 | 0.9022 | 30.899 | 0.8820 | 34.050 |
| &nbsp;&nbsp;seed `rep_s1` | 36.126 | 0.9512 | 32.099 | 0.9030 | 30.994 | 0.8829 | 34.190 |
| **R3 plain + NN anchor** (n=2) | 36.116 ± 0.124 | 0.9513 ± 0.0009 | 32.088 ± 0.069 | 0.9029 ± 0.0010 | 30.987 ± 0.048 | 0.8828 ± 0.0010 | 34.170 ± 0.094 |
| &nbsp;&nbsp;seed `plainA_s0` | 35.992 | 0.9504 | 32.020 | 0.9020 | 30.940 | 0.8818 | 34.076 |
| &nbsp;&nbsp;seed `plainA_s1` | 36.240 | 0.9522 | 32.157 | 0.9039 | 31.035 | 0.8837 | 34.264 |
| **R4 rep + NN anchor** (n=2) | 36.054 ± 0.120 | 0.9508 ± 0.0009 | 32.068 ± 0.075 | 0.9025 ± 0.0011 | 30.962 ± 0.060 | 0.8823 ± 0.0010 | 34.129 ± 0.095 |
| &nbsp;&nbsp;seed `repA_s0` | 35.934 | 0.9499 | 31.993 | 0.9014 | 30.902 | 0.8813 | 34.034 |
| &nbsp;&nbsp;seed `repA_s1` | 36.174 | 0.9518 | 32.143 | 0.9036 | 31.022 | 0.8834 | 34.224 |

| Gain (mean over seeds) | Set5 PSNR | Set5 SSIM | Set14 PSNR | Set14 SSIM | BSD100 PSNR | BSD100 SSIM | val42 PSNR |
|---|---|---|---|---|---|---|---|
| data+recipe: R1 - R0 | +0.487 | +0.0037 | +0.325 | +0.0035 | +0.183 | +0.0024 | +0.298 |
| rep blocks: R2 - R1 | +0.413 | +0.0027 | +0.257 | +0.0021 | +0.176 | +0.0017 | +0.258 |
| anchor on plain: R3 - R1 | +0.469 | +0.0030 | +0.293 | +0.0024 | +0.217 | +0.0021 | +0.308 |
| anchor on rep: R4 - R2 | -0.006 (within noise) | -0.0001 (within noise) | +0.017 (within noise) | -0.0001 (within noise) | +0.016 (within noise) | -0.0001 (within noise) | +0.009 (within noise) |
| rep on anchor: R4 - R3 | -0.062 (within noise) | -0.0004 (within noise) | -0.020 (within noise) | -0.0004 (within noise) | -0.025 (within noise) | -0.0004 (within noise) | -0.041 (within noise) |

## INT8 by post-training quantization (PTQ, 99.99 percentile, per-layer weight scales)

| Row | Set5 PSNR | Set5 SSIM | Set14 PSNR | Set14 SSIM | BSD100 PSNR | BSD100 SSIM | val42 PSNR |
|---|---|---|---|---|---|---|---|
| **R0 baseline (deployed: 180 imgs, 50k steps)** (n=2) | 34.928 ± 0.095 | 0.9402 ± 0.0017 | 31.347 ± 0.051 | 0.8931 ± 0.0016 | 30.475 ± 0.051 | 0.8745 ± 0.0012 | 33.281 ± 0.136 |
| &nbsp;&nbsp;seed `baseline` | 35.023 | 0.9420 | 31.398 | 0.8948 | 30.526 | 0.8756 | 33.417 |
| &nbsp;&nbsp;seed `baseline_s1` | 34.833 | 0.9385 | 31.296 | 0.8915 | 30.424 | 0.8733 | 33.146 |
| **R1 plain, DIV2K-800+Flickr2K, 8-fold aug, cosine, 300k steps** (n=2) | 34.287 ± 0.411 | 0.9296 ± 0.0008 | 31.047 ± 0.218 | 0.8838 ± 0.0006 | 30.201 ± 0.122 | 0.8654 ± 0.0002 | 32.615 ± 0.195 |
| &nbsp;&nbsp;seed `plain_s0` | 34.698 | 0.9303 | 31.265 | 0.8844 | 30.324 | 0.8656 | 32.811 |
| &nbsp;&nbsp;seed `plain_s1` | 33.876 | 0.9288 | 30.828 | 0.8832 | 30.079 | 0.8652 | 32.420 |
| **R2 rep (re-parameterized training blocks, merged)** (n=2) | 32.394 ± 0.935 | 0.8622 ± 0.0418 | 29.859 ± 0.595 | 0.8172 ± 0.0405 | 29.291 ± 0.299 | 0.8112 ± 0.0256 | 31.017 ± 0.446 |
| &nbsp;&nbsp;seed `rep_s0` | 33.328 | 0.9040 | 30.454 | 0.8578 | 29.590 | 0.8368 | 31.462 |
| &nbsp;&nbsp;seed `rep_s1` | 31.459 | 0.8204 | 29.263 | 0.7767 | 28.991 | 0.7857 | 30.571 |
| **R3 plain + NN anchor** (n=2) | 35.887 ± 0.187 | 0.9476 ± 0.0022 | 31.973 ± 0.091 | 0.8998 ± 0.0020 | 30.903 ± 0.073 | 0.8799 ± 0.0019 | 33.976 ± 0.163 |
| &nbsp;&nbsp;seed `plainA_s0` | 35.699 | 0.9454 | 31.882 | 0.8978 | 30.829 | 0.8780 | 33.813 |
| &nbsp;&nbsp;seed `plainA_s1` | 36.074 | 0.9499 | 32.064 | 0.9019 | 30.976 | 0.8818 | 34.140 |
| **R4 rep + NN anchor** (n=2) | 35.502 ± 0.475 | 0.9444 ± 0.0050 | 31.804 ± 0.249 | 0.8977 ± 0.0044 | 30.763 ± 0.207 | 0.8776 ± 0.0045 | 33.656 ± 0.430 |
| &nbsp;&nbsp;seed `repA_s0` | 35.027 | 0.9394 | 31.555 | 0.8933 | 30.556 | 0.8731 | 33.226 |
| &nbsp;&nbsp;seed `repA_s1` | 35.977 | 0.9494 | 32.052 | 0.9020 | 30.970 | 0.8820 | 34.086 |

| Gain (mean over seeds) | Set5 PSNR | Set5 SSIM | Set14 PSNR | Set14 SSIM | BSD100 PSNR | BSD100 SSIM | val42 PSNR |
|---|---|---|---|---|---|---|---|

## INT8 after quantization-aware training (QAT, per-layer weight scales)

| Row | Set5 PSNR | Set5 SSIM | Set14 PSNR | Set14 SSIM | BSD100 PSNR | BSD100 SSIM | val42 PSNR |
|---|---|---|---|---|---|---|---|
| **R0 baseline (deployed: 180 imgs, 50k steps)** (n=2) | 34.928 ± 0.095 | 0.9402 ± 0.0017 | 31.347 ± 0.051 | 0.8931 ± 0.0016 | 30.475 ± 0.051 | 0.8745 ± 0.0012 | 33.281 ± 0.136 |
| &nbsp;&nbsp;seed `baseline` | 35.023 | 0.9420 | 31.398 | 0.8948 | 30.526 | 0.8756 | 33.417 |
| &nbsp;&nbsp;seed `baseline_s1` | 34.833 | 0.9385 | 31.296 | 0.8915 | 30.424 | 0.8733 | 33.146 |
| **R1 + QAT** (n=2) | 35.409 ± 0.020 | 0.9446 ± 0.0004 | 31.657 ± 0.017 | 0.8975 ± 0.0004 | 30.693 ± 0.017 | 0.8782 ± 0.0005 | 33.662 ± 0.016 |
| &nbsp;&nbsp;seed `plain_qat_s0` | 35.429 | 0.9450 | 31.673 | 0.8980 | 30.710 | 0.8787 | 33.677 |
| &nbsp;&nbsp;seed `plain_qat_s1` | 35.389 | 0.9442 | 31.640 | 0.8971 | 30.675 | 0.8776 | 33.646 |
| **R2 + QAT** (n=2) | 35.794 ± 0.043 | 0.9479 ± 0.0001 | 31.845 ± 0.042 | 0.9000 ± 0.0003 | 30.832 ± 0.039 | 0.8802 ± 0.0004 | 33.878 ± 0.039 |
| &nbsp;&nbsp;seed `rep_qat_s0` | 35.751 | 0.9478 | 31.803 | 0.8996 | 30.792 | 0.8798 | 33.839 |
| &nbsp;&nbsp;seed `rep_qat_s1` | 35.836 | 0.9480 | 31.887 | 0.9003 | 30.871 | 0.8806 | 33.917 |
| **R3 + QAT** (n=2) | 36.051 ± 0.146 | 0.9505 ± 0.0010 | 32.048 ± 0.074 | 0.9025 ± 0.0010 | 30.962 ± 0.049 | 0.8824 ± 0.0009 | 34.116 ± 0.089 |
| &nbsp;&nbsp;seed `plainA_qat_s0` | 35.906 | 0.9495 | 31.974 | 0.9015 | 30.913 | 0.8815 | 34.027 |
| &nbsp;&nbsp;seed `plainA_qat_s1` | 36.197 | 0.9515 | 32.123 | 0.9035 | 31.010 | 0.8833 | 34.205 |
| **R4 + QAT** (n=2) | 35.934 ± 0.157 | 0.9497 ± 0.0013 | 31.968 ± 0.110 | 0.9015 ± 0.0016 | 30.895 ± 0.073 | 0.8813 ± 0.0013 | 34.029 ± 0.129 |
| &nbsp;&nbsp;seed `repA_qat_s0` | 35.776 | 0.9484 | 31.857 | 0.8999 | 30.822 | 0.8800 | 33.900 |
| &nbsp;&nbsp;seed `repA_qat_s1` | 36.091 | 0.9510 | 32.078 | 0.9030 | 30.968 | 0.8826 | 34.157 |

| Gain (mean over seeds) | Set5 PSNR | Set5 SSIM | Set14 PSNR | Set14 SSIM | BSD100 PSNR | BSD100 SSIM | val42 PSNR |
|---|---|---|---|---|---|---|---|
| PTQ -> QAT, plain: R1q - R1 | +1.122 | +0.0150 | +0.610 | +0.0137 | +0.492 | +0.0128 | +1.046 |
| PTQ -> QAT, rep: R2q - R2 | +3.400 | +0.0857 | +1.987 | +0.0827 | +1.541 | +0.0690 | +2.861 |
| deployed -> new plain+QAT: R1q - R0 | +0.481 | +0.0044 | +0.310 | +0.0044 | +0.218 | +0.0037 | +0.380 |
| rep blocks (INT8): R2q - R1q | +0.385 | +0.0033 | +0.189 | +0.0024 | +0.139 | +0.0020 | +0.216 |
| anchor on plain (INT8): R3q - R1q | +0.642 | +0.0059 | +0.392 | +0.0050 | +0.269 | +0.0042 | +0.454 |
| anchor on rep (INT8): R4q - R2q | +0.140 (within noise) | +0.0018 | +0.122 | +0.0015 (within noise) | +0.064 (within noise) | +0.0011 (within noise) | +0.151 |
| rep on anchor (INT8): R4q - R3q | -0.118 (within noise) | -0.0008 (within noise) | -0.081 (within noise) | -0.0011 (within noise) | -0.066 (within noise) | -0.0011 (within noise) | -0.087 (within noise) |
| rep+QAT vs deployed: R2q - R0 | +0.866 | +0.0077 | +0.498 | +0.0069 | +0.356 | +0.0057 | +0.597 |
| anchor+QAT vs rep+QAT: R3q - R2q | +0.258 | +0.0026 | +0.203 | +0.0025 | +0.130 | +0.0022 | +0.238 |
| plain+anchor+QAT vs deployed: R3q - R0 | +1.124 | +0.0103 | +0.701 | +0.0094 | +0.487 | +0.0079 | +0.835 |
| everything: R4q - R0 | +1.006 | +0.0095 | +0.621 | +0.0083 | +0.420 | +0.0068 | +0.747 |

## Reference points

| | Set5 | Set14 | BSD100 / BSD200 |
|---|---|---|---|
| bicubic (this project, PSNR-Y / SSIM-Y) | 33.67 / 0.9303 | 30.32 / 0.8698 | 29.56 / 0.8434 |
| FSRCNN paper, bicubic row (PSNR) | 33.66 | 30.23 | 29.70 (BSD200) |
| FSRCNN-s (PSNR / SSIM; 91+General-100) | 36.58 / 0.9532 | 32.28 / 0.9052 | 31.48 / 0.9027 (BSD200) |
| FSRCNN (PSNR / SSIM; 91+General-100) | 37.00 / 0.9558 | 32.63 / 0.9088 | 31.80 / 0.9074 (BSD200) |

FSRCNN numbers: arXiv 1608.00367, Tables 4 and 6 (read from the paper). FSRCNN used BSD200, not BSD100, so that column is not comparable image for image.
