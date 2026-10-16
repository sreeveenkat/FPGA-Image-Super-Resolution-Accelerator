# FPGA Image Super-Resolution Accelerator — the whole project explained, from step 1

This document explains **what** was built, **why** each decision was made and **how** each part works, in the order the work was done
(M0 → M7). Every number in it is copied from a measurement file in `results/` or from the project log; the file is named next to the
numbers so you can show it in a review. Words marked *like this* are explained in the glossary at the end (section 15).

---

## Contents

1. The project in one page
2. Basic ideas you need first
3. The big picture (block diagram)
4. Step M0 – learning the Zynq board
5. Step M1 – the baseline: bicubic, metrics, test images
6. Step M2 – designing and training the neural network (FP32)
7. Step M3 – converting the network to 8-bit integers (INT8) + the "golden model"
8. Step M4 – one convolution layer in Verilog (the conv engine)
9. Step M5 – the whole network in Verilog (the tile core)
10. Step M6 – the complete system on the ZedBoard (AXI, DMA, ARM driver)
11. Step M7 – benchmark: quality, speed, resources, power, reproducibility
12. How everything was verified (all test counts)
13. Problems found and lessons learned
14. Honest limitations and future work
15. Glossary
16. Where to find each thing (file map)
17. Questions a reviewer may ask (with answers)

---

## 1. The project in one page

**Goal.** Take a small image (960×540 pixels) and produce a sharp image twice as large in each direction (1920×1080 = Full HD). This
is called **×2 super-resolution** (SR). The work is done by a small *neural network* that runs as custom hardware inside the FPGA
part of a **ZedBoard** (chip: Xilinx **Zynq XC7Z020**).

**Why.** Upscaling with a simple formula (bicubic) gives blurry edges. A trained neural network recovers sharper edges. Running it on
an FPGA shows how a neural network can be turned into real digital hardware: fixed-point arithmetic, memories, a datapath, a bus
interface and driver software.

**Scope change (important).** The original idea was "sparse ray tracing + AI reconstruction to 4K". A Zynq-7020 has only
**220 DSP slices** (hardware multipliers), which is far too few for 4K at a useful speed, so 4K was dropped. The project became a
**1080p-output ×2 super-resolution accelerator**. Ray tracing stays an optional extension (M8, not started).

**Final result (measured on the board, 2026-10-12):**

| What | Value |
|---|---|
| Frame time, 960×540 → 1920×1080 | **1,311.9 ms per frame = 0.762 fps** (mean of 20 frames) |
| Correctness | Board output **byte-identical** to the software integer model on **all 119** test images |
| Quality (PSNR-Y, higher = better) | Set5 **35.02 dB**, Set14 **31.40 dB**, BSD100 **30.53 dB** vs bicubic 33.67 / 30.32 / 29.56 dB |
| Wins over bicubic | **119 of 119** images |
| FPGA resources (whole system) | 5,296 LUT (10 %), 7,831 FF (7 %), 72 BRAM (51 %), **68 DSP (31 %)** |
| Clock / timing | 100 MHz, timing met: WNS +0.503 ns, WHS +0.016 ns |
| Power | **Estimated** by Vivado (not measured): 1.913 W whole chip, of which 0.176 W is the accelerator |

---

## 2. Basic ideas you need first

### 2.1 What is an image to a computer?
An image is a grid of pixels. Each pixel has three numbers, **R, G, B**, each from 0 to 255 (one byte = 8 bits). A 960×540 image
is 960 × 540 × 3 = **1,555,200 bytes**; a 1920×1080 image is **6,220,800 bytes**.

### 2.2 What is super-resolution?
From a low-resolution (LR) image, guess the high-resolution (HR) image. ×2 means every input pixel becomes a 2×2 block of output pixels.
The simple methods are:
* **Nearest neighbour**: copy each pixel 4 times → blocky.
* **Bicubic**: smooth interpolation using 4×4 neighbours → blurry. This is the standard baseline in papers.
* **CNN** (this project): a trained network looks at a neighbourhood and predicts the 4 output pixels → sharper.

### 2.3 What is a convolution (conv) layer?
A small window (3×3 here) slides over the image. At each position, every value in the window is multiplied by a learned *weight* and
everything is added up (plus a *bias*). One such sum is a **MAC** (multiply-accumulate) chain. A layer with 16 output *channels* has 16
different sets of weights, so it produces 16 numbers per pixel ("feature maps").
* **Depthwise conv**: each channel is filtered only by its own 3×3 window (cheap).
* **1×1 (pointwise) conv**: mixes the channels of one pixel (no neighbours).
* **ReLU**: replaces negative values by 0.
* **Pixel shuffle**: rearranges 12 channels of one LR pixel into a 2×2 block of RGB pixels (3 colours × 4 positions = 12).

### 2.4 How do we measure quality?
* **PSNR** (Peak Signal-to-Noise Ratio, in dB): compares our output with the true HR image. +1 dB is a clearly visible improvement.
* **SSIM** (Structural Similarity, 0…1): compares local structure; 1 = identical.
* **"Y"**: the measurement is done on the brightness (luma) channel only, as in SR papers, with a 2-pixel border cut off.

### 2.5 FPGA, Zynq, PS and PL
* An **FPGA** is a chip whose logic you design yourself (in Verilog). It has *LUTs* (logic), *FFs* (flip-flops/registers),
  *BRAM* (block RAM, 36 Kbit each) and *DSPs* (fast multipliers).
* The **Zynq** contains **two parts**: the **PS** (Processing System: two ARM Cortex-A9 cores at 650 MHz, DDR memory controller,
  UART, …) and the **PL** (Programmable Logic = the FPGA fabric). Our accelerator lives in the PL; the control program runs on the ARM.
* XC7Z020 limits: 53,200 LUT, 106,400 FF, 140 BRAM36, **220 DSP**.

### 2.6 How PS and PL talk: AXI and DMA
| Bus type | Used for | In this project |
|---|---|---|
| **AXI4-Lite** | reading/writing a few 32-bit registers | ARM → accelerator registers (START, STATUS, …) |
| **AXI4 (memory-mapped)** | bulk memory reads/writes with addresses | DMA ↔ DDR memory (through port HP0) |
| **AXI4-Stream** | continuous data without addresses (TDATA, TVALID, TREADY, TLAST) | DMA ↔ accelerator pixel data |

The **DMA** (Direct Memory Access engine) copies data between DDR memory and the stream by itself, so the ARM does not move every byte.
*MM2S* = memory to stream (input to the accelerator); *S2MM* = stream to memory (output back to DDR).

### 2.7 Why INT8?
Training uses 32-bit floating point (FP32). Floating-point hardware is big. 8-bit integers (INT8) are small and fit the FPGA's DSP
multipliers well. Converting FP32 → INT8 is called **quantization**. It loses a little quality (here 0.08–0.18 dB).

---

## 3. The big picture

```
                 PC (training, quantization, checking)                                ZedBoard (Zynq XC7Z020)
 ┌──────────────────────────────────────────────────┐        ┌────────────────────────────────────────────────────────────────┐
 │ M1 datasets + bicubic baseline + metrics         │        │ PS: ARM Cortex-A9 (bare-metal C)                                │
 │ M2 PyTorch FP32 network (train)                  │        │   pads image, cuts 70x70 tiles, places 128x128 results          │
 │ M3 INT8 quantization -> NumPy integer model      │──.mem──│        │ AXI-Lite (GP0, 0x4000_0000)      DDR <─HP0─> AXI DMA   │
 │      (the "golden model")                        │ weights│        ▼                                    (0x4040_0000)│     │
 │ M4/M5 Verilog simulation vs golden model         │        │ PL: sr_accel_top (registers) ─ sr_axis_wrapper ─ sr_tile_core  │
 └──────────────────────────────────────────────────┘        │       L1 → L2 → L3 → L4 → pixel shuffle   (100 MHz)  ◀─stream─┘│
                                                             └────────────────────────────────────────────────────────────────┘
```

**The reference chain (the most important idea of the whole project):**

```
PyTorch FP32 model  →  NumPy INTEGER model ("golden")  →  Verilog RTL (simulation)  →  real board
       (M2)                     (M3)                           (M4, M5)                  (M6, M7)
```
Each stage is checked against the one before it. The RTL and the board are compared with the integer model **bit for bit** (every byte
must be equal), never "approximately". This is why we can say the board is correct: 119/119 images byte-identical.

---

## 4. Step M0 – learning the Zynq board

**What:** four small lab exercises on the real ZedBoard (done by the owner on 2026-10-10/11; record: `docs/milestones/M0_lab_record.md`).
**Why:** before building the accelerator you must know how the ARM, the FPGA, AXI and DMA work together, or debugging later is impossible.

| Step | Goal | Result |
|---|---|---|
| 1 | ARM prints over the UART | "Hello from Zynq! count = N" every second: PASS |
| 2 | AXI GPIO | switches SW0–SW7 drive LEDs LD0–LD7: PASS |
| 3 | Own AXI-Lite IP (`adder_ip`) | 25 + 17 = 42, 6/6 tests PASS |
| 4 | AXI DMA loopback (DDR → MM2S → FIFO → S2MM → DDR) | 256 B, 64 KB, 1 MB all byte-exact: PASS |

**How / lessons that were reused in M6:**
* DMA in **simple mode** (no scatter-gather), 26-bit length register, 32-bit width, burst 16.
* **Cache rule:** the ARM has a data cache; the DMA reads DDR directly. *Flush* the cache before the DMA reads ARM data;
  *invalidate* before the ARM reads DMA output. Forgetting this gives wrong or zero data.
* Start the receiving channel (S2MM) before the sending channel (MM2S); always poll with a timeout.
* Vitis 2024.1 trap: `XAxiDma_LookupConfig()` wants the **base address**, not a device ID.

---

## 5. Step M1 – the baseline: bicubic, metrics, test images

**What:** build the measuring stick before building the network.
**Why:** a result is only meaningful compared to a baseline measured in exactly the same way.

**How:**
* **Test sets** (standard in SR papers): **Set5** (5 images), **Set14** (14), **BSD100** (100) → **119 test images**. Official ×2 LR
  files were also downloaded to validate our method.
* **Training data:** DIV2K photos (img0193–img0384, 192 images; 180 for training, 12 for *validation*). The original planned dataset
  (General-100) link was dead.
* **LR protocol:** crop HR to even width/height ("modcrop"), then downscale ×2 with **Pillow BICUBIC**. Our LR files are **bit-exact
  with the official LR files** for all even-sized images (Set5 5/5, Set14 11/11). Odd-sized images were re-aligned on purpose (the official
  files are slightly misaligned), so BSD100 numbers can differ a little from papers.
* **Metrics:** PSNR and SSIM (Gaussian 11×11, σ = 1.5, the paper definition); Y = BT.601 luma; 2-pixel border shaved.
* Colour convention: RGB everywhere in Python (OpenCV loads BGR; the loaders convert).

**Results** (`results/quality/baseline_x2.md`, also in table A):

| Set | Method | PSNR RGB | SSIM RGB | PSNR Y | SSIM Y |
|---|---|---|---|---|---|
| Set5 | nearest | 29.08 | 0.8783 | 30.86 | 0.9001 |
| Set5 | bicubic | 31.79 | 0.9088 | **33.67** | 0.9303 |
| Set14 | nearest | 26.72 | 0.8202 | 28.58 | 0.8464 |
| Set14 | bicubic | 28.30 | 0.8426 | **30.32** | 0.8698 |
| BSD100 | nearest | 27.10 | 0.8117 | 28.42 | 0.8251 |
| BSD100 | bicubic | 28.23 | 0.8299 | **29.56** | 0.8434 |

Checks: `check_dataset.py` (all files decode, no duplicates, **no train/test overlap**), `check_lr_protocol.py`, 13 unit tests in
`test_baseline.py`. Re-running gives byte-identical results.

---

## 6. Step M2 – designing and training the neural network (FP32)

### 6.1 The network (`software/ai/models/srnet.py`)

```
RGB input (+3 px border)
 → L1  Conv 3×3,  3 → 16 channels  + ReLU
 → L2  Depthwise 3×3, 16 channels   + ReLU
 → L3  Conv 1×1, 16 → 16 channels  + ReLU
 → L4  Conv 3×3, 16 → 12 channels
 → PixelShuffle(2)  → RGB output, 2× width and 2× height
```

| Layer | Weights | Biases | Parameters | MACs per input pixel |
|---|---|---|---|---|
| L1 conv 3×3, 3→16 | 3·16·9 = 432 | 16 | 448 | 432 |
| L2 depthwise 3×3, 16 | 16·9 = 144 | 16 | 160 | 144 |
| L3 conv 1×1, 16→16 | 256 | 16 | 272 | 256 |
| L4 conv 3×3, 16→12 | 16·12·9 = 1,728 | 12 | 1,740 | 1,728 |
| **Total** | | | **2,620** | **2,560** |

A 960×540 frame therefore needs about 960·540·2,560 ≈ **1.33 billion MACs**.

**Why this shape:**
* **Very small** (2,620 parameters) so that it fits 220 DSPs and the BRAM of an XC7Z020.
* **Hardware friendly:** only ReLU, no skip connections, no batch-norm; pixel shuffle is only re-addressing (no arithmetic).
* Depthwise + 1×1 (the FSRCNN/MobileNet idea) is cheaper than a full 3×3 16→16 layer (144 + 256 = 400 MACs instead of 2,304).
* Output layer produces 12 = 3 colours × 2 × 2 values per LR pixel → pixel shuffle → ×2 image.

### 6.2 The "valid convolution + 3-pixel halo" decision (key for tiling)
All convolutions are **valid** (no zero padding inside the network). Three 3×3 layers each shrink the image by 1 pixel per side, so the
network needs a **3-pixel border (halo)** of real neighbours around the region it computes:

```
70×70 input tile (64×64 core + 3 px halo each side)
 → L1 → 68×68 → L2 → 66×66 → L3 (1×1) → 66×66 → L4 → 64×64 (12 channels) → pixel shuffle → 128×128 RGB
```
For the whole image the border is made by **replicate padding** (copying the edge pixels). Because of this, cutting an image into tiles
with a 3-pixel overlap gives **exactly** the same result as processing it whole. That is what lets the FPGA work on one 70×70 tile at a
time with small on-chip memories.

### 6.3 Training (`software/ai/training/train.py`)
* Loss **L1** (mean absolute error), optimizer **Adam**, learning rate 2e-3 → 2e-5 (cosine), 100 epochs × 500 steps × batch 32,
  LR patch 32×32 (+3 px halo), random flips/rotations, seed 0, CPU, ~33 minutes.
* 180 training images, 12 **validation** images. All choices were made on validation images only, **never on the test sets**.
* Final checkpoint: `software/ai/checkpoints/srnet_fp32.pt` (14 KB, sha256 starts `f1ae81f706ad3707`), committed to git.

### 6.4 Experiments (ablations) – why the simplest model was kept (`results/quality/m2_training_summary.md`)

| Variant | Params | Best validation PSNR-Y | vs bicubic (33.719) |
|---|---|---|---|
| **A: L1 loss, 16 ch (chosen)** | 2,620 | **34.954** | +1.235 |
| B: L1 + 0.2·(1−SSIM) | 2,620 | 34.908 | +1.189 |
| C: edge-touching windows | 2,620 | 34.891 | +1.172 |
| D: 24 channels | ~5.5k | 34.869 | +1.150 |

All within ~0.09 dB (noise between runs is 0.02–0.05 dB) → no variant is meaningfully better → keep the smallest and simplest (A).

Reproducibility: re-running training gives 0.02 dB difference (not bit-identical: thread count changes the float addition order).
Two seeds differ by 0.03–0.09 dB on the test sets. That is why the trained weights are frozen and everything after them is checked byte by byte.

### 6.5 FP32 results (`results/quality/model_fp32_x2.md`)

| Set | Bicubic PSNR-Y | FP32 CNN PSNR-Y | Gain | SSIM-Y bicubic → CNN |
|---|---|---|---|---|
| Set5 | 33.67 | **35.21** | +1.53 dB | 0.9303 → 0.9449 |
| Set14 | 30.32 | **31.51** | +1.18 dB | 0.8698 → 0.8975 |
| BSD100 | 29.56 | **30.60** | +1.04 dB | 0.8434 → 0.8785 |

* Better than bicubic on **119/119** images (BSD100 per-image gain: min +0.46, median +0.98, max +2.46 dB).
* Border effect: outer 8-pixel band gains +0.83 dB vs +0.98 dB inside (replicate padding, a few % of pixels; ignored).
* Visual check: sharper edges, text and stripes; no checkerboard or colour shift. Fine random texture (gravel, fur, cloth) is **not**
  recovered — expected for 2,620 parameters.
* Target size check: 960×540 → 1920×1080 works; 135 tiles equal the whole-image output to 6.6e-7 (float rounding only).

---

## 7. Step M3 – converting the network to 8-bit integers (INT8) + the golden model

### 7.1 What and why
The FPGA will compute with integers, so we need an **integer version** of the network and a **software model** of exactly what the
hardware must compute. That model, `software/ai/quantization/integer_reference.py` (pure NumPy integers, no floats), is the
**golden model**: the RTL and the board must match it bit for bit.

### 7.2 The integer arithmetic (identical for every layer)
* Activations (pixel values, feature maps): **uint8** (0…255), one scale per layer.
* Weights: **int8**, symmetric, range [−127, 127], **one scale per layer**.
* Biases: **int32**. Accumulator: **int32** (checked to never overflow).
* For each output value:

```
acc = bias[co] + Σ  x(uint8) · w(int8)                         (the MACs)
y   = (acc · M[co] + 2^(SHIFT−1)) >> SHIFT                      (requantize: multiply by M, round half up, arithmetic shift)
out = clamp(y, 0, 255)                                          (this clamp is also the ReLU)
```
`M / 2^SHIFT` is the real number `s_in · s_w / s_out` (input scale × weight scale ÷ output scale), stored as a 16-bit integer M and a
shift. `acc · M` needs about 40 bits in hardware.

**The actual parameters** (`qparams.npz`, `hardware/rtl/weights/`):

| Layer | SHIFT | M (all channels share one value) | M / 2^SHIFT | weight range |
|---|---|---|---|---|
| L1 | 24 | 62,656 (0xF4C0) | 0.003735 | −127…112 |
| L2 | 23 | 40,008 (0x9C48) | 0.004769 | −127…113 |
| L3 | 21 | 42,362 (0xA57A) | 0.020200 | −60…127 |
| L4 | 24 | 43,607 (0xAA57) | 0.002599 | −124…127 |

Input scale 1/255 (so the input is just the RGB byte); last-layer output scale 1/255 (so the output is directly the RGB byte).

### 7.3 How the settings were chosen (Post-Training Quantization sweep)
The activation range of each layer was set from a **percentile** of the activations seen on 100 training crops. Sweep on the 12
**validation** images (`results/quality/m3_ptq_sweep.md`, FP32 reference 34.954 dB):

| Percentile | Weights | INT8 PSNR-Y | Drop vs FP32 |
|---|---|---|---|
| 99.0 | per-layer | 29.648 | 5.307 dB (catastrophic) |
| 99.9 | per-layer | 34.529 | 0.425 |
| **99.99** | **per-layer** | **34.731** | **0.223 (chosen)** |
| 100 (max) | per-layer | 34.675 | 0.280 |
| 99.99 | per-channel | 34.647 | 0.307 |

→ 99.99th percentile, per-layer weight scales. The drop is small, so *QAT* (quantization-aware retraining) was not needed.

### 7.4 INT8 results (`results/quality/model_int8_x2.md`)

| Set | FP32 PSNR-Y | INT8 PSNR-Y | Drop | INT8 SSIM-Y |
|---|---|---|---|---|
| Set5 | 35.21 | **35.02** | 0.18 dB | 0.9420 |
| Set14 | 31.51 | **31.40** | 0.11 dB | 0.8948 |
| BSD100 | 30.60 | **30.53** | 0.08 dB | 0.8756 |

Worst single image drop: 0.41 dB. INT8 still beats bicubic on **119/119**. Tiled output equals whole-image output **exactly** (integers,
no rounding differences).

### 7.5 Exports for the hardware
* `hardware/rtl/weights/weights_Ln.mem`, `wrom_Ln.mem` (weights rearranged "step-major" for the hardware ROM), `bias_Ln.mem`,
  `mult_Ln.mem`, `network_params.vh` (shifts and sizes).
* **Golden tiles** in `data/golden/` (zeros, all-255, noise, single pixel, ramp, small 12×12, real image tiles, border tile): input and the
  expected output of **every layer**, as byte-per-line hex files the Verilog testbenches read.
* Checks: 21 + 7 tests, an independent pure-Python recompute from only the exported files, a comparison with a float64 PyTorch version
  (≤ 1 LSB), and 22 deliberate "breakages" of the code — all caught by the tests.

---

## 8. Step M4 – one convolution layer in Verilog (the conv engine)

### 8.1 What
`hardware/rtl/conv_engine/conv_engine.v`: one hardware block that computes one layer. It is instantiated **four times** with different
parameters (`C_IN, C_OUT, K, DEPTHWISE, IN_W, IN_H, SHIFT` + weight files). Helper modules in `hardware/rtl/common/`:
`mac_unit.v` (multiply-accumulate), `requant.v` (requantizer), `weight_rom.v`, `tile_ram.v` / `tile_ram_split.v`.

### 8.2 How it works ("folded" design)
* **One MAC lane per output channel** (16 lanes for L1–L3, 12 for L4), each in a DSP48 slice.
* Every clock cycle the engine reads **one input word** (all channels of one pixel, channel c in bits `8c+:8`) and **one ROM word** (the
  weights of all output channels for that step). All lanes do `acc += a × w` in parallel.
* Steps per output pixel `STEPS = K·K·(depthwise ? 1 : C_IN)`: L1 3·3·3 = 27, L2 9, L3 16, L4 3·3·16 = 144.
* One shared **requantizer** (3 pipeline stages) handles the 16 results of a pixel while the next pixel's MACs run. It needs C_OUT
  cycles, so a new pixel starts every `PERIOD = max(STEPS, C_OUT)` cycles.
* Interface: `start` pulse, `busy`, `done` pulse, `cycles` counter, read port to the input RAM (1-cycle latency), write port to the
  output RAM. One-cycle synchronous reset is enough.

| Layer | Steps | Cycles per output pixel | Output pixels | Cycles per 64×64 tile |
|---|---|---|---|---|
| L1 | 27 | 27 | 68×68 = 4,624 | 124,872 |
| L2 | 9 | **16** (limited by the requantizer, not 9) | 66×66 = 4,356 | 69,713 |
| L3 | 16 | 16 | 4,356 | 69,720 |
| L4 | 144 | 144 | 64×64 = 4,096 | **589,844 (64 % of all)** |
| **Sum** | | | | **854,149** |

### 8.3 Results (`results/utilization/m4_conv_engine.md`)
Each engine synthesized and placed-and-routed alone in Vivado ("out-of-context") at 100 MHz:

| Layer | LUT | FF | DSP | BRAM36 | Setup slack (WNS) |
|---|---|---|---|---|---|
| L1 | 298 | 851 | 18 | 2 | +3.853 ns |
| L2 | 398 | 953 | 18 | 0 | +3.393 ns |
| L3 | 369 | 841 | 18 | 0 | +2.913 ns |
| L4 | 349 | 693 | 14 | 1.5 | +3.146 ns |

All four together: **68 DSP** = 18 + 18 + 18 + 14. Each engine uses one DSP per MAC lane (16, 16, 16, 12) plus 2 more. Those 2 are
most likely the requantizer's wide multiply (32-bit × 17-bit); this is inferred from the counts, not checked in the netlist.
Bit-exact with the golden model on all 4 layers × 10 golden tiles, on randomized layers (different M per channel, non-square tiles), and
the **synthesized netlists** simulate bit-exact too. 32 deliberate RTL breakages were all caught.

### 8.4 Important lessons from M4
* Building the ROM contents in a Verilog `initial` loop **simulated fine but Vivado silently ignored it** (warning Synth 8-311) and
  removed the engine. Fix: the Python exporter writes the ROM file in the final layout (`wrom_Ln.mem`) and Verilog only does `$readmemh`.
* Small 9×8-bit multiplies went into LUTs instead of DSPs → `(* use_dsp = "yes" *)` on `mac_unit`.
* A plain 70×70×128-bit RAM used **32 BRAM36**, not ~20 as planned (fixed in M5).
* Timing fix (2026-10-09): one register stage after the result multiplexer in front of the requantizer raised the margin from
  +0.135 ns to +3.853 ns (L1), costing only +1 cycle per engine.

---

## 9. Step M5 – the whole network in Verilog (the tile core)

### 9.1 What
`hardware/rtl/sr_core/sr_tile_core.v`: takes one 70×70 RGB tile as a **byte stream**, runs L1 → L2 → L3 → L4, does the pixel shuffle, and
sends the 128×128 RGB result out as a byte stream.

```
bytes in (70×70×3 = 14,700) → loader → ram0 (4,900 × 24 bit)
   -L1-> ram1 (4,624 × 128 bit) -L2-> ram2 (4,356 × 128) -L3-> ram3 (4,356 × 128) -L4-> ram4 (4,096 × 96 bit)
   → pixel shuffle + packer → bytes out (128×128×3 = 49,152)
```
A small state machine (IDLE → LOAD → L1 → L2 → L3 → L4 → OUT → IDLE) starts the engines one after the other. Streams use
valid/ready handshakes (like AXI-Stream), `out_last` marks the last byte.

**Pixel shuffle in hardware:** output pixel (2y+dy, 2x+dx), colour c = channel `k = 4c + 2dy + dx` of L4 at (y, x). It is just choosing
which byte of the 96-bit word to send — no arithmetic.

### 9.2 Why one RAM per layer (no ping-pong)?
Simplest to build and verify. Speed was not the first goal; correctness was.

### 9.3 The BRAM problem and fix
Vivado rounds the depth of a large RAM up to a power of two: one 4,624-deep RAM was built like an 8,192-deep one → 32 BRAM36.
`tile_ram_split.v` splits it into a 4,096-deep part + the remainder → **18.5 BRAM36**. Without this the five buffers would not fit.

### 9.4 Results (`results/utilization/m5_tile_core.md`)

| Item | Value |
|---|---|
| Cycles per tile (simulation, no stalls) | **926,201** = engines 854,149 + byte-wide I/O ~72,052 (load 14,700 + output 49,152 + ~8,200 RAM fetch cycles) |
| Frame estimate (135 tiles at 100 MHz) | ~1.25 s (~0.80 fps), compute + byte streams only |
| LUT / FF / DSP / BRAM (placed and routed) | 1,896 / 3,341 / 68 (31 %) / 70 (50 %) |
| Setup slack at 100 MHz | +0.723 ns (hold +0.085 ns); critical path: layer RAM → MAC input |

**Verification:** every layer RAM and the output stream match the golden data on all 9 real-size tiles (also with random stalls);
**seam test**: a real image cut into tiles (20 tiles at a small size, 4 at real size), run through the RTL and pasted back, equals the
whole-image golden result exactly; 60 resets at different moments; netlist simulation; 21 deliberate breakages caught; **73 simulation
runs** in the full regression.

---

## 10. Step M6 – the complete system on the ZedBoard

### 10.1 Hardware wrapper: AXI-Stream (`hardware/rtl/axi_wrapper/sr_axis_wrapper.v`)
* The DMA sends **32-bit words**; the core takes **bytes**. The wrapper unpacks each word into 4 bytes (little-endian: first byte =
  bits 7:0) and packs output bytes back into 32-bit words.
* Input tile = 14,700 B = **3,675 words**; output tile = 49,152 B = **12,288 words**; TLAST on the last output word.
* `s_axis_tready` is high only while the core is loading, so the DMA can be started **before** START without losing data.
* Error flags: input TLAST too early, TLAST missing on the last word, START while busy.

### 10.2 Top module and registers (`hardware/rtl/top/sr_accel_top.v`, `docs/REGISTER_MAP.md`)
An AXI4-Lite slave with these registers (base address **0x4000_0000**):

| Offset | Name | Meaning |
|---|---|---|
| 0x00 | CONTROL | write bit0 = START, bit1 = soft reset |
| 0x04 | STATUS | bit0 BUSY, bit1 DONE (sticky), bit2 ERROR (sticky) |
| 0x08 | TILE_SIZE | 64 |
| 0x0C | CYCLES | clock cycles of the last tile |
| 0x10 | ERROR_CODE | 0 none, 1 early TLAST, 2 missing TLAST, 3 TKEEP ≠ 0xF |
| 0x14 | VERSION | 0x53520602 (first board version: 0x53520601) |
| 0x18–0x30 | debug | input beats, TLAST position, START-to-first-beat cycles, beats before start, start counts, error position |

"DONE" means the **last output word has been accepted by the DMA**, not just computed.

### 10.3 The block design (Vivado)
PS7 (ARM) + AXI DMA (0x4040_0000, simple mode) + `sr_accel_top`, PL clock FCLK_CLK0 = **100 MHz**. The DMA reaches DDR through
**S_AXI_HP0**. (The M0 GPIOs and `adder_ip` were kept, so addresses stay identical to the tested system.) Saved as Tcl:
`hardware/vivado/bd/design_1_m6.tcl`; full build script: `hardware/vivado/scripts/build_m6_system.tcl`.

### 10.4 The ARM software (`software/board/sr_app/`)
* `sr_driver.c` — for each tile: flush caches → arm S2MM (receive 49,152 B) → arm MM2S (send 14,700 B) → write START → poll STATUS
  and DMA until done (timeout ~1 s) → check error bits → invalidate cache → read CYCLES. On any error: reset **core → DMA → core** and
  report a code.
* `sr_tiling.c` — pad the image by 3 px (replicate) and extend to a multiple of 64, cut 70×70 tiles, place 128×128 results.
  960×540 → padded to 960×576 → **15 × 9 = 135 tiles**. Proven on the PC to be byte-exact with the Python integer model (also for
  7 awkward sizes).
* Timer: the BSP timer function returned 0, so the driver reads the ARM global timer (325 MHz) directly.
* Tests built into `main.c`: **T1** golden tile + 20 repeats, **T2** whole image, **T3** timing, **T5** error recovery,
  **T6** stress (1,000 tiles).
* `run_board.tcl` (xsdb, over JTAG): programs the FPGA **safely** (PL held in reset and PS–PL level shifters off while reprogramming),
  loads the program, copies the image into DDR, runs, copies the result back. `compare_raw.py` compares with the expected output.

### 10.5 First board results (2026-10-11, `results/speed/m6_board.md`)

| Test | Result |
|---|---|
| T1 golden tile | all 49,152 bytes correct; 20/20 repeats identical; CYCLES 926,217–926,220 (simulation 926,202); 9,521 µs per tile |
| T2 128×128 (Set14 baboon crop) | byte-exact, 38.7 ms |
| T2 960×540 → 1920×1080 (3 runs) | byte-exact (6,220,800 bytes, checksum 0xcf947f22), 1,311.4 / 1,312.7 / 1,313.0 ms |
| T3 15 frames | ~1.312 s per frame, spread < 2 ms |
| Power-cycle test | still byte-exact after switching the board off and on |

### 10.6 Problems on the board and how they were solved
1. **Timer gave 0** → read the global timer registers directly (checked against the PLL settings: CPU 650 MHz, timer 325 MHz).
2. **Reloading a program over a running one**: old dirty cache lines overwrote the new program → `run_board.tcl` turns the L2 cache off
   and loads the ELF twice (A/B test: 3 failures of 9 before, 0 of 15 after).
3. **Reset order**: resetting DMA first gave a wrong next tile after an error → order changed to core → DMA → core (14/14 recoveries OK).
4. **First-tile stream errors**: reprogramming the FPGA while a DMA transfer was still running, without isolating the PL, broke tiles
   (every tile failed after exactly 16 reloads, 2/2 runs). With **PL isolation** in the script: 50/50 OK; 8,000 fresh tiles with 0 errors;
   a simulation sweep of 918 START-timing cases found no RTL bug. **2 single failures from the early runs remain unexplained.**

### 10.7 The 0602 bitstream
The debug registers (VERSION 0x53520602) were added and the bitstream rebuilt on 2026-10-12 (5 min 34 s, Vivado with 2 parallel jobs —
8 jobs had frozen the 15 GB PC). Board regression (`results/utilization/m6_system_0602.md`):

| Test | Result |
|---|---|
| VERSION | 0x53520602 |
| T1 golden tile + 20 repeats | 20/20, CYCLES 926,217–926,220 |
| T2 128×128 and 3 × 960×540 | byte-exact (0x91a4506d, 0xcf947f22), 1,311.4–1,311.5 ms |
| T5 error recovery | 10/10 |
| T6 stress, two driver orders | 1,000/1,000 + 1,000/1,000, 0 errors |
| Fresh program loads | 50/50 |

---

## 11. Step M7 – benchmark: the four tables

### Table A — Quality (`results/quality/table_a_x2.md`)
The FPGA row comes from images that **actually ran on the board** (all 119, 2026-10-12, 119/119 byte-exact, log
`results/quality/m7_board_testsets_run.log`).

| Set | Method | PSNR RGB | SSIM RGB | PSNR Y | SSIM Y | better than bicubic |
|---|---|---|---|---|---|---|
| Set5 (5) | nearest | 29.08 | 0.8783 | 30.86 | 0.9001 | – |
| | bicubic | 31.79 | 0.9088 | 33.67 | 0.9303 | – |
| | FP32 | 33.12 | 0.9244 | 35.21 | 0.9449 | 5/5 |
| | INT8 | 32.83 | 0.9160 | 35.02 | 0.9420 | 5/5 |
| | **FPGA** | **32.83** | **0.9160** | **35.02** | **0.9420** | **5/5** |
| Set14 (14) | nearest | 26.72 | 0.8202 | 28.58 | 0.8464 | – |
| | bicubic | 28.30 | 0.8426 | 30.32 | 0.8698 | – |
| | FP32 | 29.29 | 0.8688 | 31.51 | 0.8975 | 14/14 |
| | INT8 | 29.15 | 0.8617 | 31.40 | 0.8948 | 14/14 |
| | **FPGA** | **29.15** | **0.8617** | **31.40** | **0.8948** | **14/14** |
| BSD100 (100) | nearest | 27.10 | 0.8117 | 28.42 | 0.8251 | – |
| | bicubic | 28.23 | 0.8299 | 29.56 | 0.8434 | – |
| | FP32 | 29.24 | 0.8673 | 30.60 | 0.8785 | 100/100 |
| | INT8 | 29.11 | 0.8609 | 30.53 | 0.8756 | 100/100 |
| | **FPGA** | **29.11** | **0.8609** | **30.53** | **0.8756** | **100/100** |

FPGA = INT8 exactly, because the board output is byte-identical to the integer model. Example: Set14 zebra, PSNR-Y bicubic 30.65 dB →
FPGA 32.57 dB (`docs/demo/compare_zebra.png`).

### Table B — Speed (`results/speed/m7_timing_20frames.md`, board, 20 frames)

| Metric | Value |
|---|---|
| Time per frame (mean of 20) | **1,311.9 ms** |
| Min / max | 1,311.4 / 1,313.2 ms (spread 1.7 ms = 0.13 %) |
| Frames per second | **0.762 fps** |
| Input / output pixels per second | 395 k px/s / 1.58 M px/s |
| CYCLES per tile (hardware counter, 2,700 tiles) | min 926,217, max 926,241, mean 926,220 (simulation 926,202) |
| Data moved by the DMA per frame | 8,620,020 B (135 × (14,700 + 49,152)) |

**Where the time goes:**

| Part | ms | % of frame |
|---|---|---|
| Padding the input (ARM) | 5.9 | 0.4 % |
| ARM tile copies (cut + place) | 26.4 | 2.0 % |
| DMA + compute wait | 1,279.6 | 97.5 % |
| – of which the core computing (135 × 926,220 cycles / 100 MHz) | 1,250.4 | 95.3 % |
| – of which DMA setup, handshakes, driver | 29.2 | 2.2 % |

Prediction from simulation 1,250.4 ms; measured 1,311.9 ms (+4.9 %, the ARM work and DMA handshakes). **The bottleneck is the core
itself**, and inside it L4 (64 % of the cycles).

### Table C — Resources and timing (`results/utilization/m6_system_0602.md`, whole system after place and route)

| Resource | Used | % of XC7Z020 |
|---|---|---|
| LUT | 5,296 | 9.95 % |
| FF | 7,831 | 7.36 % |
| Block RAM tiles (36 Kb) | 72 | 51.43 % |
| DSP48E1 | **68** | 30.91 % |
| Setup slack (WNS) at 100 MHz | **+0.503 ns** (0 failing endpoints of 23,943) | |
| Hold slack (WHS) | +0.016 ns | |
| Critical path | ram3 (BRAM) → L4 MAC lane 7 input (DSP) | |

Accelerator core alone (M5, out-of-context): 1,896 LUT, 3,341 FF, 68 DSP, 70 BRAM.

### Table D — Power (`results/utilization/m7_power.md`) — **Vivado ESTIMATE, confidence "Low", NOT measured**

| Item | Watts (default 12.5 % toggle) |
|---|---|
| Total on-chip | **1.913 W** (1.911 at 6.25 %, 1.915 at 25 %) |
| Static | 0.155 |
| PS7 (ARM, DDR controller) | 1.563 (82 %) |
| Accelerator `sr_accel_top` | **0.176** (~9 %) |
| AXI DMA + interconnect | 0.017 |

Energy (estimated power × measured time 1.312 s): **~2.5 J per frame** whole chip, ~0.23 J accelerator only, ~1.7 mJ per tile
(accelerator), ~1.2 µJ per output pixel (chip).

### Reproducibility (`results/utilization/m7_clean_clone_build.md`)
The whole flow was repeated from a **fresh `git clone`** in an empty folder: regenerated files byte-identical, RTL quick regression
36/36, bitstream rebuilt with the same utilization/timing/power as 0602, and on the board T1/T2/T3 and all **119 images byte-exact**.
Not repeated: dataset downloads and the 33-minute training (the checkpoint is committed).

### M7 checklist
- [x] All tables filled with measured values
- [x] FPGA output bit-exact on all test images (119/119)
- [x] Timing met at the reported 100 MHz
- [x] README reproduces the build from scratch (tested on a clean clone)
- [ ] Final "no claim without a number" review of all text (still open)

---

## 12. How everything was verified (summary)

| Level | What | Count / result |
|---|---|---|
| Python (M1–M3) | unit tests | 13 (baseline) + 9 (model) + 21 (integer) + 7 (export) = 50 tests pass |
| Python | deliberate code breakages ("mutation tests") | 18 (M1/M2) + 22 (M3), all caught |
| Python | independent recompute from exported files | all golden tiles match |
| RTL | `run_tests.sh quick` / `full` (Icarus Verilog) | **36 / 88 runs**, 0 failed |
| RTL | netlist (post-synthesis) simulations | 5/5 exact |
| RTL | deliberate RTL breakages | 32 (M4) + 21 (M5) + 14 (wrapper) + 20 (top) = **87, all caught** |
| RTL | START-timing sweep | 918 tiles exact (+6 at real size) |
| Also | Vivado xsim in the GUI (by the owner) | 24 PASS, 0 FAIL |
| Board | golden tile, frames, test sets | T1 20/20, 960×540 byte-exact, **119/119 images byte-exact** |
| Board | robustness | 2 × 1,000 stress tiles, 8,000 fresh tiles, 50 fresh loads, error recovery 10/10 |
| Build | clean clone | byte-identical files, same bitstream numbers, same board results |

**Why mutation tests?** A test that never fails proves nothing. Deliberately breaking the code (e.g. a wrong shift, wrong channel order,
missing reset) and checking that a test catches it proves the tests actually check something.

---

## 13. Problems found and lessons learned

| Problem | Lesson |
|---|---|
| ROM built in a Verilog `initial` loop worked in simulation, Vivado silently removed it | Check synthesis logs (Synth 8-311) and resource counts, not only simulation |
| Small multipliers mapped to LUTs | Use `(* use_dsp = "yes" *)` and check the DSP count |
| Plain 4,624-deep RAM cost 32 BRAM | Vivado rounds depth to a power of two → split RAM (18.5 BRAM) |
| Testbench stimulus at the rising edge raced the design | Drive stimulus on the falling edge |
| A testbench passed with missing golden files (X === X) | Add guards so a missing file is a FAIL |
| A wrong default parameter was invisible because the testbench overrode it | Test the defaults too |
| Timing margin only +0.135 ns | One register stage after the mux → +3.85 ns |
| Board timer returned 0 | Read the hardware timer directly and cross-check with CYCLES |
| Reprogramming FPGA over a running DMA broke tiles | Isolate the PL (reset + level shifters off) before programming |
| Vivado with 8 jobs froze the 15 GB PC | Use 2 jobs |
| `create_project -force` followed symlinks and deleted `hardware/` and `data/` (recovered from git + re-download) | Never put links to real folders inside tool project folders; commit early |

---

## 14. Honest limitations and future work

**Limitations**
* **0.76 fps, not real time.** The four engines run one after another, L4 alone is 64 % of the cycles, and load / compute / output are
  not overlapped; the stream is one byte per cycle.
* **Power is an estimate** (Vivado, confidence Low); nothing was measured with an instrument.
* **2 early first-tile failures** (2026-10-11) remain unexplained; none in thousands of tiles after the PL-isolation fix.
* Images go in and out over **JTAG** (debugger), not from an SD card, camera or HDMI: fine for measuring, not a product.
* INT8 loses 0.08–0.18 dB against FP32; fine random texture is not recovered by a 2,620-parameter network.
* No speed comparison with a CPU/GPU implementation was made.

**Future work**
* Speed: more parallel MACs in L4, double buffering at tile level (overlap load/compute/output), a wider stream → plan target ~5–10 fps.
* A simulation-based (SAIF) power estimate and a real power measurement.
* M8 options: HDMI output, ×4 scale, luma-only network, ray-traced input.

---

## 15. Glossary

| Term | Meaning |
|---|---|
| ×2 SR | super-resolution doubling width and height |
| LR / HR | low-resolution input / high-resolution ground truth |
| CNN | convolutional neural network |
| Channel | one "layer" of numbers per pixel (RGB = 3 channels; feature maps = 16) |
| MAC | multiply-accumulate: `acc = acc + a × w` |
| ReLU | `max(0, x)` |
| Valid convolution | no padding: output is smaller than input by (kernel − 1) |
| Halo | the extra 3-pixel border a tile needs so the valid convolutions produce the full core |
| Pixel shuffle | rearranging 12 channels into a 2×2 block of RGB pixels |
| FP32 / INT8 | 32-bit floating point / 8-bit integer |
| Quantization (PTQ / QAT) | converting to integers after training / training with integers simulated |
| Requantize | scaling a 32-bit sum back to 8 bits: `(acc·M + round) >> SHIFT`, then clamp |
| Golden model | the bit-exact software reference the hardware must match |
| PSNR / SSIM | quality measures (dB / 0…1), higher is better |
| Validation set | images used to choose settings; test images are never used for choices |
| Ablation | an experiment changing one thing to see if it matters |
| RTL | register-transfer level = the Verilog design |
| Testbench | Verilog code that drives the design and checks its outputs |
| Netlist simulation | simulating the design after synthesis (closer to real hardware) |
| LUT / FF / BRAM / DSP | FPGA logic / registers / 36 Kb memory blocks / hardware multipliers |
| WNS / WHS | worst setup / hold slack; ≥ 0 means timing is met |
| Out-of-context | synthesizing a block alone, without the rest of the system |
| PS / PL | ARM processing system / programmable logic (FPGA fabric) of the Zynq |
| AXI-Lite / AXI-Stream | register bus / data streaming bus |
| DMA, MM2S, S2MM | copy engine; memory→stream; stream→memory |
| TLAST / TKEEP | stream signals: last word of a packet / which bytes are valid |
| Cache flush / invalidate | write ARM cache to DDR / discard ARM cache so DDR is re-read |
| Bitstream | the file that programs the FPGA |
| XSA / BSP / ELF | hardware description for Vitis / board support library / compiled ARM program |
| xsdb / JTAG | Xilinx debugger / debug cable used to load and control the board |
| Mutation test | deliberately breaking code to prove a test catches it |
| Byte-exact | every byte equal (stronger than "similar PSNR") |

---

## 16. Where to find each thing (file map)

| Part | Files |
|---|---|
| Datasets, LR protocol | `software/ai/dataset/` (`pairs.py`, `check_dataset.py`, `check_lr_protocol.py`), `data/README.md` |
| Metrics, evaluation | `software/ai/evaluation/` (`metrics.py`, `eval_baseline.py`, `eval_model.py`, `eval_int8.py`, `run_all.py`) |
| Network, training | `software/ai/models/srnet.py`, `software/ai/training/train.py`, `software/ai/checkpoints/srnet_fp32.pt` |
| Quantization, golden model | `software/ai/quantization/` (`quantize.py`, `integer_reference.py`, `export_rtl.py`, `qparams.npz`) |
| Exported weights | `hardware/rtl/weights/` |
| RTL | `hardware/rtl/common/`, `conv_engine/`, `sr_core/`, `axi_wrapper/`, `top/` |
| Testbenches | `hardware/verification/tb/`, `run_tests.sh`, `run_postsynth.sh`, `demo_sim.sh` |
| Vivado scripts, block design | `hardware/vivado/scripts/`, `hardware/vivado/bd/design_1_m6.tcl` |
| ARM program, board scripts | `software/board/sr_app/`, `software/board/run_board.tcl`, `demo.sh`, `README.md` |
| PC helpers | `software/host_tools/` (png↔raw, expected output, compare, figures) |
| Results | `results/quality/`, `results/speed/`, `results/utilization/` |
| Guides | `README.md`, `docs/REGISTER_MAP.md`, `docs/VERIFY_YOURSELF.md`, `docs/DEMO.md` |

---

## 17. Questions a reviewer may ask (with answers)

**Q: Why not 4K?** The XC7Z020 has 220 DSPs. Even this 2,620-parameter network needs 1.33 GMAC per 960×540 frame; 4K output would be
4× more work on the same small chip. The realistic target was 1080p output.

**Q: How do you know the FPGA is correct?** It is compared byte for byte with the integer golden model: per layer in simulation, per tile
on the board (T1), whole frames (T2), and all 119 test images on the board — 119/119 byte-identical. Therefore its PSNR equals the INT8
model's PSNR exactly.

**Q: Why is the FPGA quality slightly lower than FP32?** Quantization to 8 bits: 0.18 / 0.11 / 0.08 dB drop (Set5 / Set14 / BSD100). It
still beats bicubic on every image.

**Q: Why is it only 0.76 fps?** The design was built for correctness first: the 4 layers run one after another on folded engines, L4
needs 144 cycles per pixel (64 % of the time), and loading/computing/output are not overlapped. 95 % of the frame time is the core
computing, so the DMA and ARM are not the bottleneck.

**Q: How would you make it faster?** Parallelize L4 (more MAC lanes, the largest win), overlap tile load/compute/output with double
buffering, use a 32-bit stream into the core instead of bytes, and pipeline the layers so they run at the same time.

**Q: Why valid convolutions and a 3-pixel halo?** So that a tile computed alone gives exactly the same pixels as the whole image. This
lets the FPGA use small on-chip memories (one 70×70 tile at a time) with no seams — proven by the seam test.

**Q: How much of the chip is used?** 68 of 220 DSPs (31 %), 72 of 140 BRAM (51 %), 10 % LUT, 7 % FF; timing met at 100 MHz.

**Q: Is the power measured?** No. It is a Vivado estimate (1.913 W, confidence Low), and 82 % of it is the ARM side.

**Q: Did you test on data the model was trained on?** No for quality: settings were chosen on 12 validation images, quality is reported on
Set5/Set14/BSD100 only, and a check confirms no overlap between training and test images. (The DIV2K image used for speed/bit-exact tests
is a training image, which does not matter for speed or bit-exactness.)

**Q: What is still not solved?** 2 early single first-tile failures on the board are unexplained; power is not measured; input/output is over
JTAG; no CPU/GPU speed comparison.
