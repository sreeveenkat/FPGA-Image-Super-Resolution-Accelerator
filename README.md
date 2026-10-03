# FPGA Image Super-Resolution Accelerator (ZedBoard / Zynq-7020)

A small **INT8 convolutional neural network** that upscales images **2×** (target: 960×540 → 1920×1080), trained in PyTorch and
being built as a tile-based accelerator on the **Zynq XC7Z020** (Digilent ZedBoard). The ARM core controls the FPGA over AXI-Lite and
moves image tiles with AXI DMA.

> **Scope change:** this repository started as a *sparse ray tracing + AI 4K reconstruction* idea. On a Zynq-7020 (220 DSP slices) native 4K
> reconstruction is not realistic, so the project is now a **low-resolution super-resolution accelerator (≤ 1080p output)**. The ray-traced
> front end is kept as an optional extension. The original notes are in [`docs/resources/`](docs/resources/).

## Status

| Milestone | What | Board needed | Status |
|---|---|---|---|
| M0 | Zynq basics: UART, AXI GPIO, own AXI-Lite IP, DMA loopback | yes | not started (waiting for board) |
| **M1** | Bicubic baseline + metrics + datasets | no | **done** |
| **M2** | FP32 CNN training and evaluation | no | **done** |
| M3 | INT8 quantization + bit-accurate integer Python model | no | next |
| M4 | One convolution layer in Verilog (cocotb, bit-exact) | simulation | planned |
| M5 | Full network RTL, pixel shuffle, tiling with halo | simulation | planned |
| M6 | AXI wrapper, DMA, ARM driver | yes | planned |
| M7 | Benchmark, resource/timing/power report | yes | planned |
| M8 | Optional: HDMI, ×4, luma-only, ray-traced input, custom multiplier | — | optional |

Step-by-step guides for every milestone are in [`docs/milestones/`](docs/milestones/README.md).

## The network

```
RGB (+3 px halo) → Conv3×3 (3→16) + ReLU → Depthwise 3×3 (16) + ReLU → Conv1×1 (16→16) + ReLU → Conv3×3 (16→12) → PixelShuffle(2) → RGB ×2
```

* 2,620 parameters, 2,560 multiply-accumulates per input pixel (≈ 1.3 GMAC for a 960×540 frame).
* All convolutions are **valid** (no padding): the input carries a 3-pixel border, so processing an image in tiles gives the same result as
  processing it whole. This is exactly how the FPGA tile engine will work.
* Chosen to be hardware friendly: ReLU only, no residual connections, pixel shuffle is pure re-addressing.

## Results so far (×2, measured)

Bicubic uses the same low-resolution protocol as the standard benchmarks (Pillow bicubic; bit-exact with the official LR files for
even-sized images). PSNR is on the Y channel with a 2-pixel border shaved; SSIM is the Gaussian 11×11 definition.

| Test set | Bicubic PSNR-Y | FP32 CNN PSNR-Y | Gain | SSIM-Y bicubic → CNN |
|---|---|---|---|---|
| Set5 (5) | 33.67 dB | 35.21 dB | +1.53 | 0.9303 → 0.9449 |
| Set14 (14) | 30.32 dB | 31.51 dB | +1.18 | 0.8698 → 0.8975 |
| BSD100 (100) | 29.56 dB | 30.60 dB | +1.04 | 0.8434 → 0.8785 |

* Better than bicubic on **119 of 119** test images; the worst image still gains +0.46 dB.
* Two training seeds differ by 0.03–0.09 dB, so quote the gain as roughly **+1.0 to +1.5 dB (±0.1)**.
* Verified at the target size: 960×540 → 1920×1080 runs in ~0.1 s on a CPU, and 135 tiles (64×64 core + 3 px halo) reproduce the
  whole-image output to 6.6e-7.
* Limits: fine random texture (gravel, fur, fabric weave) is not recovered; that is expected for a 2.6 K-parameter network.
* Quantization (M3) and all hardware numbers (resources, timing, fps) are **not measured yet**.

Details, ablations (SSIM loss, 24 channels, edge windows: all within noise) and the reproducibility notes:
[`results/quality/m2_training_summary.md`](results/quality/m2_training_summary.md).

## Repository layout

```
docs/          plan, milestone guides, original notes
software/ai/   dataset, models, training, quantization, evaluation (Python)
software/arm_driver/, software/host_tools/   ARM C driver and PC helpers (later milestones)
hardware/      rtl/ (Verilog), verification/ (cocotb), vivado/ (scripts, constraints)
data/          datasets and golden vectors (git-ignored, see data/README.md)
results/       measured quality tables and plots
CLAUDE.md      running project log: decisions, status, measured numbers
```

## Reproduce the software results

```bash
python3 -m venv --system-site-packages .venv && .venv/bin/pip install -r requirements.txt   # PyTorch 2.x is also required
software/ai/scripts/fetch_div2k_subset.sh 192          # training images (DIV2K subset from a Hugging Face mirror)
# Set5 / Set14 / BSD100 HR + official x2 LR: see data/README.md for the sources and folder layout

.venv/bin/python software/ai/dataset/check_dataset.py           # data sanity + no train/test overlap
.venv/bin/python software/ai/dataset/check_lr_protocol.py       # LR protocol matches the official files
.venv/bin/python software/ai/evaluation/eval_baseline.py        # bicubic / nearest baselines
.venv/bin/python software/ai/training/train.py --epochs 100 --steps 500 --images 192 --val 12 --threads 4 \
                 --out software/ai/checkpoints/srnet_fp32.pt    # ≈ 10–35 min on a CPU
.venv/bin/python software/ai/evaluation/eval_model.py           # model vs bicubic on all test sets
.venv/bin/python software/ai/evaluation/check_target_res.py     # 960×540 → 1080p and tiled == whole image
.venv/bin/python -W error software/ai/evaluation/test_baseline.py
.venv/bin/python -W error software/ai/evaluation/test_model.py
```

Training is statistically but not bit-for-bit reproducible (thread count changes floating-point summation order); the trained
checkpoints (14 KB each) are therefore committed in `software/ai/checkpoints/`.

## Planned verification chain

`PyTorch FP32` → `NumPy integer model (golden)` → `RTL`. The RTL will be compared bit-for-bit with the integer model, never with PyTorch.

## References

* Dong et al., *Accelerating the Super-Resolution Convolutional Neural Network* (FSRCNN), ECCV 2016.
* Ahmed et al., *Super-Resolution CNN Accelerator on Low-Cost Zynq-7000 Series SoC-based FPGA*, URSI 2024.
* *Quantized Neural Network Architecture for Hardware Efficient Real-Time 4K Image Super-Resolution*, VDAT 2024.
* *An FPGA implementation of Whitted-style ray tracing accelerator* (used for the optional ray-tracing extension).

The papers are not redistributed here because they carry institutional IEEE licence notices.
