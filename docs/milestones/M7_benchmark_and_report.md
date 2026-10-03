# M7 — Benchmark, Compare and Write the Report

**Time:** 1–2 weeks | **Where:** PC + board | **Depends on:** M6 (working system)

---

## 1. Why this milestone exists

A working circuit is not yet a project result. A result is **numbers someone else can check**:
"how good is the picture, how fast, how big, how much power". This milestone collects those numbers and packages everything
so a teacher, interviewer or your future self can reproduce it.

The rule: **never report a number you did not measure.** If the FPGA gets 1.2 fps, say 1.2 fps — not "real time".

---

## 2. What to measure

### A. Image quality (PC side, same test images for every row)

| Method | PSNR (dB) | SSIM |
|---|---|---|
| Nearest neighbour (M1) | | |
| Bicubic (M1) | | |
| FP32 CNN (M2) | | |
| INT8 integer model (M3) | | |
| **FPGA output (M6)** | | |

Expected: **FPGA row == INT8 row exactly** (they are the same arithmetic). The drop from FP32 to INT8 is a real, reportable result.

### B. Speed

| Metric | How to measure |
|---|---|
| Cycles per tile | `CYCLES` register in the core |
| Time per frame | ARM global timer around the whole tile loop (split: compute, DMA, ARM copy) |
| FPS | `1 / time_per_frame` |
| Pixels/s | input pixels ÷ time |
| DMA bandwidth | bytes moved ÷ DMA time |
| Breakdown | % of time in core vs DMA vs ARM copying — shows the real bottleneck |

Cross-check with your prediction: `tiles × cycles_per_tile / clock_frequency`.

### C. Resources and timing (Vivado, after implementation)

```tcl
report_utilization    -file util.txt
report_timing_summary -file timing.txt
report_power          -file power.txt
```
Record: LUT, FF, BRAM, DSP (and % of the chip), worst setup slack (WNS must be ≥ 0), maximum achievable clock.

### D. Power and energy (estimate)
Vivado's power report gives an *estimate*, not a measurement. Say "estimated". Energy per frame ≈ power × time per frame.

### E. Optional comparison
The same network on the PC CPU (PyTorch, timed) as a reference point. Compare honestly; a CPU or GPU will usually be faster in
raw speed; the FPGA's selling points are determinism, power and integration.

---

## 3. Step-by-step

1. Make a script `software/ai/evaluation/run_all.py` that, for each test image, builds the table in section A.
2. Run the board on the same test images; save the outputs and compare with the integer model.
3. Add timing code in the driver; run 20 frames; report mean and spread.
4. Generate Vivado reports; copy into `results/`.
5. Make the **demo figure**: bicubic | FPGA output | ground truth, with zoomed crops of edges and text.
6. Write `README.md` (below) and `results.md` with all tables.
7. Clean the repository (no generated Vivado folders; commit scripts, constraints, `.mem` files, small test vectors, reports).

---

## 4. README contents

1. One-paragraph description and the headline result with real numbers.
2. Block diagram (from M0/M4/M5/M6).
3. Network description (layers, parameters, MACs).
4. Quantization scheme (types, M/SHIFT, rounding).
5. How to reproduce: dataset → train → quantize → build bitstream → run on board (exact commands).
6. Results tables (A, B, C).
7. Verification summary (reference chain; seam test; bit-exact results).
8. Limitations and what failed (be honest — it is valued).
9. Future work.

## 5. Output of this milestone

- `results/` with quality table, speed table, utilization/timing/power reports, comparison images.
- `README.md` that lets another person reproduce the project.
- A short demo (photo/video of the board running + before/after images).

## 6. Exit checklist

- [ ] All three tables filled with measured values.
- [ ] FPGA output bit-exact with the integer model on all test images.
- [ ] Timing met (WNS ≥ 0) at the frequency you report.
- [ ] README reproduces the build from scratch (try it on a clean folder).
- [ ] No claim without a number behind it.

## 7. Example "honest" summary sentence

> "A 2.6 K-parameter INT8 super-resolution CNN on a ZedBoard (XC7Z020, 100 MHz) upscales 960×540 images to 1920×1080 in
> **X ms** using **Y DSPs / Z BRAM**, with PSNR **P dB** versus bicubic's **Q dB** on Set14."
Fill X, Y, Z, P, Q only from your own measurements.
