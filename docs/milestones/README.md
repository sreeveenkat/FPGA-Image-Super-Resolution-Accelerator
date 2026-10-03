# FPGA Super-Resolution on ZedBoard — Milestone Guide

Read this file first. Then do the milestones **in order**, one file at a time.

## 1. Final scope (no 4K)

We drop 4K. It is not realistic on the XC7Z020 (220 DSPs). The new targets are:

| Target | Input → Output | Scale | Why |
|---|---|---|---|
| **Main goal** | **960×540 → 1920×1080 (1080p)** | ×2 | Output can be shown on the ZedBoard HDMI port |
| Development size | 64×64 → 128×128 | ×2 | Tiny images make debugging and simulation fast |
| Stretch goal | 480×270 → 1920×1080 | ×4 | Only after the main goal works |

Everything in these files uses the **×2 network** (3 colour channels in, 12 channels out, pixel-shuffle to ×2).

## 2. The big picture in one paragraph

A small image goes in. A small neural network (CNN) guesses the missing detail and makes an image twice as wide and
twice as tall. We first build and train the network on a PC (Python). Then we turn it into plain integer maths (INT8).
Then we build a hardware circuit (Verilog) on the FPGA that does exactly the same integer maths. The ARM processor on the
board feeds it the image and collects the result. Finally we measure quality and speed.

```
 PC (Python)                                    ZedBoard
 ───────────                                    ────────
 M1 baseline (bicubic)                          M0 learn ARM + AXI + DMA
 M2 train CNN (FP32)
 M3 INT8 + integer model ──weights──►           M4 conv engine (RTL)
                                                M5 full network (RTL)
                                                M6 ARM driver + DMA
                                                M7 measure & report
```

## 3. Milestone list

| # | File | What you build | Output you get | Time |
|---|---|---|---|---|
| M0 | [M0_zynq_basics.md](M0_zynq_basics.md) | Learn PS/PL, AXI, DMA | UART text, LEDs, own register, DMA round-trip | 1–1.5 wk |
| M1 | [M1_software_baseline.md](M1_software_baseline.md) | Bicubic upscaling + quality metrics | PSNR/SSIM numbers (the "floor") | 1 wk |
| M2 | [M2_train_fp32_cnn.md](M2_train_fp32_cnn.md) | Train the CNN in PyTorch | Model that beats bicubic | 1.5–2 wk |
| M3 | [M3_int8_quantization.md](M3_int8_quantization.md) | INT8 weights + integer Python model | Weight files + "golden" model for RTL | 1–1.5 wk |
| M4 | [M4_conv_engine_rtl.md](M4_conv_engine_rtl.md) | One conv layer in Verilog | RTL output = Python output, bit-exact | 2–3 wk |
| M5 | [M5_full_network_rtl.md](M5_full_network_rtl.md) | All layers + pixel shuffle + tiles | Whole-tile RTL matches golden model | 2–3 wk |
| M6 | [M6_axi_dma_arm_driver.md](M6_axi_dma_arm_driver.md) | Registers, DMA, ARM C program | Full image upscaled on the board | 1.5–2 wk |
| M7 | [M7_benchmark_and_report.md](M7_benchmark_and_report.md) | Measurements + README + demo | Quality/speed/resource tables | 1–2 wk |
| M8 | [M8_optional_extensions.md](M8_optional_extensions.md) | Extras (HDMI, ×4, ray tracer, custom multiplier) | Optional | — |

Core project (M0–M7): roughly **3–4 months** at 5–6 hours/day.

## 4. Golden rules

1. **Never start a milestone before the previous exit checklist is fully ticked.** A skipped check becomes a mystery bug
   two milestones later.
2. **One reference chain**: PyTorch FP32 → integer Python model → RTL. RTL is compared with the *integer Python model*.
3. **Test small first.** 64×64 images before 960×540. One layer before five layers.
4. **Write down numbers.** Keep a `results.md` and add measured values as you go. Do not claim anything you did not measure.
5. If stuck for more than 2 days on one bug, shrink the problem (smaller image, one layer, one pixel) and ask for help.

## 5. Tools you need (install once)

- Vivado + Vitis 2024.x (free WebPACK supports XC7Z020) and the ZedBoard board files
- Python 3 with: `torch`, `numpy`, `opencv-python`, `scikit-image`, `matplotlib`
- Icarus Verilog (or Verilator) and `cocotb` for simulation
- A serial terminal (`screen` or `minicom` on Linux), git

## 6. Board facts (XC7Z020, ZedBoard)

| Item | Value |
|---|---|
| LUTs / FFs | 53,200 / 106,400 |
| Block RAM | 140 × 36 Kb (≈ 630 KB) |
| DSP48E1 | 220 |
| DDR3 | 512 MB (attached to the ARM side, PS) |
| ARM | Dual Cortex-A9 |
| Practical PL clock | 100 MHz to start (try 150 MHz later) |
| Display | HDMI up to 1080p |
