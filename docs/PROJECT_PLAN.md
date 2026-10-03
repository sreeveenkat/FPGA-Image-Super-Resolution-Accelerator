# FPGA Image Super-Resolution (Low-Res → High-Res) on ZedBoard — Full Project Plan

Board: **ZedBoard, Zynq-7000 XC7Z020-CLG484** | Tools: Vivado/Vitis 2024.x, Python (PyTorch), C/C++

---

## 1. What is this project? (plain words)

You take a **small, blurry image** (e.g. 480×270) and use a **small neural network (CNN)** to produce a
**big, sharp image** (e.g. 1920×1080). The CNN runs on the **FPGA fabric (PL)**, not on a CPU/GPU.
The ARM processor (PS) on the Zynq just loads the image, starts the accelerator, and collects the result.

```
Low-res image ──► ARM (PS) ──DMA──► FPGA CNN accelerator (PL) ──DMA──► DDR ──► High-res image
  (input)         control            (INT8 convolution engine)                  (output)
```

The earlier .md files add an optional front-end: an FPGA **ray tracer** that *creates* the low-res image
(plus depth + normal maps). That is a second, separate project. **Treat it as optional / Phase 2.**
The core, defensible project is the super-resolution accelerator.

---

## 2. Is it possible? (honest answer)

**Yes — if you scope it correctly. No — if you try "real-time 4K ray tracing + AI" on this board.**

### What the XC7Z020 actually gives you

| Resource | Amount | Meaning for you |
|---|---|---|
| LUTs | 53,200 | Control logic, small multipliers, glue |
| Flip-flops | 106,400 | Pipelines |
| BRAM | 140 × 36 Kb ≈ 630 KB | Line buffers, weights, small tiles |
| DSP48E1 | **220** | The real limit: ~220 multipliers per clock |
| DDR3 (PS side) | 512 MB | Frame buffers (a 4K RGB frame = 24.9 MB) |
| ARM | Dual Cortex-A9 @ ~667 MHz | Control software |
| Realistic PL clock | 100–150 MHz | Don't plan on more |
| Video out | HDMI up to 1080p | 4K can't be displayed; save/transfer it |

### Compute budget (my estimates — verify during Milestone 3)

Small network (from your docs): 3×3 conv (RGB+depth+normal → 16) → depthwise 3×3 → 1×1 pointwise → 3×3 conv (16 → 48) → pixel shuffle ×4.

- MACs per input pixel ≈ 864 + 144 + 256 + 6,912 ≈ **8,200** (the final 16→48 conv dominates)
- A lighter ×2 network (final conv 16→12): ≈ **3,000 MAC/pixel**
- Hardware throughput: ~128 DSP-MACs/cycle used × 100 MHz × ~70 % efficiency ≈ **~9 GMAC/s**

| Input → Output | Network | MACs/frame | Est. time/frame | Est. FPS |
|---|---|---|---|---|
| 480×270 → 1920×1080 (×4) | 8.2k MAC/px | ~1.1 G | ~0.12 s | ~8 |
| 960×540 → 3840×2160 (×4) | 8.2k MAC/px | ~4.3 G | ~0.5 s | ~2 |
| 960×540 → 1920×1080 (×2) | 3k MAC/px | ~1.5 G | ~0.17 s | ~6 |
| 1920×1080 → 3840×2160 (×2) | 3k MAC/px | ~6.2 G | ~0.7 s | ~1.5 |

**Conclusion**
- Producing a correct **4K image from 960×540** on the ZedBoard: **feasible, at ~1–2 fps** (not real-time).
- **Real-time (30 fps)** needs a bigger FPGA (the NIT Calicut paper used a ZCU104 with 1,114 DSPs, 24 fps for 1080p→4K ×2).
- The Zynq-7000 paper in your folder fit an FSRCNN on a similar chip but used **98 % of BRAM and 84 % of LUTs** — so the design is tight; keep the network small.
- Weights are tiny (~8 K parameters = ~8 KB at INT8), so they fit easily in BRAM. The bottleneck is **DSPs and the final 48-channel layer**.
- Be careful with the "4.35 ns" claim in the Zynq paper — that is not a full-image latency.

### Rules to stay safe
1. Success = **correct** output image + **measured** quality/speed/resources. Not "real-time".
2. Don't claim numbers until you measured them.
3. Keep a working baseline at every stage (see Section 9).

---

## 3. Inputs, outputs, and deliverables

| | Description |
|---|---|
| **Input** | Low-res image (PNG/raw), later also depth + normal maps if you add the ray tracer |
| **Process** | INT8 CNN on FPGA, processed in tiles (e.g. 64×64 + 1-pixel halo) |
| **Output** | High-res image stored in DDR, saved to SD card / sent over UART/Ethernet to PC |
| **Quality report** | PSNR and SSIM vs. ground truth, compared with bicubic and the FP32 model |
| **Hardware report** | LUT/FF/BRAM/DSP usage, max clock, power estimate, cycles per frame, FPS |
| **Code** | Python (train/quantize), C/C++ (ARM driver), Verilog/SystemVerilog (RTL), testbenches |
| **Demo** | Side-by-side: bicubic vs. FPGA-AI output vs. ground truth |

---

## 4. System architecture

```
                 ZYNQ XC7Z020
┌──────────────────────────────────────────────────────────┐
│  PS (ARM A9)                       PL (FPGA fabric)      │
│  ┌────────────┐   AXI-Lite    ┌──────────────────────┐   │
│  │ C app      │──────────────►│ Control/Status regs  │   │
│  │ (Vitis)    │               └──────────┬───────────┘   │
│  └─────┬──────┘                          │               │
│        │ AXI HP port         ┌───────────▼────────────┐  │
│  ┌─────▼──────┐   AXI DMA    │  CNN accelerator       │  │
│  │ DDR3 512MB │◄────────────►│  line buffers + MACs   │  │
│  │ in / out   │  AXI-Stream  │  requant + pixel shuf. │  │
│  └────────────┘              └────────────────────────┘  │
└──────────────────────────────────────────────────────────┘
```

Three AXI types (don't mix them up):
- **AXI-Lite** — control/status registers (start, done, width, height…)
- **AXI4 Memory-Mapped** — bulk access to DDR
- **AXI-Stream** — pixel data flowing through the accelerator

---

## 5. The neural network (version 1)

```
Input tile (C_in channels) → 3×3 Conv (16) + ReLU
                           → 3×3 Depthwise + ReLU
                           → 1×1 Pointwise (16) + ReLU
                           → 3×3 Conv (3·r² channels)
                           → Pixel Shuffle ×r  → RGB high-res tile
```

- r = 2 or 4. Start with **r = 2** (cheaper), move to 4 only after it works.
- Start with **RGB only (3 channels)**. Adding depth + normal helps most when the source is a ray tracer.
- The papers suggest options to cut cost: process only the **Y (luma)** channel through the CNN and upscale colour
  channels with simple interpolation; replace deconvolution with interpolation + conv (QFSRCNN, 6,065 parameters).
- Quantization: **INT8 weights/activations, INT32 accumulators**, requantize (scale + shift + clamp) after every layer.

---

## 6. What you need

### Hardware
- ZedBoard (you have it), micro-USB cables (JTAG + UART), SD card, 12 V PSU
- HDMI monitor (optional, for 1080p display)
- PC with ≥16 GB RAM (Vivado is heavy)

### Software
- Vivado + Vitis 2024.x (free WebPACK covers XC7Z020), ZedBoard board files
- Python 3, PyTorch, NumPy, OpenCV, scikit-image (PSNR/SSIM)
- Icarus Verilog or Verilator + cocotb (fast simulation); Vivado simulator when needed
- Serial terminal (screen/putty), git

### Skills you'll build
Zynq PS/PL integration, AXI, DMA, fixed-point/INT8 arithmetic, streaming convolution RTL, PyTorch training and QAT.
You already have Verilog + synthesis experience from RISC-V; the **new** parts are PS/PL/AXI/DMA and CNN hardware.

### Datasets
Public SR datasets for training/testing (DIV2K, General-100, Set5, Set14, BSD100). Make low-res input by downscaling
the high-res image (bicubic). No ray tracer needed for the core project.

---

## 7. Milestones (do them in order; don't skip exit criteria)

### M0 — PS/PL literacy (1–1.5 weeks)
1. Zynq PS hello world over UART.
2. AXI GPIO: read switches, write LEDs from C.
3. Your own AXI-Lite peripheral (write two numbers, read the sum).
4. AXI DMA loopback: DDR → stream → DDR, byte-exact check.

**Output:** DMA round-trip works every power cycle. This is the plumbing for everything else.

### M1 — Software baseline (1 week)
- Python script: load HR image → downscale → bicubic upscale → PSNR/SSIM vs. original.

**Output:** Bicubic PSNR/SSIM numbers. This is the floor your CNN must beat.

### M2 — Train FP32 model (1.5–2 weeks)
- Build the small CNN in PyTorch, train on DIV2K/General-100 patches, L1 loss first (add SSIM later).
- Split by image, never by patch from the same image.

**Output:** FP32 model clearly beating bicubic on held-out images (not a marginal 0.1 dB), no checkerboard/colour artifacts.

### M3 — INT8 quantization + bit-accurate integer model (1 week+)
- QAT (PyTorch `torch.ao.quantization`), export INT8 weights, scales, zero points.
- Write a **pure NumPy integer model** (INT8×INT8 → INT32 → +bias → requant → round → clamp). **This is your RTL's
  source of truth**, not PyTorch's quantized ops.
- Also compute exact MACs/pixel and BRAM needs to confirm the budget in Section 2.

**Output:** INT8 PSNR drop vs. FP32 measured; integer model matches QAT output near-exactly.

### M4 — One conv layer in RTL (2–3 weeks)
- Line buffers (BRAM) + 3×3 window generator + INT8 MAC array (let Vivado infer DSP48) + requantize.
- Verify against the integer Python model with random and boundary inputs (cocotb).

**Output:** Single layer RTL output == Python integer output, bit-exact.

### M5 — Full network + pixel shuffle (2–3 weeks)
- Chain depthwise, pointwise, final conv; pixel shuffle as address logic (no arithmetic).
- Tiling with halo: e.g. 64×64 tile + 1-pixel border, discard the border on output. Wrong halo = visible seams.

**Output:** Full-network RTL matches integer model on real tiles, no seams.

### M6 — AXI wrapper + ARM driver (1.5–2 weeks)
- AXI-Lite registers (CONTROL, STATUS, WIDTH, HEIGHT, INPUT_BASE, OUTPUT_BASE, CYCLE_COUNT…).
- AXI DMA streams tiles in and out of DDR; ARM loops over tiles, polls for done (interrupts later).
- Cycle counter for benchmarking.

**Output:** One command on the ARM turns a low-res image in DDR into a high-res image in DDR, matches the software reference.

### M7 — Integration, benchmarking, report (1–2 weeks)
- Bicubic vs. FP32 vs. INT8 vs. FPGA: PSNR/SSIM table.
- Vivado reports: LUT/FF/BRAM/DSP, timing slack, power. Measured FPS, DMA bandwidth.
- Optional HDMI display at 1080p.

**Output:** Reproducible results + README + demo.

### M8 (optional) — Optimizations / research add-ons
- Custom or posit multiplier in the MAC array (your IIT Dharwad work), evaluated at unit / layer / image level.
- Pack two INT8 multiplies per DSP, zero-skipping, double-buffered DMA, 4× upscale full 960×540 → 3840×2160.

### M9 (optional, separate project) — FPGA ray tracer front-end
- C++ golden ray tracer → fixed-point Python model → RTL ray generator + sphere intersection → AXI stream into DDR.
- Adds depth/normal channels to the CNN input. Do this only after M7 is finished.

---

## 8. Timeline

| Block | Time |
|---|---|
| M0–M3 (learn + software side) | ~5–6 weeks |
| M4–M6 (hardware CNN + ARM) | ~6–8 weeks |
| M7 (report) | ~1–2 weeks |
| **Core project total** | **~3–4 months** at 5–6 h/day |
| M8 / M9 optional | +1 month / +2 months |

Most likely to overrun: **M4/M5** (streaming conv + halo + requant rounding). Budget extra time.

---

## 9. Verification strategy (three reference levels)

```
PyTorch FP32  →  NumPy integer model (bit-accurate)  →  RTL
   (quality)          (source of truth for RTL)        (must match integer model)
```

- Compare RTL against the **integer model**, not against PyTorch.
- Test layer by layer before chaining anything.
- Edge cases: -128×-128, saturation, rounding boundaries, tile borders, odd image sizes, DMA backpressure.
- If the final image is wrong, walk back: FPGA → integer model → INT8 → FP32 → bicubic.

---

## 10. Risks and fallbacks

| Risk | Fallback |
|---|---|
| Network doesn't fit (DSP/BRAM) | Fewer channels (16→8), ×2 instead of ×4, Y-channel only, time-share MACs |
| Too slow | Accept low FPS, report honestly; shrink resolution (480×270 → 1080p) |
| Quantization hurts quality | More QAT epochs, per-channel scales, keep final layer higher precision |
| Tile seams | Bigger halo, verify with a seam-detection image diff |
| Vivado/Vitis version/board-file problems | Pin one version; budget 2–3 extra days in M0 |
| Scope creep | Ray tracer and custom multiplier stay optional until M7 is done |

---

## 11. Suggested repository layout

```
fpga-sr/
├── README.md
├── ai/            train.py, quantize.py, integer_reference.py, eval/
├── rtl/           conv_layer/, line_buffer/, mac/, pixel_shuffle/, axi/, top/
├── verification/  cocotb tests, test vectors
├── software/      arm-driver/ (C), host scripts
├── fpga/          vivado scripts, constraints (.xdc)
└── results/       images, utilization/timing/power reports, benchmark tables
```

Commit scripts, constraints, reports, small test vectors. Don't commit generated Vivado build folders.

---

## 12. Your first 7 days

1. Install Vivado/Vitis, add ZedBoard board files, confirm JTAG + UART work.
2. Hello world on the ARM (M0 step 1).
3. AXI GPIO LEDs/switches (M0 step 2).
4. Python bicubic baseline with PSNR/SSIM on 10 images (M1).
5. Build the PyTorch CNN skeleton and count parameters and MACs.
6. Write the one-page requirements (resolutions, scale factor, metrics).
7. Start the AXI-Lite custom peripheral.

---

## 13. Glossary (quick)

- **PS / PL** — Processing System (ARM) / Programmable Logic (FPGA fabric)
- **CNN** — convolutional neural network; layers of multiply-accumulate on pixel neighbourhoods
- **INT8 / QAT** — 8-bit integers / quantization-aware training
- **MAC** — multiply-accumulate, the basic CNN operation, one DSP48 each
- **Line buffer** — BRAM holding the last few image rows so a 3×3 window can slide over a pixel stream
- **Halo** — extra border pixels around a tile so edges of the tile convolve correctly
- **Pixel shuffle** — rearranges r² channels into an r× larger image (pure addressing)
- **PSNR / SSIM** — image-quality metrics vs. ground truth (higher is better)
- **DMA** — hardware that moves data between DDR and the FPGA without the CPU copying it
