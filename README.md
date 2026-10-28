# FPGA Image Super-Resolution Accelerator (ZedBoard / Zynq-7020)

A small **INT8 convolutional neural network** that upscales images **2×** (960×540 → 1920×1080), trained in PyTorch and run by a tile-based
accelerator in the fabric of a **Zynq XC7Z020** (Digilent ZedBoard). The ARM core controls the accelerator over AXI-Lite and moves image tiles
with AXI DMA. `main` holds this deployed tile design; a faster whole-frame layer pipeline lives on branch `pipe` (see the headline results and the table of the six designs below).

## Headline results

Measured on a ZedBoard unless marked as an estimate. All outputs are compared byte for byte with the software integer model.

* **Whole-frame layer pipeline (branch [`pipe`](../../tree/pipe), not on `main`): 95.4 ms per 960×540 → 1920×1080 frame = 10.49 fps at 125 MHz** (mean of 20 frames, clock read back from the PS registers; 95.36 ms, min 95.19, max 96.79).
  With optional **non-cacheable DMA buffers: 70.5 ms = 14.2 fps**, a second configuration that is *not* the default: it applies when the output goes to another DMA master such as a display,
  because ARM reads of the output buffer become about 10× slower (620 vs 64 ms for the 6.2 MB checksum read).
* **13.8× faster than the deployed tile design R0** (1,311.7 ms = 0.762 fps at 100 MHz) and about **140× faster than the ARM core alone** (13.437 s per frame, mean of 3 runs: one Cortex-A9 core at 650 MHz, plain C, no NEON, `-O2`).
* **Byte-exact on 119 of 119 test images** (Set5, Set14, BSD100) on the board for R0, r0_125, r3q_125 and the pipeline; R2q and R3q were checked byte-exact on the 960×540 frame only.
  Quality of the R3q weights (the pipeline uses them): +1.1 dB PSNR-Y over R0 on Set5 (Set5 36.05 / Set14 32.05 / BSD100 30.96 dB, 2-seed mean of the recipe, vs 34.93 / 31.35 / 30.48 for R0; bicubic 33.67 / 30.32 / 29.56).
* **Efficiency, Vivado estimate from simulated switching activity (not measured): 12.5 GOPS/W for the whole chip and 42.5 GOPS/W for the programmable logic alone** (27.8 GOPS end to end; 17.0 / 57.5 GOPS/W with non-cacheable buffers).
  **Power has not been measured with an instrument yet** (no meter); the Vivado numbers are in [`results/power_estimate/SUMMARY.md`](results/power_estimate/SUMMARY.md).
* Resources of the pipeline: 170 DSP (77 %), 27 BRAM, 9,888 LUT, timing met at 125 MHz (WNS +0.267 ns). The deployed R0: 68 DSP (31 %), 72 BRAM (51 %), 100 MHz.

## The six designs (which branch holds which)

**The pipeline design is on branch `pipe`.** `main` holds the deployed tile design R0, the documentation, results and all tools; the other designs are variants on their own branches, each with its own bitstream VERSION.
Board times are the 20-frame means of 2026-10-27 (100 MHz) and 2026-10-28 (125 MHz).

| Design | Branch | What it is | PL clock | Frame time on the board | fps |
|---|---|---|---|---|---|
| R0 | `main` | the deployed tile design: four layer engines, one after the other, 64×64 tiles with halo | 100 MHz | 1,311.7 ms | 0.762 |
| R2q | `r2q` | R0's hardware with re-parameterized + QAT weights (+0.87 / +0.50 / +0.36 dB PSNR-Y over R0's 2-seed mean) | 100 MHz | 1,312.0 ms | 0.762 |
| R3q | `r3q` | anchor network + QAT weights (+1.12 / +0.70 / +0.49 dB), small RTL change (anchor folded into the requantizer) | 100 MHz | 1,311.6 ms | 0.762 |
| r0_125 | `r0_125` | R0 with one more register per MAC lane so it closes timing at 125 MHz | 125 MHz | 1,061.9 ms | 0.942 |
| r3q_125 | `r3q_125` | R3q at 125 MHz | 125 MHz | 1,061.7 ms | 0.942 |
| **pipeline** | **`pipe`** | **whole-frame layer pipeline** (all four layers work at once, line buffers, no tiles; [`docs/ARCHITECTURE_PIPELINE.md`](docs/ARCHITECTURE_PIPELINE.md) on that branch), R3q weights | 125 MHz | **95.4 ms** (70.5 ms with non-cacheable DMA buffers) | **10.49** (14.2) |

Details, VERSION values, checksums and every measurement: [`docs/STATUS.md`](docs/STATUS.md), [`results/board/2026-10-27/SUMMARY.md`](results/board/2026-10-27/SUMMARY.md),
[`results/board/2026-10-28/SUMMARY.md`](results/board/2026-10-28/SUMMARY.md). Clone a design with `git checkout <branch>`.

## Earlier headline (the deployed design R0, measured 2026-10-12)

A 960×540 frame is upscaled to 1920×1080 in **1.312 s (0.76 fps)** at 100 MHz, and the output is **byte-identical to the software integer model** on all **119** test images (Set5, Set14, BSD100).
Quality: **+1.0 to +1.4 dB PSNR-Y over bicubic** (Set5 35.02 / Set14 31.40 / BSD100 30.53 dB vs 33.67 / 30.32 / 29.56), better than bicubic on 119 of 119 images. The design uses 68 DSPs (31 %) and
72 BRAM tiles (51 %); the power is **estimated** by Vivado at 1.91 W for the whole chip, 0.18 W of it the accelerator.


> **Scope change:** this repository started as a *sparse ray tracing + AI 4K reconstruction* idea. On a Zynq-7020 (220 DSP slices) native 4K
> reconstruction is not realistic, so the project is a **low-resolution super-resolution accelerator (≤ 1080p output)**. The ray-traced
> front end is kept as an optional extension.

## Status

| Milestone | What | Board needed | Status |
|---|---|---|---|
| M0 | Zynq basics: UART, AXI GPIO, own AXI-Lite IP, DMA loopback | yes | **done** 2026-10-11 |
| M1 | Bicubic baseline + metrics + datasets | no | **done** |
| M2 | FP32 CNN training and evaluation | no | **done** |
| M3 | INT8 quantization + bit-accurate integer Python model | no | **done** |
| M4 | Convolution engine in Verilog, bit-exact with the integer model | simulation | **done** |
| M5 | Full network RTL, pixel shuffle, tiling with halo | simulation | **done** |
| M6 | AXI wrapper, DMA, ARM driver, running on the board | yes | **done** 2026-10-11 (0602 build 2026-10-12) |
| M7 | Benchmark, resource/timing/power report, reproducible build | yes | **mostly done**: tables A-D measured, build reproduced from a clean clone; report in progress |
| M8 | Optional: HDMI, ×4, luma-only, ray-traced input, custom multiplier | — | not started |

Checking everything yourself:
[`docs/VERIFY_YOURSELF.md`](docs/VERIFY_YOURSELF.md). Demo script for a review: [`docs/DEMO.md`](docs/DEMO.md).

## Results on the board (M6/M7)

| Table | What | Value | Record |
|---|---|---|---|
| A quality | PSNR-Y / SSIM-Y, FPGA output (= INT8 model) | Set5 35.02 / 0.9420, Set14 31.40 / 0.8948, BSD100 30.53 / 0.8756; all 119 board outputs byte-exact | [`table_a_x2.md`](results/quality/table_a_x2.md) |
| B speed | 960×540 → 1920×1080, mean of 20 frames | **1,311.9 ms = 0.762 fps** (spread 1.7 ms); 95 % of it is the accelerator computing (926,220 cycles per 64×64 tile, 135 tiles); ARM copies 2 %, DMA overhead 2 % | [`m7_timing_20frames.md`](results/speed/m7_timing_20frames.md), [`m6_board.md`](results/speed/m6_board.md) |
| C resources | whole system (PS7 + DMA + accelerator), routed | 5,296 LUT (10 %), 7,831 FF (7 %), 72 BRAM (51 %), 68 DSP (31 %); timing met at 100 MHz, WNS +0.503 ns, WHS +0.016 ns | [`m6_system_0602.md`](results/utilization/m6_system_0602.md) |
| D power | Vivado **estimate** (confidence Low, not measured) | 1.91 W chip (PS7 1.56 W, accelerator 0.18 W); ~2.5 J per frame (accelerator alone ~0.23 J) | [`m7_power.md`](results/utilization/m7_power.md) |

Robustness on the board: 2 × 1,000 tiles without an error, 50 fresh program loads, error recovery 10/10 ([`m6_system_0602.md`](results/utilization/m6_system_0602.md)).
Demo figures (test images run on the board): [`docs/demo/`](docs/demo/).

## The network

```
RGB (+3 px halo) → Conv3×3 (3→16) + ReLU → Depthwise 3×3 (16) + ReLU → Conv1×1 (16→16) + ReLU → Conv3×3 (16→12) → PixelShuffle(2) → RGB ×2
```

* 2,620 parameters, 2,560 multiply-accumulates per input pixel (≈ 1.3 GMAC for a 960×540 frame).
* All convolutions are **valid** (no padding): the input carries a 3-pixel border, so processing an image in tiles gives the same result as
  processing it whole. This is exactly how the FPGA tile engine works.
* Chosen to be hardware friendly: ReLU only, no residual connections, pixel shuffle is pure re-addressing.


## FP32 model quality (M2, measured)

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

Details, ablations (SSIM loss, 24 channels, edge windows: all within noise) and the reproducibility notes:
[`results/quality/m2_training_summary.md`](results/quality/m2_training_summary.md).

## INT8 integer model (M3, measured)

Post-training quantization (no retraining): uint8 activations, int8 symmetric per-layer weights, int32 accumulators, per-layer
requantization `(acc·M + 2^(SHIFT-1)) >> SHIFT` with a 16-bit `M`. The NumPy integer model (`software/ai/quantization/integer_reference.py`)
is pure integer arithmetic and is the bit-exact reference for the RTL. Quantization settings (99.99th-percentile activation range,
per-layer weight scale) were chosen on 12 *validation* images, never on the test sets.

| Test set | FP32 PSNR-Y | INT8 PSNR-Y | Drop | INT8 SSIM-Y |
|---|---|---|---|---|
| Set5 (5) | 35.21 dB | 35.02 dB | 0.18 | 0.9420 |
| Set14 (14) | 31.51 dB | 31.40 dB | 0.11 | 0.8948 |
| BSD100 (100) | 30.60 dB | 30.53 dB | 0.08 | 0.8756 |

* Mean drop per set as shown; the worst single image loses 0.41 dB. INT8 still beats bicubic on 119 of 119 images.
* Tiled (64×64 core + 3 px halo) output equals whole-image output **exactly** (integer maths, no float rounding).
* Weights, biases, multipliers and golden tiles for the RTL are exported to `hardware/rtl/weights/` (format: its `README.md`).
* The sweep over quantization settings is in [`results/quality/m3_ptq_sweep.md`](results/quality/m3_ptq_sweep.md), full tables in
  [`results/quality/model_int8_x2.md`](results/quality/model_int8_x2.md).

## Convolution engine in RTL (M4, simulated + synthesized)

`hardware/rtl/conv_engine/conv_engine.v` is a folded convolution engine for one layer (one instance per layer): one MAC lane per output
channel (DSP48), a shared requantizer that overlaps with the next pixel, and a step-major weight ROM. Every layer reproduces the golden
integer model **bit for bit** on 10 golden tiles (zeros, saturated, noise, single pixel, ramp, real image tiles, a border tile), plus
randomized layers with distinct per-channel multipliers on a non-square tile. The testbenches are self-checking Verilog run with Icarus
(`hardware/verification/run_tests.sh`).

| Layer | Cycles / output pixel | Cycles per 64x64 tile (simulated) | LUT | FF | DSP | BRAM36 | WNS @ 100 MHz (routed) |
|---|---|---|---|---|---|---|---|
| L1 conv 3->16 | 27 | 124,872 | 298 | 851 | 18 | 2 | +3.853 ns |
| L2 depthwise 16 | 16 | 69,713 | 398 | 953 | 18 | 0 | +3.393 ns |
| L3 pointwise 16->16 | 16 | 69,720 | 369 | 841 | 18 | 0 | +2.913 ns |
| L4 conv 16->12 | 144 | 589,844 | 349 | 693 | 14 | 1.5 | +3.146 ns |

* Vivado 2024.1 out-of-context **synthesis and place-and-route**, one engine at a time (no I/O timing, no activation RAMs): all four layers meet
  100 MHz with no failing endpoints (margins +2.9 to +3.9 ns after the 2026-10-09 timing fix: one register stage after the requantizer-feed mux, +1 cycle per engine). All four instances together use 68 of 220 DSPs (31 %).
  The synthesized netlists were also simulated (xsim) and are bit-exact on the golden tile.
* A plain 70x70x128-bit activation buffer infers **32 RAMB36 (23 % of the chip)**, more than the ~20 first planned; M5 fixed this with a split RAM (18.5 tiles, see below).
* 854,149 engine cycles per tile x 135 tiles = 115 M cycles = about 1.15 s per 960x540 frame at 100 MHz, **compute only and from simulation**. The chained
  core with byte-wide I/O (M5, below) needs 926,201 cycles per tile (about 1.25 s per frame); DMA and ARM time are not included (board: 1.312 s per frame, see above).
* Details, pitfalls found (a ROM initialisation that simulated fine but was ignored by Vivado) and the breakage tests:
  [`results/utilization/m4_conv_engine.md`](results/utilization/m4_conv_engine.md).

## Full tile core in RTL (M5, simulated + synthesized)

`hardware/rtl/sr_core/sr_tile_core.v` takes one tile as a byte stream (70x70 RGB with a 3 px halo), runs the four conv engines one after the other
through five activation RAMs, applies the pixel shuffle and streams the 128x128 RGB result out (valid/ready handshakes, `out_last`).
It is **bit-exact with the integer model**: every layer buffer and the output stream match the golden data on 9 real-size tiles (also with random stalls
on both streams), and the **seam test** passes: tiles cut with a 3 px halo from a real image (not a multiple of the tile size), run through the RTL and pasted
together, equal the whole-image result exactly (20 tiles at a small core size, 4 tiles at the real 64x64 core). One-cycle-reset aborts at 60 different
moments leave the core quiet, and the synthesized netlist passes the same stream test.

| Whole core (HC = 64) | Value |
|---|---|
| Cycles per tile (simulated, no stalls) | 926,201 (engines 854,149 + byte-wide load/output 72,052) |
| Frame estimate, 960x540 = 135 tiles | about 1.25 s at 100 MHz (~0.80 fps), compute + byte streams only, simulation (board: 1.312 s) |
| LUT / FF / DSP / BRAM36 tiles (after place and route) | 1,896 / 3,341 / 68 (31 %) / 70 (50 %) |
| Routed setup slack at 100 MHz | **+0.723 ns** (was +0.234 ns before the 2026-10-09 timing fix; out-of-context, no I/O timing), hold +0.085 ns |

* Block-RAM finding: Vivado rounds the depth of a cascaded RAM up to a power of two, so one 4624x128-bit buffer needs 32 tiles; splitting the address
  range (`tile_ram_split`) needs 18.5. Without it the five buffers would not leave room on the chip.
* Details, design decisions and the breakage checks: [`results/utilization/m5_tile_core.md`](results/utilization/m5_tile_core.md).


## System on the board (M6)

```
ARM Cortex-A9 (bare-metal C, software/board/sr_app)          FPGA fabric, 100 MHz
  pad image, cut 70×70 tiles, place 128×128 results    ──AXI-Lite (GP0, 0x4000_0000)──▶ sr_accel_top: CONTROL/STATUS/CYCLES/ERROR/VERSION
  DDR ◀──── HP0 ────▶ AXI DMA (0x4040_0000) ──AXI-Stream 32 bit──▶ sr_axis_wrapper ──▶ sr_tile_core (L1→L2→L3→L4 → pixel shuffle) ──▶ back to the DMA
```
* `hardware/rtl/top/sr_accel_top.v`: AXI-Lite registers ([`docs/REGISTER_MAP.md`](docs/REGISTER_MAP.md)) + AXI-Stream wrapper around the M5 core. VERSION 0x53520602.
* `software/board/`: driver (DMA, timeouts, reset/recovery), tiling, tests T1 golden tile, T2 whole image, T3 timing, T5 error recovery, T6 stress;
  `run_board.tcl` (xsdb) programs the FPGA safely (PL held in reset and PS-PL level shifters off while it is reprogrammed), loads the program and
  moves images in and out over JTAG. Details: [`software/board/README.md`](software/board/README.md).

## Repository layout

```
docs/          demo script (DEMO.md), demo figures, register map, verification guide, project guide, status
software/ai/   dataset, models, training, quantization, evaluation (Python)
software/board/   ARM program (sr_app/), board scripts (xsdb, bash), platform + ELF build
software/host_tools/   PC helpers: png <-> raw, expected output, compare, figures
hardware/rtl/  Verilog: common, conv_engine, sr_core, axi_wrapper, top; rtl/weights = exported network parameters
hardware/verification/   testbenches (tb/), run_tests.sh, run_postsynth.sh, demo_sim.sh
hardware/vivado/   scripts/ (synthesis, system build, power), bd/ (block design as Tcl), ip_repo/ (M0 adder IP)
data/          datasets, golden vectors, board files (git-ignored, see data/README.md)
results/       measured numbers: quality/ speed/ utilization/
```

## Reproduce from scratch

**Tested on 2026-10-12 in a fresh `git clone` in an empty folder** (commit `e12c898`), on the machine below. Every step ran there and gave the
results listed under "Check"; the bitstream built from the clone has the same utilization, timing and power as the board-tested 0602 build, and
on the board it gave byte-identical results, including all 119 test images (record: [`m7_clean_clone_build.md`](results/utilization/m7_clean_clone_build.md)). Not re-run in that test: the dataset downloads (copied from the main folder) and the 33-minute
training (the trained checkpoint is committed; training is not bit-reproducible, see below).

**Needs:** Ubuntu 24.04 (tested), Python 3.12 with PyTorch 2.x, NumPy, OpenCV and Pillow (system packages here), Icarus Verilog 12,
Vivado + Vitis **2024.1** with the Digilent ZedBoard board files, a ZedBoard on the PROG/JTAG USB port (J17), boot jumpers on JTAG.
About 1 GB of disk for the data and 1 GB for the build.

```bash
# 0. checkout + Python environment
git clone https://github.com/sreeveenkat/FPGA-Image-Super-Resolution-Accelerator.git sr && cd sr
python3 -m venv --system-site-packages .venv && .venv/bin/pip install -r requirements.txt   # pip may time out on a slow network: just re-run it
source <Xilinx install>/Vitis/2024.1/settings64.sh                                       # vivado, vitis, xsdb on the PATH

# 1. data (git-ignored)
software/ai/scripts/fetch_div2k_subset.sh 192             # DIV2K training images -> data/train/HR
# Set5 / Set14 / BSD100 HR + official x2 LR -> data/test/HR, data/test/LR_official: sources in data/README.md
.venv/bin/python software/ai/evaluation/eval_baseline.py   # FIRST: makes data/test/LR + the bicubic/nearest baselines
.venv/bin/python software/ai/dataset/check_dataset.py      # Check: "OK: all files decode, no duplicates, no train/test overlap, all test LR present"

# 2. model (M2-M3). Training is optional: software/ai/checkpoints/srnet_fp32.pt is committed.
# .venv/bin/python software/ai/training/train.py --epochs 100 --steps 500 --images 192 --val 12 --threads 4 --out software/ai/checkpoints/srnet_fp32.pt
.venv/bin/python software/ai/quantization/quantize.py      # -> qparams.npz
.venv/bin/python software/ai/quantization/export_rtl.py    # -> hardware/rtl/weights/*.mem + data/golden/
.venv/bin/python software/ai/quantization/gen_unit_vectors.py
git status --short                                         # Check: empty (all regenerated files byte-identical to the committed ones)
.venv/bin/python -W error software/ai/quantization/test_integer.py && .venv/bin/python -W error software/ai/quantization/test_export.py
.venv/bin/python software/ai/evaluation/run_all.py --no-fpga   # Check: "max |recomputed - published| over all metrics: 0" (~30 s)

# 3. RTL simulation (M4-M5)
hardware/verification/run_tests.sh quick                   # Check: "36 test runs passed, 0 failed" (~3 min)

# 4. bitstream (M6): new Vivado project from the repo, ~7 min. Keep 2 jobs: 8 froze a 15 GB PC.
vivado -mode batch -nojournal -log ../m6_build.log -source hardware/vivado/scripts/build_m6_system.tcl -tclargs $PWD/../m6_build 2
# Check: "WNS 0.503  WHS 0.016" and "BUILD_OK"; the log says 12 x "<this checkout>/hardware/rtl/weights/... is read successfully"

# 5. ARM program: Vitis platform (BSP) from the new XSA, then the test programs
vitis -s software/board/create_platform.py $PWD/../m6_build/design_1_wrapper.xsa $PWD/../m6_ws        # Check: "PLATFORM_OK" (~30 s)
export SR_BSP=$PWD/../m6_ws/m6_platform/export/m6_platform/sw/standalone_ps7_cortexa9_0 SR_LSCRIPT=$PWD/software/board/sr_app/lscript.ld
.venv/bin/python software/host_tools/golden_tile_h.py      # golden tile header for T1
for n in 1 2 3; do software/board/build_elf.sh $n; done    # -> software/board/build/sr_app_t{1,2,3}.elf

# 6. on the board (power on, fresh or not)
export SR_BIT=$PWD/../m6_build/m6_sr.runs/impl_1/design_1_wrapper.bit
.venv/bin/python software/host_tools/make_test_images.py
.venv/bin/python software/host_tools/expected_output.py data/board/div2k_img0193_lr_960x540.raw data/board/div2k_img0193_expected_1920x1080
xsdb software/board/run_board.tcl software/board/build/sr_app_t1.elf - - t1.txt
# Check t1.txt: result=0, version=0x53520602, stat6=20 (20 repeats identical), stat0/1 = CYCLES ~926,217-926,241
xsdb software/board/run_board.tcl software/board/build/sr_app_t2.elf data/board/div2k_img0193_lr_960x540.raw out.raw t2.txt
.venv/bin/python software/host_tools/compare_raw.py out.raw data/board/div2k_img0193_expected_1920x1080.raw   # Check: "BYTE-EXACT: yes", fnv1a32 0xcf947f22
xsdb software/board/run_board.tcl software/board/build/sr_app_t3.elf data/board/div2k_img0193_lr_960x540.raw t3.raw t3.txt
# Check t3.txt: stat1 = mean frame time in us (~1,311,900)

# 7. table A with the FPGA row (all 119 test images on the board, ~11 min)
.venv/bin/python software/host_tools/board_testsets.py prep
software/board/run_testsets.sh                              # Check: "119 byte-exact, 0 failed of 119"
.venv/bin/python software/ai/evaluation/run_all.py          # -> results/quality/table_a_x2.md (FPGA row == INT8 row)
```

Notes:
* `build_elf.sh`, `run_board.tcl` and `demo.sh` default to the paths of the original PC (`~/Desktop/venkat/...`); the `SR_BSP`, `SR_LSCRIPT`
  and `SR_BIT` variables above override them. `demo.sh` has no override yet: on another PC use the commands of step 6.
* `hardware/vivado/bd/design_1_m6.tcl` is `write_bd_tcl` of the board-tested block design. It still contains the two GPIOs and the
  `adder_ip` from M0 (in `hardware/vivado/ip_repo/`) so that the address map and the BSP stay identical to the tested system.
* Steps 1-3 run without the Xilinx tools; step 3 needs only Icarus Verilog. More checks (full regression ~20 min, netlist simulation, breakage
  tests): [`docs/VERIFY_YOURSELF.md`](docs/VERIFY_YOURSELF.md).
* Training is statistically but not bit-for-bit reproducible (thread count changes the floating-point summation order: about 0.02 dB); that is
  why the checkpoint (14 KB) is committed and everything after it is checked byte for byte.

## Newer designs

The six designs, their branches and board times are in the table at the top of this file. They live in separate branches; `main`, its weights and its bitstream are unchanged.
Resources and timing are from Vivado (routed); expected board answers: [`docs/paper/board_expected.md`](docs/paper/board_expected.md); checklist: [`docs/paper/board_checklist.md`](docs/paper/board_checklist.md).

* The three 125 MHz designs were first run on 2026-10-27 at 100 MHz by mistake (the loading script's platform init set 100 MHz after the bitstream); on 2026-10-28 they were run with their own init script and the clock
  **read back as 125.000 MHz** before every run, byte-exact on 119/119 images each. Measured against the model: 1,061.85 / 1,061.68 / 95.36 ms (predicted 1,061.8 / ~1,062 / 95.2 ms).
* The pipeline's DMA-wait overhead (22.4 ms of the 95.4 ms) was measured to be cache maintenance (flush input 2.9, flush output 9.6, invalidate output 9.9 ms); with non-cacheable DMA buffers it disappears (70.5 ms).
* A VERSION check protects every program: a program built for another bitstream stops before it touches the DMA (tested on the board, with a marker in the DMA registers).
* The pipeline's first full-size simulation found a FIFO bug that the whole regression and the mutation study had missed (a counter that no test wrapped); it is fixed, and every counter now has a test that
  crosses its wrap point (`docs/STATUS.md`).

## Verification chain

`PyTorch FP32` → `NumPy integer model (golden)` → `RTL (Icarus, xsim, synthesized netlists)` → `board`. The RTL and the board are compared
**bit for bit** with the integer model, never with PyTorch: per layer and per tile in simulation, the seam test for tiling, and on the board the
golden tile, whole frames and all 119 test images.

## Limitations (honest list)

* **The deployed design is 0.76 fps, not real time.** The four layer engines run one after another and are folded (L4 alone is 64 % of the cycles); tile load, compute and
  output are not overlapped. The whole-frame pipeline (branch `pipe`) answers this: 95.4 ms (10.49 fps) measured on the board at 125 MHz, 70.5 ms with non-cacheable DMA buffers; still not real time at 30 fps, and not merged into `main`.
* **Power is a Vivado estimate** (confidence Low) for the deployed design; **nothing was measured with an instrument** (no meter, power not measured yet for any bitstream; a SAIF-based Vivado estimate for the pipeline and R0 is in `results/power_estimate/`). 82 % of the estimate is the ARM side (PS7).
* **2 single first-tile failures** seen on 2026-10-11 are still unexplained (`results/speed/m6_board.md`); none happened in the thousands of tiles after
  the PL-isolation fix in the loading script.
* Images are moved in and out over JTAG (debugger memory access), not from an SD card or a video input: fine for measuring, not a product.
* The INT8 model loses 0.08-0.18 dB against FP32; fine random texture (gravel, fur, fabric) is not recovered by a 2,620-parameter network.
* PC comparison (measured, [`docs/paper/cpu_baseline.md`](docs/paper/cpu_baseline.md)): the same network in FP32 PyTorch takes 129 ms per frame on one
  CPU thread of an i5-13450HX and 7.9 ms on an RTX 3050 laptop GPU (incl. copies); the deployed FPGA design (1,312 ms) is slower than both; the pipeline (112.1 ms on the board) is faster than one CPU thread (129 ms) and slower than the GPU (7.9 ms).

## Future work

* Speed: decide which design is merged into `main` (the pipeline is on branch `pipe`); reduce the ARM-side cache cost (22 ms) without making ARM reads of the output slow.
* A measured board power figure (needs a meter); the SAIF-based estimate exists (`results/power_estimate/`).
* M8 options: HDMI output, ×4, luma-only network, ray-traced input.

## References

* Dong et al., *Accelerating the Super-Resolution Convolutional Neural Network* (FSRCNN), ECCV 2016.
* Ahmed et al., *Super-Resolution CNN Accelerator on Low-Cost Zynq-7000 Series SoC-based FPGA*, URSI 2024.
* *Quantized Neural Network Architecture for Hardware Efficient Real-Time 4K Image Super-Resolution*, VDAT 2024.
* *An FPGA implementation of Whitted-style ray tracing accelerator* (used for the optional ray-tracing extension).

The papers are not redistributed here because they carry institutional IEEE licence notices.
