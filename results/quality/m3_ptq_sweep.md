# M3 PTQ sweep (12 validation images, PSNR-Y, calibration = 100 training crops)

FP32 reference on the same images: 34.954 dB

| percentile | weights | PSNR-Y int8 | drop vs FP32 (dB) |
|---|---|---|---|
| 99.0 | per-layer | 29.648 | 5.307 |
| 99.9 | per-layer | 34.529 | 0.425 |
| 99.99 | per-layer | 34.731 | 0.223 |
| 100.0 | per-layer | 34.675 | 0.280 |
| 99.0 | per-channel | 29.600 | 5.354 |
| 99.9 | per-channel | 34.440 | 0.514 |
| 99.99 | per-channel | 34.647 | 0.307 |
| 100.0 | per-channel | 34.542 | 0.413 |
