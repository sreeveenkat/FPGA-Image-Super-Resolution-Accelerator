# Side-by-side crops (rule-based picks)

R2q = `rep_qat_s1` (val42 33.917 dB), R3q = `plainA_qat_s1` (val42 34.205 dB); deployed = qparams.npz. INT8 integer model. Crop = 96x96 HR window where the models differ most, shown 4x (nearest).

| pick | image | bicubic | deployed | R2q | R3q | window (y,x) |
|---|---|---|---|---|---|---|
| gain | BSD100/42049 | - | 32.92 | 34.75 | 35.11 | (224,224) |
| median | Set5/baby | - | 38.02 | 38.29 | 38.45 | (344,0) |
| worst | BSD100/86068 | - | 29.58 | 29.56 | 29.65 | (136,184) |
| anchor | Set5/butterfly | - | 29.22 | 30.87 | 31.54 | (144,160) |

Whole-image PSNR-Y (dB) in the table; the crops are in `results/images/ladder_crops_*.png` (git-ignored, regenerate with this script).
