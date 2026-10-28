# FPGA Image Super-Resolution Accelerator: Complete Project Guide

*Updated 28 October 2026, after the second board session. Session 1 (27 Oct): all six bitstreams ran on the board at a 100 MHz PL clock, every output byte-exact. Session 2 (28 Oct): VERSION-refusal controls passed, and the three 125 MHz designs (r0_125, r3q_125, pipe) ran at a read-back 125.000 MHz, byte-exact on all 119 images each. One board, one temperature range (47.9–49.2 °C), no margin sweep. Power is still not measured.*

This guide explains the whole project from zero: what it is, every concept you need, every step that was done, every result, and what is still left. It assumes you know nothing. Read it in order the first time.

**Important rule used throughout:**
- **Measured** = a real number from the board or a real test run.
- **Simulated** = from a Verilog simulation (exact, but not yet on the board).
- **Predicted / model** = from a calculation (an estimate).

Never write a predicted number in the report as if it were measured.

---

## Table of contents

1. [The project in one paragraph](#1-the-project-in-one-paragraph)
2. [Basic concepts you must know](#2-basic-concepts-you-must-know)
3. [The neural network](#3-the-neural-network)
4. [From PyTorch to integers: quantization](#4-from-pytorch-to-integers-quantization)
5. [Version 1 hardware: the tile engine design (R0)](#5-version-1-hardware-the-tile-engine-design-r0)
6. [How the design is verified](#6-how-the-design-is-verified)
7. [Why version 1 is slow: the gap analysis](#7-why-version-1-is-slow-the-gap-analysis)
8. [Comparison with PC and GPU](#8-comparison-with-pc-and-gpu)
9. [Improving image quality (R1 to R4)](#9-improving-image-quality-r1-to-r4)
10. [The anchor trick (R3q)](#10-the-anchor-trick-r3q)
11. [Higher clock: 125 MHz (r0_125, r3q_125)](#11-higher-clock-125-mhz-r0_125-r3q_125)
12. [Version 2 hardware: the layer pipeline](#12-version-2-hardware-the-layer-pipeline)
13. [The deadlock bug and what it teaches](#13-the-deadlock-bug-and-what-it-teaches)
14. [All six bitstreams at a glance](#14-all-six-bitstreams-at-a-glance)
15. [The board session](#15-the-board-session)
16. [Power measurement](#16-power-measurement)
17. [Publishing a paper](#17-publishing-a-paper)
18. [Honesty and AI use](#18-honesty-and-ai-use)
19. [Where everything is in the repository](#19-where-everything-is-in-the-repository)
20. [What is done and what is left](#20-what-is-done-and-what-is-left)
21. [Viva / interview questions with answers](#21-viva--interview-questions-with-answers)
22. [Glossary](#22-glossary)

---

## 1. The project in one paragraph

A small neural network (a CNN with 2,620 parameters) takes a low-resolution image (960×540) and makes it twice as large (1920×1080) with sharper edges than ordinary resizing. This is called **image super-resolution (SR)**. The network was trained in PyTorch, converted to 8-bit integers (INT8), and then built as custom hardware in Verilog on a **Zynq-7020 FPGA** (on a **ZedBoard**). The ARM processor on the same chip controls the hardware and moves image data with DMA. The special strength of the project is **verification**: the board output is proven to be **byte-for-byte identical** to a software reference model on 119 standard test images.

---

## 2. Basic concepts you must know

### 2.1 What is super-resolution?
Making an image bigger. Normal resizing (**bicubic interpolation**) just blends neighbouring pixels, so the result looks blurry. A neural network learns from many example images how sharp edges should look, so it can produce a sharper result.

### 2.2 What is a CNN?
A **convolutional neural network**. Each layer slides small filters (for example 3×3) over the image. Each filter output is a sum of **multiply-accumulate (MAC)** operations: multiply pixel × weight, add everything up. A CNN is basically a huge number of MACs, which is why special hardware helps.

### 2.3 What is an FPGA?
A chip whose logic you can design yourself. You write Verilog, a tool (Vivado) turns it into a **bitstream** file, and loading the bitstream configures the chip. Resources inside the FPGA:

| Resource | What it is | Zynq-7020 has |
|---|---|---|
| **LUT** | small piece of general logic | 53,200 |
| **FF** (flip-flop) | stores one bit for one clock cycle | 106,400 |
| **DSP** (DSP48E1) | a hard-wired multiplier + adder block, fast and low-power | **220** |
| **BRAM** | on-chip memory blocks | 140 (36 Kb tiles) |

### 2.4 What is a Zynq?
A chip with **two parts**:
- **PS** (Processing System): two ARM Cortex-A9 cores. Runs normal C programs.
- **PL** (Programmable Logic): the FPGA part, where our accelerator lives.

They talk over **AXI** buses:
- **AXI-Lite**: for small control registers (start, status, VERSION, CYCLES).
- **AXI DMA**: moves large image data between DDR memory and the PL without the CPU copying it.

### 2.5 What is the ZedBoard?
A development board with the Zynq-7020, DDR memory, a 12 V power input, a USB-JTAG port (to load bitstreams and programs) and a USB-UART port (console messages).

### 2.6 Image quality metrics
- **PSNR** (Peak Signal-to-Noise Ratio, in dB): higher = closer to the original sharp image. +0.1 dB is small, +1 dB is a big improvement.
- **SSIM**: structural similarity, 0 to 1, higher is better.
- Standard practice (we follow it): measure on the **Y channel** (brightness) and cut a 2-pixel border.

### 2.7 Test images
- **Set5** (5 images), **Set14** (14), **BSD100** (100). Together = **119 images**. These are the standard benchmark sets used in SR papers.
- **DIV2K** and **Flickr2K**: large high-quality image sets used for **training**.

---

## 3. The neural network

- 4 convolution layers: **L1, L2, L3, L4**.
- **2,620 parameters** (weights + biases). Very small. (Famous FSRCNN has about 12,000.)
- About **2,560 MACs per low-resolution pixel**. For one 960×540 frame: 2,560 × 960 × 540 ≈ **1.33 billion MACs**.
- L4 is the most expensive layer: about **67%** of all MACs.
- The last step is **PixelShuffle**: L4 produces several channels per low-res pixel, and PixelShuffle rearranges them into a 2× bigger image.
- Scale factor: **×2** only.

**Known limit:** a 2,620-parameter network cannot recover fine random texture (grass, fur, fabric). That's normal; say so honestly.

---

## 4. From PyTorch to integers: quantization

### 4.1 Why integers?
PyTorch uses 32-bit floating point (FP32). Floating point hardware is big and slow on an FPGA. **INT8** (8-bit integers) is small and fits the DSP blocks well.

### 4.2 How it works
- Weights and activations are stored as 8-bit integers.
- A layer computes an integer sum (the **accumulator**, `acc`), up to 32 bits wide.
- Then **requantization** scales it back to 8 bits:

```
out = (acc × M + 2^(SHIFT−1)) >> SHIFT      then clamp to the valid range
```

- `M` = an integer multiplier, `SHIFT` = a right shift. Together they act like multiplying by a small fraction.
- `2^(SHIFT−1)` is the **rounding constant** (makes it round to nearest, not round down).
- In this design, `M` can be different per output channel (stored in `mult_Ln.mem`), and `SHIFT` is one value per layer (a Verilog parameter).

### 4.3 PTQ vs QAT
- **PTQ** (post-training quantization): train in FP32, then convert. Simple. The original model (R0) used this.
- **QAT** (quantization-aware training): simulate the INT8 rounding during training so the network learns to cope with it. Better quality. Used for the improved models.

### 4.4 The integer golden model
A NumPy program that does **exactly** the same integer math as the hardware. It is the "truth" that the hardware must match bit-for-bit.

---

## 5. Version 1 hardware: the tile engine design (R0)

### 5.1 Tiles and halo
The image is cut into **tiles** of 64×64 pixels (135 tiles per frame). A 3×3 filter needs neighbouring pixels, so each tile is loaded with an extra **halo** of 3 pixels around it. The halo pixels are computed twice (once per neighbouring tile), about **10%** wasted work.

### 5.2 Four engines, one at a time
There is one hardware **engine per layer** (L1, L2, L3, L4). Each engine has its own DSPs. For each tile:
1. L1 engine runs, L2/L3/L4 wait.
2. Then L2 runs, the others wait.
3. Then L3, then L4.

### 5.3 Numbers (measured / synthesis)

| Item | Value |
|---|---|
| Clock | 100 MHz |
| DSPs used | 68 of 220 |
| BRAM | ~72 of 140 tiles |
| LUT / FF | ~5,300 / ~7,800 |
| Cycles per tile | 926,201 (L1 124,872 · L2 69,713 · L3 69,720 · L4 589,844) |
| **Frame time (measured on board)** | **1.312 s = 0.76 fps** |

The tested bitstream is called **TESTED_0602** (VERSION register 0x53520602).

### 5.4 Engineering lessons found
- **BRAM depth rounding:** memories round up to power-of-two depth, so buffers used more BRAM than expected (32 → 18.5 tiles in one case).
- **PL reprogramming:** re-loading the FPGA while the ARM/DMA was active failed without isolating the PL first.

---

## 6. How the design is verified

This is the project's strongest part. Most student and even many published designs only check "the picture looks right". This project proves exactness.

### 6.1 The reference chain
```
PyTorch model (FP32)
   → integer golden model (NumPy, exact integer math)
      → RTL simulation (Verilog in iverilog / Vivado xsim)
         → board (real hardware)
```
Each step is compared with the previous one.

### 6.2 Bit-exact / byte-exact
"Bit-exact" means **every output pixel value is identical** to the golden model, not just close. On the board, R0 output was byte-exact on **all 119** test images.

### 6.3 Seam test
Because the image is cut into tiles, bugs often appear at tile borders (seams). The seam test runs several tiles and checks the borders match the whole-image result exactly.

### 6.4 Mutation testing
How do you know your tests are good? You **deliberately insert bugs** ("mutants") into the RTL, for example a wrong shift or an off-by-one, and check the test suite catches each one. A mutant that the tests do not catch means the tests have a hole.
- An **equivalent mutant** changes the code but not the behaviour, so it *must* survive. That's expected, not a failure.

### 6.5 Netlist (post-synthesis) simulation
After Vivado synthesizes the design, the resulting gate-level netlist is simulated again. This catches cases where synthesis behaves differently from the RTL simulation.

### 6.6 Counter-wrap rule (added after the deadlock bug, see section 13)
Every counter and pointer in the design must wrap around (overflow) in at least one test.

---

## 7. Why version 1 is slow: the gap analysis

### 7.1 The calculation
- MACs per frame: 1.33 G (1.46 G including halo recomputation).
- Ideal time with 68 DSPs at 100 MHz: 1.33 G / (68 × 100 M) ≈ **0.195 s**.
- Measured: **1.312 s**.
- Efficiency: about **16–17%**. Only about 1 in 6 DSPs is doing useful work on average.

### 7.2 Why
Inside each engine, the DSPs are almost always busy. **But only one of the four engines runs at a time**, so the DSPs of the other three engines sit idle. That's the gap.

### 7.3 Throughput in standard units
1 MAC = 2 operations. 1.33 G × 2 × 0.76 fps ≈ **2 GOPS** (giga-operations per second). Low compared with other Zynq-7020 designs. Reviewers will compute this, so state it yourself.

### 7.4 The cycle model
`software/analysis/cycle_model.py` predicts cycle counts. It matches the simulated cycles of each layer to within 24 cycles, so its predictions can be trusted for planning.

---

## 8. Comparison with PC and GPU

Measured on the PC with `software/analysis/cpu_baseline.py`:

| Platform | Time per frame | Notes |
|---|---|---|
| PC CPU, FP32, 1 thread | 115–129 ms | varies between runs |
| RTX 3050 GPU | 6.7 ms (7.9 ms with copies) | measured ~70 W → about **0.55 J per frame** |
| ARM Cortex-A9 only (test T7) | **13,433 ms** | measured 28 Oct with the ARM timer fixed, byte-exact, one frame, one run (UART host timestamps: 13.423 s). On 27 Oct the program's timer was not enabled and only a host-timed ≈13.4 s (±0.2 s) existed |
| ZedBoard R0 | 1,311.7 ms | measured |
| ZedBoard R0 at 125 MHz (r0_125 / r3q_125) | 1,061.9 / 1,061.7 ms | measured 28 Oct, 125 MHz |
| ZedBoard pipeline at 100 MHz | 112.1 ms | measured 27 Oct |
| **ZedBoard pipeline at 125 MHz** | **95.4 ms (10.5 fps)** | measured 28 Oct, PL clock read back as 125.000 MHz |

**Honest conclusion:** an FPGA this small will never beat a desktop GPU on speed. The fair comparison is:
1. **Same chip with and without the accelerator** (ARM-only vs FPGA), and
2. **Energy per frame** (power × time) for a small, low-power embedded device.

---

## 9. Improving image quality (R1 to R4)

Goal: better pictures **without changing the network shape**, mostly by training better weights.

### 9.1 First, the evaluation was checked
- Low-res test images made with Pillow's anti-aliased bicubic: bit-exact with the official Set5/Set14 files.
- PSNR on Y with a 2-pixel border; HR images cropped to an even size first.
- Our bicubic scores (33.67 / 30.32 / 29.56) are close to the FSRCNN paper's bicubic row (33.66 / 30.23 / 29.70), but only Set5 matches. Set14 is 0.09 dB higher, and the paper's last column is BSD200, not BSD100, so it is not comparable image for image (`results/quality/image_quality_ladder.md`, Reference points). Our LR images are bit-exact with the official ones for all even-sized images (Set5 5/5, Set14 11/11); Set14 and BSD100 contain odd-sized images that were re-aligned on purpose, so they can differ slightly from the literature.
- No test image overlaps with any training image (checked against 3,642 training images).
- Choices were made using **42 clean DIV2K validation images** only; test sets only for final numbers.

### 9.2 The training "ladder"

| Rung | What changes |
|---|---|
| R0 | the original deployed model (PTQ) |
| R1 | more data (DIV2K + Flickr2K), flips/rotations, L1 loss, better schedule |
| R2 | + **re-parameterization**: extra parallel branches during training, merged back into one normal 3×3 conv afterwards, so the hardware is unchanged |
| R3 | + **anchor** residual (see section 10), plain network |
| R4 | rep + anchor together |
| "q" | after QAT (e.g. R2q = R2 + QAT) |

### 9.3 Final results: INT8 on the integer model, mean of 2 seeds (PSNR-Y / SSIM-Y)

| Model | Set5 | Set14 | BSD100 |
|---|---|---|---|
| bicubic | 33.67 / 0.9303 | 30.32 / 0.8698 | 29.56 / 0.8434 |
| R0 (2-seed mean: deployed checkpoint + one retrain) | 34.93 / 0.9402 | 31.35 / 0.8931 | 30.48 / 0.8745 |
| **R2q** (rep + QAT, no logic change) | 35.79 / 0.9479 | 31.85 / 0.9000 | 30.83 / 0.8802 |
| **R3q** (plain + anchor + QAT) | **36.05 / 0.9505** | **32.05 / 0.9025** | **30.96 / 0.8824** |
| R4q (rep + anchor + QAT) | 35.93 / 0.9497 | 31.97 / 0.9015 | 30.90 / 0.8813 |

The deployed R0 checkpoint alone scores 35.02 / 31.40 / 30.53 (PSNR-Y, `results/quality/table_a_x2.md`); the R0 row is the 2-seed mean so that it is compared with the other rungs on equal terms.

**What it means:**
- Gain over bicubic on Set5 went from **+1.26 dB (R0, 2-seed mean) to +2.38 dB (R3q)**.
- Better data and training gave the biggest single step.
- Re-parameterized weights **collapse under PTQ** (Set5 drops to about 32.4 dB), so QAT is mandatory for them.
- Rep and anchor don't add up; the best is plain + anchor + QAT (**R3q**).
- R3q beat R2q on 118 of 119 images, with both seeds of R3q above both seeds of R2q.
- Visual check: new models remove edge ringing and give sharper edges; fine texture is still not recovered.

### 9.4 Safety checks for new weights
- Accumulators: worst case fits easily in 32 bits (11–15 bits headroom).
- Requantizer product (acc × M): at most 37 bits (worst-case bound, R3q layer 4) of the 49 available.
- New SHIFT values: R2q 22/22/21/22, R3q 22/22/21/25 (R0 was 24/23/21/24).
- Weights are built into the bitstream (`$readmemh`), so **every new model needs a Vivado rebuild**.

---

## 10. The anchor trick (R3q)

### 10.1 The idea
Instead of making the network produce the whole output pixel, it produces only a **correction** (residual) that is **added to the nearest input pixel**. Learning a small correction is easier, so quality improves. This idea comes from **ABPN** (mobile SR, CVPR 2021 workshops).

### 10.2 The clever hardware part (learn this for your viva)
The normal requantizer computes:
```
(acc × M + 2^(S−1)) >> S
```
If you also add `p × 2^S` (p = the anchor pixel) **before** the shift:
```
(acc × M + 2^(S−1) + p × 2^S) >> S   =   requantized value + p
```
This is exact, because `p × 2^S` is a whole multiple of `2^S`, so it does not touch the low bits that decide the rounding. So the addition costs **no extra adder, no extra pipeline stage and no extra cycle**. The clamp to 0–255 is still applied after.

### 10.3 Cost (synthesis)
About **+33 to +45 LUT and +66 FF, 0 DSP, 0 BRAM**. The cycle count is unchanged.

### 10.4 Verification
Seam tests, anchor-specific requantizer and layer-4 tests, a randomized saturating test, 26 mutants (all caught, 1 equivalent survives correctly), and netlist simulation checked against the anchored golden tile.

---

## 11. Higher clock: 125 MHz (r0_125, r3q_125)

- One extra register was added in the multiply path so the design meets timing at **125 MHz** (it uses the DSP's internal input register where possible).
- r0_125 timing: WNS +0.632 ns (positive = timing met).
- Cost: +4 cycles per tile (926,205 instead of 926,201).
- **Predicted** frame time: 1,061.8 ms (0.94 fps), about 1.24× faster than R0 (+24%).
- 150 MHz was not pursued: it needs more changes for only about 1.2× more.
- **r3q_125** = R3q (best quality) at 125 MHz. Built, simulated, and measured on the board on 28 Oct (see below).

**Board finding (27 Oct):** every run of that session was actually at **100 MHz**. The init script used by `run_board.tcl` was generated for 100 MHz and sets the clock divisors after the bitstream is loaded (read back: DIV0=5, DIV1=2). The 125 MHz designs were byte-exact at 100 MHz and gave the same tile times as their 100 MHz versions.

**Real 125 MHz runs (28 Oct):** each design was run with its **own XSA's `ps7_init.tcl`** (the three are byte-identical, md5 `d2a7789c…`). It differs from the platform script (md5 `86bd78c7…`) in one register value only, `FPGA0_CLK_CTRL` (0xF8000170): `0x00200500` → `0x00200400`, i.e. DIVISOR0 5 → 4. Before every run the script read the clock registers back: `FPGA0_CLK_CTRL = 0x00200400`, `IO_PLL_CTRL` FDIV = 30, PLL locked, so FCLK0 = 33.333 MHz × 30 / (4 × 2) = **125.000 MHz**; it refuses to run otherwise. Vivado timing of the three builds was met (WNS +0.632 / +0.393 / +0.267 ns, WHS +0.032 / +0.025 / +0.014 ns, TNS 0).

| Design | T3 20-frame mean / min / max | fps | 119 images | Predicted |
|---|---|---|---|---|
| r0_125 | 1,061.85 / 1,061.26 / 1,062.96 ms | 0.942 | 119/119 byte-exact | 1,061.8 ms |
| r3q_125 | 1,061.68 / 1,061.26 / 1,063.29 ms | 0.942 | 119/119 byte-exact | about 1,062 ms |
| pipe | 95.36 / 95.19 / 96.79 ms | 10.49 | 119/119 byte-exact | 95.2 ms |

All three agree with the model within 0.2 %; the cycle counts are unchanged from 100 MHz, so the gain is the clock (tiled 1.235×). **Limits of this result:** one board, die temperature 47.9–49.2 °C, no voltage or temperature margin sweep, no long soak. It shows that the three builds run correctly at 125 MHz on this board, not how much margin they have.

---

## 12. Version 2 hardware: the layer pipeline

### 12.1 The idea
Fix the gap from section 7: let **all four layers work at the same time** on different parts of the image, like an assembly line. Each layer gets a number of DSPs in proportion to its work.

### 12.2 How it works
- **Line buffers:** each layer keeps only the last few rows of its input in memory (a 3×3 filter needs 3 rows), instead of whole tiles. Uses little BRAM and **removes the halo recomputation**.
- **Inter-stage FIFOs:** small queues between layers so a fast layer can wait for a slow one.
- **Anchor FIFO:** holds input pixels until L4 needs them for the anchor addition (4,096 deep).
- Uses the **R3q weights with the anchor**, at **125 MHz**.

### 12.3 Numbers

| Item | Value | Type |
|---|---|---|
| DSPs | 170 of 220 | synthesis |
| Timing | built for 125 MHz, WNS +0.267 ns | timing met |
| **Clock on the board** | **100 MHz on 27 Oct, 125.000 MHz on 28 Oct** | measured read-back both days |
| Cycles per 960×540 frame | 8,398,481 (sim) / 8,398,491–8,398,508 (board) | **simulation and board agree to within 27 cycles (0.0003%)** |
| Golden-tile cycles | 74,641 (sim) / 74,651–74,654 (board) | agree to within 13 cycles |
| Core compute time at 100 MHz | 8.40 M cycles / 100 MHz ≈ 84.0 ms | calculated from measured cycles |
| PL time per frame | 106.4 ms (~22 ms outside the core cycles, not yet explained) | measured |
| **End-to-end frame time, 100 MHz (27 Oct)** | **112.1 ms mean (112.0–113.6), ≈ 8.9 fps** | **measured, 20 frames** |
| **End-to-end frame time, 125 MHz (28 Oct)** | **95.36 ms mean (95.19–96.79), ≈ 10.5 fps; core 67.2 ms + 28.2 ms overhead** | **measured, 20 frames** |
| Byte-exact | **119/119 test images** at 100 MHz and again at 125 MHz, full frame, error-recovery test (T5, 100 MHz) | measured |
| Output checksum | 0x45dd4e2d (same as R3q) | measured |
| DSP efficiency (core) | 1.33 G MACs / (170 × 8.40 M) ≈ **93%** | calculated |
| Die temperature | 42–50.3 °C | measured |

**Measured speed-up: 11.7× over R0 with the PL at the same 100 MHz clock in both runs, and about 120× over the ARM alone (ARM-only time is host-timed, ±0.2 s).** So the speed-up over R0 comes from the architecture, not from the clock. At 125 MHz (28 Oct) the pipeline is 13.8× faster than R0 at 100 MHz and about 140× faster than the ARM alone; throughput about 28 GOPS end to end. DSP efficiency goes from about 16% to about 93%. Throughput: about **24 GOPS** end to end (R0: about 2 GOPS).

**Where the 95.4 ms go at 125 MHz (28 Oct, from the logs):** the frame time is exactly the sum of two timed parts: ARM padding of the input before the DMA (5.79 ms) + the wait for DMA and compute (89.57 ms). The core needs 8,398,495 cycles = 67.19 ms, so 28.2 ms are overhead: 5.79 ms ARM padding + 22.4 ms inside the DMA wait that is not core cycles (by the driver code this window also contains the cache flush of the input and output buffers, the DMA set-up, polling latency and the cache invalidate of the output; the split is not measured). The 22.4 ms is the same at 100 MHz (106.4 − 84.0 ms), so it is not PL-clock time. **A timing build (28 Oct, flagged driver, 125 MHz, 20-frame means) split it:** flush of the input buffer 2.86 ms, flush of the output buffer 9.57 ms, DMA set-up + START 0.0025 ms, the wait loop 67.188 ms (equal to the core cycles to the microsecond), and check + cache invalidate of the output 9.87 ms. So **the 22.4 ms is cache maintenance** (99.97 %); the DMA itself adds nothing beyond the core's cycles. The tiled designs show the same: 28.1 of 28.9 ms non-core time in the DMA window is cache maintenance. Nothing was changed in the cache handling; the output-buffer flush plus invalidate (19.4 ms) are about a fifth of the pipeline's frame time, which is where a future optimisation would look (it would need its own design check and the full byte-exact re-verification).

**Note:** the layer pipeline idea itself is not new (the PKU group published it; `docs/paper/related_work_and_venues.md`. A Nagasaki University paper is also mentioned in this guide, but it is not in the repo notes: verify it). Cite them; do not claim the idea as yours. Your contribution is the measured gap analysis + fix on a cheap chip, with bit-exact verification.

### 12.4 Verification
Quick suite 48/48, full suite 65/65, mutation 34 mutants (33 caught, 1 equivalent), netlist simulation 4/4, full 960×540 frame bit-exact at every stage, plus a counter-width audit (section 13).

---

## 13. The deadlock bug and what it teaches

### 13.1 What happened
The first full 960×540 simulation of the pipeline **stopped after 5 rows** (14,400 of 1,555,200 output words/beats). The testbench then sat in an unbounded status poll for about 6.5 hours before it was stopped (the poll is now bounded).

### 13.2 The cause (a classic Verilog trap)
The anchor FIFO computed how full it is as `write_pointer − read_pointer`. The pointers are 13 bits, but Verilog evaluated the subtraction in **32 bits**. After 8,192 pushes the pointers wrap back to 0, the 32-bit result becomes negative, the FIFO wrongly says "full", the input stops, and the whole pipeline **deadlocks**.

### 13.3 Why no test caught it
No earlier test pushed more than **3,072** entries, so the pointers never wrapped. The regression (60/60) and mutation test (30 mutants) all passed. **Mutation testing shows whether tests notice a change; it cannot show the tests reach every state.**

### 13.4 Fixes
- Occupancy now computed in the pointers' own width (both FIFOs).
- New FIFO unit test that wraps the pointers 234 times.
- A second width bug was also found: frame height + 6 could wrap for heights ≥ 65,530. Height is now limited to 4,096 (larger values refused with error code 4).
- Every counter now has a test that wraps it (`docs/PIPELINE_COUNTER_AUDIT.md`).
- The old bug was added as mutant F2.

### 13.5 Why this is good for the project
It's a real, honest verification finding: *a deadlock invisible to unit tests, full regression and mutation testing, found only by a full-size frame.* Use it in your report and paper.

---

## 14. All six bitstreams at a glance

All values below were **measured on the board on 27 Oct 2026, all at 100 MHz**. Every design was byte-exact.

| Name | What it is | Built for | VERSION (read back) | Checksum | End-to-end mean | Speed-up vs R0 |
|---|---|---|---|---|---|---|
| **R0** (TESTED_0602) | original design, original weights | 100 MHz | 0x53520602 | 0xcf947f22 | 1,311.7 ms | 1.00× |
| **R2q** | new weights (rep + QAT), same logic | 100 MHz | 0x53522201 | 0x2afbc9ae | 1,312.0 ms | 1.00× |
| **R3q** | new weights + anchor | 100 MHz | 0x53523201 | 0x45dd4e2d | 1,311.6 ms | 1.00× |
| **r0_125** | R0 timed for 125 MHz | 125 MHz | 0x53524201 | 0xcf947f22 | 1,311.9 ms | 1.00× |
| **r3q_125** | R3q timed for 125 MHz | 125 MHz | 0x53524301 | 0x45dd4e2d | 1,311.8 ms | 1.00× |
| **pipe** | layer pipeline, R3q weights + anchor | 125 MHz | 0x53525301 | 0x45dd4e2d | **112.1 ms** | **11.7×** |

- The table above is the 27 Oct (100 MHz) session. On 28 Oct the three 125 MHz designs were run again at a real 125.000 MHz: r0_125 1,061.9 ms, r3q_125 1,061.7 ms, pipe 95.4 ms, all byte-exact on 119/119 images (section 11).
- ARM only (T7): ≈13.4 s per frame, byte-exact. Every tiled design is about 10.2× faster than ARM-only; the pipeline is about 120× faster (about 140× at 125 MHz).
- Negative controls: pipeline output differs from R0's expected file (77.8% of bytes), and R2q's differs too (80.1%), as required.
- Logs and the summary: `results/board/2026-10-27/SUMMARY.md`.
- Each driver program accepts only its own bitstream family. **VERSION-refusal controls (28 Oct): passed.** (a) pipeline bitstream + R3q program, (b) R2q bitstream + R0 program: both printed `SR: VERSION 0x…, expected 0x… (wrong SR_BASE … or wrong bitstream)` and `sr_init failed: 2`, and **refused before any transfer; no DDR writes**: four DDR regions (output image buffer, pad buffer, tile buffers) were filled with random patterns beforehand and read back identical afterwards; the DMA source, destination and length registers stayed 0; no tile or frame message was printed. Each matching pair then ran byte-exact. Caveat for that first run: the driver reset the DMA *before* it checked VERSION, so only "no transfer, no DDR write" was shown. **Fixed and re-tested the same day (driver change, 28 Oct):** the check now comes first. A marker was written into the DMA address registers (both channels halted beforehand, only those two registers written); the old program cleared it (the DMA reset ran), the new program left it intact, on both pairs. A mismatched program therefore no longer touches the DMA. Other mismatched pairs were not run.

- Expected values for everything are in `docs/paper/board_expected.md`.

---

## 15. The board session

### 15.1 Test names
- **T1, T2:** basic correctness tests (register access, a tile / full frame, checksum).
- **T5:** error-recovery test: bad frames must be rejected, and the next good frame must still be byte-exact.
- **T7:** the same network in plain C on the **ARM only**, no FPGA. Gives the "same chip without accelerator" baseline.
- **119-image run:** byte-exact check on all test images.
- **20-frame timing:** mean, min and max frame time.

### 15.2 Priority order (most important first)
1. R0 (sanity, plus T7)
2. **Pipeline** (the main result)
3. R3q
4. r3q_125
5. R2q (with negative control)
6. r0_125

### 15.3 Safety rules
- Load only the listed bitstreams over JTAG.
- **Never** write QSPI flash, SD card or **eFuses** (eFuse writes are permanent).
- Don't change pins, clocks, voltages or boot settings.
- Check each bitstream's md5 before loading.
- Run long jobs under `systemd-inhibit` (the PC must not sleep; it did once and paused everything for 2 h 21 min).
- If something fails: save the log, reset, move on. Don't debug at the board.
- Keep the board ventilated. If there's any burning smell or smoke, unplug the 12 V immediately.

### 15.4 What to record per bitstream
VERSION, checksum (pass/fail), CYCLES, **PL compute time and end-to-end frame time** (both!), and later power.

### 15.5 First full session (27 Oct 2026): results
- Setup verified: JTAG sees both ARM cores and the PL, UART works, boot mode = JTAG.
- All bitstream and program files checked against recorded md5 values before loading.
- **All six bitstreams ran and every output was byte-exact.** No failure, hang, retry or reset.
- Pipeline: 119/119 test images byte-exact, T1/T2/T5 passed, 112.1 ms per frame.
- T7 (ARM only): ≈13.4 s per frame, byte-exact.
- Die temperature stayed at 42–50.3 °C.
- **All runs of this session were at 100 MHz** (see section 11 for the 125 MHz session).
- **No meter available, so power was not measured.**

### 15.6 Second session (28 Oct) and what is left
Done on 28 Oct: (1) VERSION-refusal controls (passed, section 14); (2) 125 MHz runs for r0_125, r3q_125 and the pipeline with each design's own init script, clock read back, die temperature 47.9–49.2 °C, all byte-exact (section 11). Also done on 28 Oct after owner approval: a driver change (VERSION check before the DMA is touched, T7 timer, optional timing split); all six designs were re-verified with the new production ELFs (byte-exact, T3 within ±2 ms of the old means; the tiled designs read 0.3–0.75 ms slower, all in the ARM tile copy; an A/B on R0 gave +0.35 / +0.51 ms there. Label: **unresolved, ≤0.5 ms (<0.04 % of the frame)**; the pre-registered rule was not met and the cause was not isolated). Still open:
3. ~~Split the pipeline's ~22.4 ms overhead~~ **done 28 Oct**: it is cache maintenance (section 12).
4. ~~Re-run T7 with its timer working~~ **done 28 Oct**: 13.433 s per frame, byte-exact.
5. Power, once you have a multimeter.

---

## 16. Power measurement

### 16.1 Why it matters
The FPGA can't beat a GPU on speed, but it might on **energy per frame**:
```
energy per frame (J) = power while processing (W) × frame time (s)
```
GPU reference: ~0.55 J per frame. R0 (Vivado estimate) was about 2.5 J. With the measured 95.4 ms at 125 MHz, the pipeline would be about 0.38–0.48 J **if** the whole board draws about 4–5 W (112.1 ms at 100 MHz: 0.45–0.56 J). That's a guess until measured; it would be roughly equal to or a little below the GPU's 0.55 J.

### 16.2 How (needs a digital multimeter)
- The ZedBoard is said to have a **10 mΩ resistor** in series with the 12 V input, with header **J21** across it. This comes from forum quotes of the user guide and is **not verified yet**; read the guide before relying on it.
- Multimeter on **DC mV**, probes on the two J21 pins. Expect only about **2–5 mV**.
- Current = mV ÷ 10 mΩ (e.g. 3.2 mV → 320 mA). Power = current × input voltage (~12 V) (e.g. 0.32 A × 12 V = 3.84 W).
- Better: an **inline DC power meter** between the adapter and the board, with J21 as a cross-check.
- Take 5+ readings over 30+ seconds per state; same meter range every time.
- States: PL unprogrammed, ARM-only, and idle + processing for each bitstream; repeat R0 at the end.
- Get the official ZedBoard Hardware User Guide and cite its page for J21.

### 16.3 Status
**Not measured yet.** Borrow a multimeter (college lab) and do a separate ~1 hour session.

---

## 17. Publishing a paper

### 17.1 What happened
- ISCAS 2027 (22 Oct) and ARC 2027 (25 Oct) deadlines **passed**.
- A 6-page (including references) IEEE-format draft exists in `docs/paper/draft/` (build with `build.sh`). Author/affiliation and Related Work are still TODO.

### 17.2 Next target
**FPL 2027** (main FPGA conference). FPL 2026's deadline was late March 2026, so 2027 is probably similar (**to be confirmed** at 2027.fpl.org). Page limit and review type are **not checked yet**; read the call when it is published.

### 17.3 The paper's story
"We measured why a verified INT8 SR accelerator on a low-cost Zynq-7020 FPGA was slow (16% DSP efficiency), fixed it with a layer pipeline (~93% efficiency, **11.7× faster measured at the same 100 MHz clock, 13.8× at 125 MHz, ~120–140× faster than the ARM alone**), improved quality by about +0.5 to +1.1 dB (PSNR-Y, BSD100 to Set5) through training, and kept everything byte-exact on all 119 test images on the board, with a verification flow that found a deadlock that regression and mutation testing missed."

### 17.4 What it needs before submission
- Board numbers for every claim (speed, byte-exact, **power**).
- Comparison table with the closest papers (GOPS, GOPS/W, fps, DSPs, PSNR).
- You must **read** the related work yourself:
  (Only the PKU paper and a few others are listed in `docs/paper/related_work_and_venues.md`. The authors, venues and years below are NOT checked against the papers; confirm each one when you read it. In particular, that file calls the 4K UHD 60 fps paper "Chang et al.", this guide says "Kim et al.", and the QARepVGG year may be AAAI 2024, not 2023.)
  1. Quantized SR on PYNQ, FCCM 2020 (same chip, closest competitor)
  2. PKU real-time UHD SR system (layer pipeline)
  3. Nagasaki University pipelined SR on FPGA
  4. Kim et al., 4K UHD 60 fps SR on FPGA (IEEE TCSVT)
  5. Liu et al., SR on edge FPGAs (ACM TODAES 2024)
  6. ABPN (anchor idea, CVPR 2021 workshops)
  7. ECBSR (re-parameterization, ACM MM 2021)
  8. QARepVGG (quantizing re-parameterized nets, AAAI 2023)
- Your guide's approval and co-authorship.
- Anonymous submission (don't link the public GitHub repo; it shows your name).

### 17.5 Verdict rules (agreed in advance)
- **Not publishable yet:** any byte-exact failure, or FPGA not clearly faster than ARM-only.
- **Short paper (regional IEEE / FPL short, weaker chance):** everything byte-exact, clear speed and energy win over ARM, +1 dB measured.
- **Strong FPL short paper:** all of that + the measured pipeline speed-up and the deadlock/verification finding.

**Status after 27 Oct:** byte-exact ✔, speed-up over ARM ✔ (~120×), measured pipeline speed-up ✔ (11.7×), quality ✔, verification finding ✔. **Missing: measured power / energy.** Once power is measured: a solid FPL short-paper candidate. Acceptance is never guaranteed.

---

## 18. Honesty and AI use

- Much of the code, tests and text were written with an AI coding assistant. **That's allowed, but it must be disclosed.** IEEE requires authors to disclose AI-generated content (usually in the acknowledgments).
- Commit messages were cleaned of the tool name. That's fine for tidiness, but **do not hide AI use from your guide, examiners or reviewers.**
- **You must be able to explain every part yourself.** Examiners will ask. Go through one module per day and ask for explanations until you can draw and explain it without help.

---

## 19. Where everything is in the repository

| What | Where |
|---|---|
| Project status, rules, decisions | `docs/STATUS.md` |
| Board checklist (step by step) | `docs/paper/board_checklist.md` |
| Board runbook | `docs/paper/board_session_runbook.md` |
| Expected board values | `docs/paper/board_expected.md` |
| Paper draft (LaTeX) | `docs/paper/draft/` |
| Counter/width audit | `docs/PIPELINE_COUNTER_AUDIT.md` (branch `pipe`) |
| Quality ladder results | `results/quality/image_quality_ladder.md` |
| Comparison crops | `results/images/ladder_crops_*.png` |
| Cycle model | `software/analysis/cycle_model.py` |
| PC/GPU baseline | `software/analysis/cpu_baseline.py` |
| Accumulator range check | `software/ai/quantization/acc_range.py` |
| Board logs (today) | `results/board/2026-10-27/` |
| Sandboxes (git worktrees) | `~/Desktop/venkat/sandbox_R2q`, `sandbox_R3q`, `sandbox_R0_125`, … |
| Bitstreams | `~/Desktop/venkat/*_artifacts/` (old builds in `superseded_*` folders) |
| Fallback bitstream | `~/Desktop/venkat/TESTED_0602.bit` |

**Git branches:** `main`, `r2q`, `r3q`, `r0_125`, `r3q_125`, `pipe`. Everything is committed **locally**; nothing pushed. Backup branches `backup/*-2026-10-25` exist from the history cleanup.

**Settings note:** Claude Code hooks were disabled (`disableAllHooks`) because the plugins' hooks needed Node.js, which isn't installed.

---

## 20. What is done and what is left

### Done
- [x] Network trained, quantized, integer golden model
- [x] Version 1 hardware (R0) measured on board: 1.312 s, byte-exact 119/119
- [x] Gap analysis + cycle model (16–17% efficiency explained)
- [x] PC CPU and GPU baselines
- [x] Quality ladder: +1.1 dB on Set5 (R3q vs the R0 2-seed mean), fully verified
- [x] R2q, R3q, r0_125, r3q_125, pipeline: built, timing met, fully simulated
- [x] Pipeline deadlock bug found and fixed; counter audit
- [x] Board checklist, runbook, expected values
- [x] **Board session (27 Oct): all six bitstreams byte-exact; pipeline 112.1 ms = 11.7× vs R0, ~120× vs ARM; 119/119 images**
- [x] **Board session 2 (28 Oct): VERSION-refusal controls passed (refused before any transfer, no DDR writes); r0_125, r3q_125 and pipe at a read-back 125.000 MHz, 119/119 byte-exact each; 1,061.9 / 1,061.7 / 95.4 ms (one board, 47.9–49.2 °C, no margin sweep)**
- [x] T7 ARM-only baseline (≈13.4 s, timer to be fixed)
- [x] Paper draft updated with measured numbers (6 pages incl. references; related work still TODO)

### Left
- [ ] Power measurement (needs a meter); optionally look at the cache handling (19.4 ms of the pipeline's frame time), which would be a new driver change
- [ ] **Power measurement** (needs a multimeter)
- [ ] Merge the winning design (pipeline, or R3q) into `main` after board results
- [ ] Update the public GitHub README (it is stale)
- [ ] **You:** read the related-work papers
- [ ] **You:** meet your guide: results, draft, authors, venue
- [ ] **You:** study every module until you can explain it
- [ ] Final paper numbers, comparison table, AI disclosure, submit (FPL 2027, to be confirmed)

---

## 21. Viva / interview questions with answers

**Q: What does your project do?**
A: It upscales 960×540 images to 1920×1080 with a small INT8 CNN running as custom hardware on a Zynq-7020 FPGA, and proves the board output is bit-exact with a software reference.

**Q: Why an FPGA and not a GPU?**
A: A GPU is faster, but it's big and power-hungry. An FPGA can run the network in a small, low-power embedded device. The fair comparison is the same chip with and without the accelerator, and energy per frame.

**Q: Why INT8?**
A: Integer math is much smaller and faster on an FPGA than floating point, and 8-bit multiplies fit the DSP blocks. Quality loss was only about 0.1–0.2 dB, and QAT reduces it further.

**Q: Explain requantization.**
A: The accumulator is multiplied by an integer M, a rounding constant 2^(S−1) is added, and it's shifted right by S. That scales the large sum back to 8 bits, rounding to nearest. Then it's clamped.

**Q: Why was version 1 slow?**
A: Four layer engines ran one after another, so three engines' DSPs were always idle. Efficiency was only 16–17%. The cycle model confirmed it.

**Q: How did you fix it?**
A: A layer pipeline: all four layers run at the same time, connected by line buffers and FIFOs, with DSPs shared out in proportion to each layer's work. DSP efficiency went from about 16% to about 93%. On the board it is 11.7× faster (1,311.7 → 112.1 ms) at the same 100 MHz clock, and 95.4 ms (13.8×) at 125 MHz, byte-exact on all 119 test images both times.

**Q: What is a line buffer?**
A: A memory holding only the last few image rows a layer needs (3 rows for a 3×3 filter), instead of a whole tile. It saves memory and avoids recomputing halo pixels.

**Q: What is the anchor?**
A: The network predicts a correction added to the nearest input pixel instead of the whole pixel. It's cheaper to learn, so quality improves. In hardware, it's folded into the requantizer's rounding constant, so it costs no adder and no cycles.

**Q: What does "bit-exact" mean and why does it matter?**
A: Every output pixel is identical to the golden model. A PSNR check can hide bugs that change only a few pixel values; bit-exactness catches every bug that changes any output.

**Q: What is mutation testing?**
A: Deliberately inserting bugs into the design to check that the tests catch them. It measures how good the tests are.

**Q: Tell me about a bug you found.**
A: The pipeline deadlocked after 5 rows of a full frame. A FIFO computed its fill level in 32 bits from 13-bit pointers; after the pointers wrapped, the value went negative and the FIFO falsely reported full. No test had pushed enough data to wrap the pointers, so all regressions passed. I fixed the width, added a test that wraps the pointers, and made a rule that every counter must wrap in at least one test.

**Q: What is re-parameterization?**
A: During training each 3×3 conv has extra parallel branches; after training they are merged mathematically into one 3×3 conv, so hardware is unchanged but quality is better. It needs QAT, because the merged weights lose a lot of quality with plain PTQ.

**Q: What are the limitations?**
A: ×2 only; a tiny network can't recover fine texture; a desktop GPU is faster; power not yet measured (until it is); the pipeline idea is from earlier work.

---

## 22. Glossary

| Term | Meaning |
|---|---|
| **Accumulator** | register holding the running sum of multiplications |
| **AXI / AXI-Lite / AXI DMA** | bus standards between the ARM and the FPGA logic |
| **Bicubic** | standard (non-AI) image resizing; the baseline |
| **Bitstream** | the file that configures the FPGA |
| **BRAM** | on-chip memory block |
| **Byte-exact / bit-exact** | output identical in every bit |
| **Checksum** | a short number summarizing a whole output file; equal checksums = equal outputs |
| **Clamp / saturation** | limiting a value to a range (e.g. 0–255) |
| **CYCLES register** | hardware counter of clock cycles used |
| **Deadlock** | everything waits for everything else; nothing moves |
| **DSP (DSP48E1)** | hard multiplier-adder block in the FPGA |
| **eFuse** | one-time programmable bits in the chip; never touch |
| **Equivalent mutant** | an inserted change that doesn't change behaviour |
| **FIFO** | first-in-first-out queue |
| **FP32** | 32-bit floating point |
| **fps** | frames per second |
| **GOPS** | billions of operations per second |
| **Golden model** | the trusted reference implementation |
| **Halo** | extra border pixels loaded around a tile |
| **INT8** | 8-bit integer |
| **JTAG** | debug/programming connection |
| **Line buffer** | memory holding a few image rows |
| **LUT** | basic logic element in the FPGA |
| **MAC** | multiply-accumulate |
| **Mutation testing** | inserting bugs to test the tests |
| **Netlist simulation** | simulating the synthesized design |
| **PixelShuffle** | rearranges channels into a bigger image |
| **PL / PS** | programmable logic (FPGA) / processing system (ARM) |
| **PSNR / SSIM** | image quality metrics |
| **PTQ / QAT** | quantize after training / during training |
| **Regression** | the full set of automatic tests run after every change |
| **Requantization** | scaling the accumulator back to 8 bits |
| **Residual** | a correction added to a base value |
| **RTL** | register-transfer level: the Verilog design |
| **Seam test** | checks tile borders |
| **Seed** | starting random number for training; 2 seeds show how much results vary |
| **systemd-inhibit** | Linux command that prevents sleep during a job |
| **Tile** | a block of the image processed at once |
| **Timing / WNS** | whether the design is fast enough for the clock; WNS > 0 = met |
| **UART** | serial console connection |
| **VERSION register** | identifies which bitstream is loaded |
| **Worktree / sandbox** | separate copy of the repo for experiments |
