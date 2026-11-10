# Related work: comparison table of FPGA super-resolution accelerators

Written 2026-11-10; rows 11-12 updated with the board measurements of the same day (`results/board/2026-11-10/SUMMARY.md`). Every number has a source. "Read" says how: **full** = the full paper was read here; **secondary** = taken
from another paper's comparison table (the original was NOT read: check before publishing); **abstract** = abstract only.
Nothing is filled in from memory. Our own rows come from `results/board/2026-10-28/SUMMARY.md`, `results/power_estimate/SUMMARY.md`,
the routed pipeline reports and `software/analysis/cycle_model.py` Part 6 (v2 = prediction).

## Main table (FPGA designs)

| # | Work | Device (board) | Method | In -> out | fps | Clock | DSP used | LUT | Set5 / Set14 / BSD100 PSNR-Y (dB) | Power | Read |
|---|---|---|---|---|---|---|---|---|---|---|---|
| 1 | Kim, Choi, Kim, TCAS-II 65(9) 2018 [K18b] | XCKU040 | edge-orientation linear mapping (not a CNN) | -> 3840x2160 (x2) | 60 | 150 MHz | 108 | 3K | 34.78 / 31.63 / 30.48 | n/s | secondary (TODAES T6) |
| 2 | Kim, Choi, Kim, TCSVT 29(8) 2019 [K19] | XCKU040 | CNN, 14-bit fixed | -> 3840x2160 (x2) | 60 | 150 MHz | 1920 | 151K | 36.64 / 32.47 / 31.31 | n/s | secondary (TODAES T6) |
| 3 | Chang, Kang, Kang, TCSVT 30(1) [C18] | XC7K410T | deconvolution CNN, 13-bit fixed | -> 2880x1280 | 62.7 | 130 MHz | 1512 | 167K | 36.40 / 32.21 / 31.15 | n/s | secondary (TODAES T6) |
| 4 | Sun et al., TCSVT 32(4) 2021 [S21] | XCKU15P | residual recurrent NN (video), 16-bit | -> 3840x2160 | 76 | 160 MHz | 1820 | 98K | 36.76 / 32.51 / 31.31 | n/s | secondary (TODAES T6) |
| 5 | He et al., FCCM 2018, pp. 181-188 [H18] | XC7Z045 (ZC706) | FSRCNN-s, **fully layer-pipelined**, per-layer DSP allocation, 16-bit fixed; only 25.3 % of 30x30 blocks go through the CNN, the rest bilinear | 1920x1080 -> 3940x2160 | 31.7 (3 interpolators) | 100 MHz | 858 (95 %) | 103.7K (47 %) | not on Set5; 37.36 dB (Y) on SJTU 4K video (CNN only: 38.55) | n/s | **full** |
| 6 | Liu et al., ACM TODAES 29(3) art. 53, 2024 [L24], KV260 | XCK26 (Kria KV260) | LAPAR-derived CNN, 103K params, 8-bit, Y channel only (ARM does colour) | 960x540 -> 1920x1080 | 35.79 (27.94 ms) | 200 MHz (DSP 400 MHz) | 1210 (97 %) | 65K (56 %) | 37.14 / 32.15 / 31.52 | **16.85 W board, power meter** | **full** |
| 7 | same [L24], ZCU104 | XCZU7EV | same | 1280x720 -> 2560x1440 | 25.16 | 250 MHz (DSP 500) | 1211 | 69K | same | 23.81 W board | **full** |
| 8 | Manabe, Shibata, Oguri, IEICE Trans. Fund. E101-A(12) 2018, pp. 2280-2289 [M18] | n/s | CNN with flips + residue number system, LUT arithmetic | 960x540 -> 1920x1080 | 60 (< 1 ms latency) | n/s | n/s | n/s | n/s | n/s | abstract |
| **9** | **Ours, R0 (tiled, deployed)** | **XC7Z020 (ZedBoard)** | 2,620-param CNN, INT8, RGB | **960x540 -> 1920x1080** | **0.762** | 100 MHz | 68 | 5,146 (sys) | 35.02 / 31.40 / 30.53 | 1.91 W chip (Vivado estimate, not measured) | board-measured |
| **10** | **Ours, pipeline** | **XC7Z020 (ZedBoard)** | same network + anchor (R3q), whole-frame layer pipeline, INT8, RGB | **960x540 -> 1920x1080** | **10.49** (95.36 ms); 14.18 (70.52 ms, non-cacheable buffers) | 125 MHz | 170 (77 %) | 9,888 (19 %, sys) | 36.20 / 32.12 / 31.01 | 2.22 W chip (Vivado SAIF estimate, not measured) | board-measured |
| 11 | Ours, pipeline v2 | XC7Z020 | same, 8 cycles/px, 118 LUT multipliers | same | **27.1** (36.95 ms, NC buffers); 16.2 cached | 125 MHz | 220 (100 %) | 20,651 (39 %) | same | 2.90 W chip (Vivado vectorless) | **board-measured 2026-11-10** |
| 12 | Ours, pipeline v2 packed | XC7Z020 | same, two INT8 products per DSP48E1 | same | **27.1** (36.96 ms, NC buffers); 16.2 cached | 125 MHz | 190 (86 %) | 13,323 (25 %) | same | 2.51 W chip (Vivado vectorless) | **board-measured 2026-11-10** |

n/s = not stated in what was read. Rows 1-4 are copied from Table 6 of [L24] and should be checked in the originals before the
paper is submitted. [L24] row 6 measures board power with a power meter (its Fig. 13a); ours is not measured yet.

ASIC reference points (not FPGA, not in the main table): ACNPU [Y24], TSMC 40 nm, 1080p x2 at 31.7 fps, 0.1318 W, Set5 37.34 (read:
arXiv HTML v1, full); Huang et al. ISCAS 2022 tilted layer fusion, 40 nm synthesis, 640x360 -> 1080p x3 at 60 fps, no PSNR table
(read: arXiv HTML v1, full).

## Derived numbers (computed here from the table; same definitions for every row)

Output megapixels per second per DSP = out_w x out_h x fps / 1e6 / DSP. It favours small networks, so it is shown with the network size.

| Row | Output MP/s | MP/s per DSP | Note |
|---|---|---|---|
| 1 Kim TCAS-II (not CNN) | 497.7 | 4.61 | no CNN: not comparable |
| 2 Kim TCSVT | 497.7 | 0.259 | |
| 3 Chang | 231.1 | 0.153 | |
| 4 Sun | 630.4 | 0.346 | |
| 5 He (PKU) | 269.8 | 0.314 | 75 % of blocks bilinear |
| 6 Liu KV260 | 74.2 | 0.061 | larger network (103K params) |
| 10 Ours pipeline | 21.8 (29.4 NC) | 0.128 (0.173 NC) | 2,620 params |
| 11 Ours v2 (measured) | 56.1 | 0.255 | 220 DSP |
| 12 Ours v2 packed (measured) | 56.1 | 0.295 | 190 DSP |

DSP efficiency, [L24] Table 7 definition (GOPS/DSP; 2 ops per MAC): Qiu 2016 XC7Z045 0.18, Xiao 2017 XC7Z045 0.28, Ma 2017
Arria-10 0.30, HybridDNN PYNQ-Z1 0.38, [L24] KV26 0.82 (DSP at 400 MHz), ZU7EV 1.02 (500 MHz). Ours: compute part 2 x 1.327 G MAC
/ 67.19 ms = 39.5 GOPS / 170 DSP = **0.23 GOPS/DSP at 125 MHz**; end to end (95.36 ms) 27.8 GOPS = 0.16. Per DSP per MHz: ours
0.23 / 125 = 1.86e-3, [L24] 0.82 / 400 = 2.05e-3 and 1.02 / 500 = 2.04e-3: **the same per-cycle DSP use (both near 2 ops per DSP
per cycle)**; [L24]'s higher GOPS/DSP comes from the DSP clock (double-pumped, 400-500 MHz on UltraScale+), not from busier DSPs.
v2 (model): 2 x 1.327 G / 33.6 ms ~ 79 GOPS on 220 DSP + 118 LUT multipliers.

## Honest reading

Where we are NOT better:
* **Speed**: every CNN row runs 25-76 fps; ours 10.5 (14.2 NC), v2 predicted 27. Manabe [M18] does our exact task at 60 fps.
* **Image quality**: Set5 36.20 dB is below [L24] 37.14, [S21] 36.76, [K19] 36.64 and about level with [C18] 36.40. Only the
  non-CNN [K18b] (34.78) is lower. (Our BSD100 protocol re-aligns odd-sized images, so BSD100 differs slightly from literature;
  Set5 uses the standard LR and matches published bicubic.)
* **Novelty of the layer pipeline**: [H18] is already a fully layer-pipelined CNN with per-layer DSP allocation on a Zynq.

Where we can make a defensible claim (each needs the exact wording):
* **Smallest resources and cheapest device** in the table: 170 DSP / 9.9K LUT (whole system) vs 858-1920 DSP and 65-167K LUT for
  the other CNN designs; the only one on a Zynq-7020.
* **Same per-cycle DSP efficiency as the 2024 state of the art** ([L24], same definition), on a 7-series part at 125 MHz.
* **Evidence**: end-to-end board timing including the ARM and DMA, byte-exact against a golden integer model on all 119 test
  images, mutation-tested RTL. None of the papers read here report a bit-exact check of the hardware output.
* **Possible energy claim, NOT YET MEASURED**: [L24] reports 2.12 fps/W at 16.85 W board power. If the ZedBoard draws about 5 W
  while running, the pipeline would reach ~2 fps/W (10.5 fps) or ~2.8 (14.2 fps), and v2 ~5. This needs the board power
  measurement; do not claim it before.

## References (as printed in the papers read)

* [K18b] Y. Kim, J.-S. Choi, M. Kim, "2X super-resolution hardware using edge-orientation-based linear mapping for real-time 4K UHD 60 fps video applications," IEEE TCAS-II, 65(9):1274-1278, 2018. (cited from [L24])
* [K19] Y. Kim, J.-S. Choi, M. Kim, "A real-time convolutional neural network for super-resolution on FPGA with applications to 4K UHD 60 fps video services," IEEE TCSVT, 29(8):2521-2534, 2019. (cited from [L24]/[Y24]; full text not reachable here)
* [C18] J.-W. Chang, K.-W. Kang, S.-J. Kang, "An energy-efficient FPGA-based deconvolutional neural networks accelerator for single image super-resolution," IEEE TCSVT, 30(1):281-295. (cited from [L24]; year printed as 2018)
* [S21] K. Sun, M. Koch, Z. Wang, S. Jovanovic, H. Rabah, S. Simon, "An FPGA-based residual recurrent neural network for real-time video super-resolution," IEEE TCSVT, 32(4):1739-1750, 2021. (cited from [L24])
* [H18] Z. He, H. Huang, M. Jiang, Y. Bai, G. Luo, "FPGA-based real-time super-resolution system for ultra high definition videos," IEEE FCCM 2018, pp. 181-188, doi 10.1109/FCCM.2018.00036. (read)
* [L24] H. Liu, Y. Qian, Y. Liang, B. Zhang, Z. Liu, T. He, W. Zhao, J. Lu, B. Yu, "A high-performance accelerator for real-time super-resolution on edge FPGAs," ACM TODAES, 29(3), Article 53, May 2024, doi 10.1145/3652855. (read)
* [M18] T. Manabe, Y. Shibata, K. Oguri, "FPGA implementation of a real-time super-resolution system using flips and an RNS-based CNN," IEICE Trans. Fundamentals, E101-A(12):2280-2289, 2018, doi 10.1587/transfun.E101.A.2280. (abstract; full text behind J-STAGE subscription)
* [Y24] T.-H. Yang, T.-S. Chang, "ACNPU: A 4.75TOPS/W 1080P@30FPS super resolution accelerator with decoupled asymmetric convolution," IEEE TCAS-I, 71(2):670-679, 2024. (read: arXiv v1)

Not reachable here (need college library access): full text of [K19] (IEEE Xplore), [M18] (J-STAGE). Ask the professor or the
library for these two; [M18] is the closest prior work (same task).
