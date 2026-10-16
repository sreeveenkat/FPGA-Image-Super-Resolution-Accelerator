    # Run everything yourself — commands, inputs, outputs, file locations, how to verify

This is the hands-on companion to `docs/PROJECT_EXPLAINED.md` (which explains *what/why*). Here: **which command, what it reads (input),
what it writes (output), where the file is, what you should see, and how you know it is correct.**

* Project folder (called **ROOT**): `/home/sreevenkat/Desktop/venkat/sem_project_all`. **Run every command from ROOT.**
* Python: always `.venv/bin/python` (not plain `python`).
* Lines marked ✅ were re-run on 2026-10-13 and printed exactly what is shown. Board steps (Part 6) were run on 2026-10-12 (board record
  files named next to them); they were not re-run today.

---

## Contents
0. Map of the folders: where inputs, golden data and results live
1. One-time setup (every new terminal)
2. Software M1 — datasets and bicubic baseline
3. Software M2 — the FP32 network
4. Software M3 — INT8 model, golden model, exports for the hardware
5. Hardware in simulation (M4/M5/M6 RTL) — Icarus Verilog and Vivado
6. Hardware on the ZedBoard (M6/M7)
7. Rebuilding the bitstream and the ARM program (optional, long)
8. Tables A–D: where the final numbers come from and how to re-check them
9. Quick checklist (copy/paste, ~10 minutes, no board)
10. Traps — read before you run
11. Troubleshooting

---

## 0. Map of the folders

```
ROOT/
├── software/
│   ├── ai/                      PYTHON (PC)
│   │   ├── dataset/             pairs.py (load images, make LR), check_dataset.py, check_lr_protocol.py
│   │   ├── models/srnet.py      the network definition
│   │   ├── training/train.py    training
│   │   ├── evaluation/          metrics.py, eval_baseline.py, eval_model.py, eval_int8.py, run_all.py, tests
│   │   ├── quantization/        quantize.py, integer_reference.py (GOLDEN MODEL), export_rtl.py, qparams.npz, tests
│   │   ├── checkpoints/         srnet_fp32.pt  (THE trained network, frozen, sha256 f1ae81f706ad3707…)
│   │   └── scripts/             fetch_div2k_subset.sh (download training images)
│   ├── board/                   ARM C PROGRAM + BOARD SCRIPTS
│   │   ├── sr_app/              main.c, sr_driver.c/.h, sr_tiling.c/.h, sr_memmap.h, lscript.ld
│   │   ├── sr_regs.h            register offsets (C view of docs/REGISTER_MAP.md)
│   │   ├── build_elf.sh         compiles the ARM program -> software/board/build/sr_app_t<N>.elf
│   │   ├── run_board.tcl        xsdb script: program FPGA, load ELF, send image, run, read result
│   │   ├── demo.sh              one-command board demo
│   │   └── run_testsets.sh      runs all 119 test images on the board
│   └── host_tools/              PC helpers: srim.py (raw format), make_test_images.py, expected_output.py, compare_raw.py, figures
├── hardware/
│   ├── rtl/                     VERILOG
│   │   ├── common/              mac_unit.v, requant.v, weight_rom.v, tile_ram.v, tile_ram_split.v
│   │   ├── conv_engine/         conv_engine.v (one layer)
│   │   ├── sr_core/             sr_tile_core.v (whole network, one tile)
│   │   ├── axi_wrapper/         sr_axis_wrapper.v (32-bit AXI-Stream <-> bytes)
│   │   ├── top/                 sr_accel_top.v (AXI-Lite registers; the block used in Vivado)
│   │   └── weights/             EXPORTED NETWORK: wrom_L1..4.mem, bias_L*.mem, mult_L*.mem, weights_L*.mem, network_params.vh
│   ├── verification/            run_tests.sh, run_postsynth.sh, demo_sim.sh, tb/ (testbenches)
│   └── vivado/                  scripts/ (synthesis, system build, power), bd/design_1_m6.tcl (block design)
├── data/                        (git-ignored: big or generated files)
│   ├── train/HR/                192 DIV2K training photos (img0193…img0384)
│   ├── test/HR/<Set5|Set14|BSD100>/        the 119 ground-truth test images
│   ├── test/LR/…                our ×2 low-resolution inputs (made by eval_baseline.py)
│   ├── test/LR_official/…       official LR files (only used to validate our LR)
│   ├── golden/                  GOLDEN TEST VECTORS for the RTL (see 4.4)
│   │   ├── unit/                requant vectors + randomized layers
│   │   └── seam/                seam-test tiles
│   └── board/                   board inputs (.raw), expected outputs, board outputs, demo files
│       └── testsets/<set>/      per test image: <name>_lr.raw (input), <name>_exp.raw (expected), <name>_board.raw (from board)
├── results/                     MEASURED NUMBERS (tracked in git)
│   ├── quality/                 baseline_x2, model_fp32_x2, model_int8_x2, table_a_x2 (.md + .csv), m3_ptq_sweep.md, m2_training_summary.md
│   ├── speed/                   m6_board.md, m7_timing_20frames.md (+ stats, logs)
│   ├── utilization/             m4_*, m5_*, m6_*, m7_power.md, m7_clean_clone_build.md (Vivado reports)
│   └── images/                  (git-ignored) comparison pictures made by the evaluation scripts
└── docs/                        README-level docs: PROJECT_EXPLAINED.md, RUN_GUIDE.md (this), REGISTER_MAP.md, DEMO.md, VERIFY_YOURSELF.md, demo/*.png
```

Outside ROOT (board build projects): `~/Desktop/venkat/vitis/m6_sr_0602/` (Vivado project of the board bitstream **0602**,
bitstream `m6_sr.runs/impl_1/design_1_wrapper.bit`), `~/Desktop/venkat/vitis/m6_sr/` (older 0601, fallback).

### The data flow in one picture (input → output of every step)

```
data/train/HR ──train.py──▶ checkpoints/srnet_fp32.pt ──quantize.py──▶ quantization/qparams.npz
                                                                           │
                         export_rtl.py ◀───────────────────────────────────┘
                           │                          │
                           ▼                          ▼
        hardware/rtl/weights/*.mem            data/golden/*.hex, *.npz  (inputs + expected outputs per layer)
                           │                          │
                           └──────▶ Verilog testbenches (run_tests.sh) compare RTL output with golden ─▶ PASS/FAIL
                           └──────▶ Vivado bitstream ─▶ board

data/test/HR ──eval_baseline.py──▶ data/test/LR + results/quality/baseline_x2.*
data/test/LR ──eval_model.py──▶ results/quality/model_fp32_x2.*      ──eval_int8.py──▶ results/quality/model_int8_x2.*
data/board/<img>_lr.raw ──(board)──▶ <img>_board.raw  ──compare_raw.py── vs ──▶ <img>_exp.raw (expected_output.py = integer model)
```

---

## 1. One-time setup (do this in every new terminal)

```bash
cd ~/Desktop/venkat/sem_project_all
.venv/bin/python --version                    # Python 3.12.x
iverilog -V | head -1                         # Icarus Verilog version 12.0
# only for Vivado / Vitis / xsdb (Parts 5.4, 6, 7):
source ~/Desktop/vivado_install/Vivado/2024.1/settings64.sh
source ~/Desktop/vivado_install/Vitis/2024.1/settings64.sh
```

Check the frozen model and the data ✅:
```bash
sha256sum software/ai/checkpoints/srnet_fp32.pt | cut -c1-16     # f1ae81f706ad3707
ls data/train/HR | wc -l                                         # 192
ls data/test/HR                                                  # BSD100  Set14  Set5
ls data/golden | head -3                                         # full255_in.hex  full255_L1.hex  full255_L2.hex
```
**Why:** every later number was derived from exactly this checkpoint. If the hash differs, nothing will match.

Lint (syntax check of all Python) ✅:
```bash
.venv/bin/python -m pyflakes $(git ls-files 'software/*.py'); echo "exit=$?"     # no output, exit=0
```

---

## 2. Software M1 — datasets and bicubic baseline

### 2.1 Dataset check ✅
| | |
|---|---|
| Command | `.venv/bin/python software/ai/dataset/check_dataset.py` |
| Input | `data/train/HR/*`, `data/test/HR/*/*`, `data/test/LR/*/*` |
| Output | text only |
| Why | proves train and test images are different (no cheating) and all files decode |

Expected:
```
train images: 192   test images: 119
train size range: min 816 px short side; max 2040 px long side
OK: all files decode, no duplicates, no train/test overlap, all test LR present
```

### 2.2 LR protocol check ✅
| | |
|---|---|
| Command | `.venv/bin/python software/ai/dataset/check_lr_protocol.py` |
| Input | `data/test/HR`, `data/test/LR_official` |
| Why | proves our low-resolution images equal the official benchmark ones |

Expected:
```
Set5    even-sized: 5/5 bit-exact | odd-sized (intentionally re-aligned): 0
Set14   even-sized: 11/11 bit-exact | odd-sized (intentionally re-aligned): 3
BSD100  even-sized: 0/0 bit-exact | odd-sized (intentionally re-aligned): 100
OK: LR protocol reproduces the official LR files exactly wherever they are well-defined
```

### 2.3 Bicubic / nearest baseline
| | |
|---|---|
| Command | `.venv/bin/python software/ai/evaluation/eval_baseline.py` |
| Input | `data/test/HR/<set>/*.png` |
| Output | `data/test/LR/<set>/*` (LR inputs), `results/quality/baseline_x2.md` + `.csv`, pictures `results/images/` |
| Verify | `git diff --exit-code -- results/quality; echo $?` → `0` (= reproduced byte for byte) |

Expected (in `results/quality/baseline_x2.md`), PSNR-Y: bicubic Set5 **33.67**, Set14 **30.32**, BSD100 **29.56** dB;
nearest 30.86 / 28.58 / 28.42 dB.

### 2.4 Unit tests ✅
```bash
.venv/bin/python -W error software/ai/evaluation/test_baseline.py      # 13 lines "PASS ...", exit 0
```
A `SKIP` line means data was missing → that test did NOT run.

---

## 3. Software M2 — the FP32 network

### 3.1 Model tests ✅
```bash
.venv/bin/python -W error software/ai/evaluation/test_model.py         # 9 lines "PASS ...", exit 0
```
Checks: 2,620 parameters, 2,560 MACs/pixel, tiled == whole image, padding, rounding, beats bicubic on real images.

### 3.2 Evaluate the trained network
| | |
|---|---|
| Command | `.venv/bin/python software/ai/evaluation/eval_model.py` |
| Input | `software/ai/checkpoints/srnet_fp32.pt`, `data/test/LR`, `data/test/HR` |
| Output | `results/quality/model_fp32_x2.md` + `.csv`, pictures `results/images/model_fp32_*`, `modelzoom_fp32_*` |
| Verify | `git diff --exit-code -- results/quality; echo $?` → `0` |

Expected PSNR-Y: Set5 **35.21**, Set14 **31.51**, BSD100 **30.60** dB (gain +1.53 / +1.18 / +1.04 over bicubic), 119/119 images better.

### 3.3 Target size + tiling check ✅
```bash
.venv/bin/python software/ai/evaluation/check_target_res.py
```
Input: a validation image (img0373). Expected:
```
img0373.png: whole image (540, 960) -> (1080, 1920) in 0.09s (CPU)
PSNR-Y model 41.31 dB vs bicubic 40.38 dB
tiles 135 | float max diff 6.56e-07 | uint8 values differing 98 of 6220800 (max diff 1)
OK
```
**Why:** proves 960×540 → 1920×1080 works and 135 tiles give the same picture (tiny float differences only; the INT8 model has 0).

Optional: `.venv/bin/python software/ai/evaluation/border_effect.py` → interior +0.98 dB, outer 8 px band +0.83 dB.

### 3.4 Training (optional)
* Smoke test, ~6 s (only proves the loop runs):
  `.venv/bin/python software/ai/training/train.py --epochs 1 --steps 3 --images 192 --val 12 --threads 2 --out /tmp/tiny.pt`
  → prints `train 180 imgs, val 12 imgs; params=2620 MACs/px=2560` and one epoch line.
* Full retrain, ~33 min:
  `.venv/bin/python software/ai/training/train.py --epochs 100 --steps 500 --images 192 --val 12 --threads 4 --out /tmp/srnet_retrain.pt`
  then `.venv/bin/python software/ai/evaluation/eval_model.py --ckpt /tmp/srnet_retrain.pt --tag retrain`.
  Expect within ±0.1 dB of 3.2 (training is not bit-exact).
* ⚠️ **Never** write to `software/ai/checkpoints/srnet_fp32.pt`: the INT8 weights, the RTL and all golden files depend on it.
* Training log already present: `software/ai/checkpoints/srnet_fp32.log.json`, curve `results/quality/training_curves.png`.

---

## 4. Software M3 — INT8, the golden model, exports for the hardware

### 4.1 Tests ✅
```bash
.venv/bin/python -W error software/ai/quantization/test_integer.py     # 21 PASS
.venv/bin/python -W error software/ai/quantization/test_export.py      # 7 PASS
python3 software/ai/quantization/check_export_independent.py           # ... ALL OK: 11 tiles, time 12 s
```
The last one is the strongest: plain Python (no NumPy, no project code) recomputes every golden tile **only from the exported
`.mem` files** and must get the same bytes.

### 4.2 Quantize (FP32 → integer parameters)
| | |
|---|---|
| Command | `.venv/bin/python software/ai/quantization/quantize.py --out /tmp/q_check.npz` |
| Input | `software/ai/checkpoints/srnet_fp32.pt`, 100 training crops (calibration) |
| Output | `/tmp/q_check.npz` (the real one is `software/ai/quantization/qparams.npz`; without `--out` it overwrites that file, which is fine only if identical) |
| Verify | `.venv/bin/python -c "import numpy as np;a=np.load('software/ai/quantization/qparams.npz');b=np.load('/tmp/q_check.npz');print('identical:',all((a[k]==b[k]).all() for k in a.files))"` → `identical: True` |

Inside `qparams.npz`: per layer `L*_w` (int8 weights), `L*_b` (int32 bias), `L*_m` (multiplier), `L*_shift`:
L1 M=62,656 shift 24 · L2 M=40,008 shift 23 · L3 M=42,362 shift 21 · L4 M=43,607 shift 24.

### 4.3 INT8 quality (~5 min)
| | |
|---|---|
| Command | `.venv/bin/python software/ai/evaluation/eval_int8.py` |
| Input | `qparams.npz`, `data/test/LR`, `data/test/HR` |
| Output | `results/quality/model_int8_x2.md` + `.csv`, pictures `results/images/model_int8_*` |
| Verify | `git diff --exit-code -- results/quality; echo $?` → `0` |

Expected PSNR-Y: Set5 **35.02**, Set14 **31.40**, BSD100 **30.53** dB (drop vs FP32 0.18 / 0.11 / 0.08 dB). Optional `--sweep`
(~4 min) reproduces `results/quality/m3_ptq_sweep.md` (99.99 % per-layer is best, −0.22 dB).

### 4.4 Export to the hardware + golden vectors — WHERE THE GOLDEN DATA IS
```bash
.venv/bin/python software/ai/quantization/export_rtl.py
.venv/bin/python software/ai/quantization/gen_unit_vectors.py
git status --short hardware/rtl/weights          # must print NOTHING (exported weights unchanged)
```
| Output | Location | What is inside |
|---|---|---|
| Network for Verilog | `hardware/rtl/weights/` | `wrom_L1..4.mem` (weights in ROM order, read by `weight_rom.v`), `bias_L*.mem`, `mult_L*.mem`, `weights_L*.mem` (plain `[co][ci][ky][kx]`), `network_params.vh` (shifts), `README.md` (formats) |
| **Golden tiles** | `data/golden/<tile>_in.hex`, `_L1.hex`, `_L2.hex`, `_L3.hex`, `_L4.hex`, `_out.hex`, `<tile>.npz` | input tile and the **expected output of every layer**, one byte per line, order `[y][x][c]`. Tiles: `zeros, full255, noise, pixel, ramp, real0, real1, real2, real_corner` (70×70 → 128×128) and `small12`, `small12b` (small, for fast tests) |
| Unit vectors | `data/golden/unit/` | requantizer test vectors (shifts 1, 2, 3, 8, 21, 23, 24), randomized layers `randL1..4` |
| Seam test | `data/golden/seam/` | tiles cut from an image + their RTL outputs (made by `run_tests.sh`) |

Sizes of one real golden tile: in 70×70×3 = 14,700 lines, L1 68×68×16, L2 66×66×16, L3 66×66×16, L4 64×64×12, out 128×128×3 = 49,152 lines.
The `real*` tiles need `data/train/HR` to exist. Who made them: `integer_reference.py` (the golden model) — the RTL must match them **bit for bit**.

---

## 5. Hardware in simulation (no board needed)

### 5.1 Quick RTL regression ✅ (~3 min)
| | |
|---|---|
| Command | `hardware/verification/run_tests.sh quick ; echo "exit=$?"` |
| Input | `hardware/rtl/**/*.v`, `hardware/rtl/weights/*.mem`, `data/golden/*.hex`, `data/golden/unit/*` |
| Output | text (temporary files only; `data/golden/seam/` is rewritten) |
| Tool | Icarus Verilog (`iverilog`, `vvp`) |

What runs: requantizer (7 shifts), MAC, RAMs, weight ROMs, each conv layer on golden tiles + randomized layers, the whole tile core,
the AXI-Stream wrapper, the AXI top module (driven like the ARM + DMA), the register header check, the host tools, the C tiling code,
and a 20-tile seam test.

Expected last line: **`== summary: 36 test runs passed, 0 failed (quick)`** and `exit=0`. Typical lines:
```
PASS requant SHIFT=24: 12981 vectors bit-exact
PASS layer 1 tile small12: 100 pixels (10x10) x 16 ch bit-exact, 2724 cycles (27 per pixel, PERIOD 27), re-run + abort/recover OK
PASS sr_tile_core HC=6 tile small12: 432 output bytes bit-exact, layer buffers exact, 10961 cycles, re-run + 2nd tile + abort sweep OK
PASS sr_accel_top HC=6 tile small12: 108 output beats bit-exact via AXI-Lite + AXI-Stream, CYCLES=10962, ...
PASS test_regs: sr_regs.h == sr_accel_top.v == REGISTER_MAP.md (29 constants, 13 registers, HC=64)
[seam hc=8] 20 tiles simulated, 0 failed
PASS seam hc=8: 20 RTL tiles assembled == whole-image integer model, 74x58 pixels bit-exact
```
Any `FAIL` line or exit ≠ 0 = failure.

### 5.2 Full RTL regression (~20–25 min)
```bash
hardware/verification/run_tests.sh full
```
Expected: **`== summary: 88 test runs passed, 0 failed (full)`**. Adds: all layers on all 9 real tiles, the whole core at real size
(70×70 → 128×128) with and without stalls, real-size seam test (4 tiles), the 960×540 C tiling test, ARM compile check, wrapper and top at
real size, START-timing sweep. Cycle numbers (same for every tile):
L1 124,872 · L2 69,713 · L3 69,720 · L4 589,844 · whole core **926,201** · top module **926,202**.

### 5.3 Run one testbench by hand (to see it is real)
```bash
RTL="hardware/rtl/common/mac_unit.v hardware/rtl/common/requant.v hardware/rtl/common/weight_rom.v hardware/rtl/common/tile_ram_split.v hardware/rtl/conv_engine/conv_engine.v hardware/rtl/sr_core/sr_tile_core.v"
iverilog -g2012 -Wall -I . -o /tmp/core6.vvp -P tb_sr_tile.HC=6 $RTL hardware/verification/tb/tb_sr_tile.v
vvp /tmp/core6.vvp +TILE=small12 +TILE2=small12b
```
Expected: `PASS sr_tile_core HC=6 tile small12: 432 output bytes bit-exact, layer buffers exact, 10961 cycles, ...`
Real size (≈50 s): build with `-P tb_sr_tile.HC=64`, run `vvp /tmp/core64.vvp +TILE=real0` → 49,152 bytes bit-exact, 926,201 cycles.
Options: `+STALL=1` random stream pauses, `+TILE=<name>` any tile in `data/golden`, `+NOEXTRA` single run.

| Testbench (`hardware/verification/tb/`) | Tests module |
|---|---|
| `tb_requant.v`, `tb_mac_unit.v`, `tb_tile_ram.v`, `tb_tile_ram_split.v`, `tb_weight_rom.v` | the small building blocks |
| `tb_conv_layer.v` | `conv_engine.v`, one layer |
| `tb_sr_tile.v` | `sr_tile_core.v`, whole network |
| `tb_sr_axis.v` | `sr_axis_wrapper.v` |
| `tb_sr_accel_top.v` | `sr_accel_top.v` (AXI-Lite + AXI-Stream, like the ARM/DMA) |

### 5.4 Waveform demo (~3 min, or 1 s with `--wave`)
```bash
hardware/verification/demo_sim.sh            # quick regression + one HC=6 tile with a VCD waveform
hardware/verification/demo_sim.sh --wave     # waveform only
```
Expected: `36 test runs passed, 0 failed` then `PASS ... 108 output beats bit-exact ... CYCLES=10962`. Opens GTKWave with
`hardware/verification/demo_sim.gtkw` (install first: `sudo apt install gtkwave`). State row: 0 IDLE, 1 LOAD (433 cycles), 2 L1 (2,726),
3 L2 (1,043), 4 L3 (1,050), 5 L4 (5,206), 6 OUT (504).

### 5.5 In Vivado (second simulator, synthesis, timing) — needs `source …/Vivado/2024.1/settings64.sh`
| Command | What | Expected | Output folder |
|---|---|---|---|
| `hardware/verification/run_postsynth.sh` | simulate the **synthesized netlists** (4 layers + tile core) with xsim | `== post-synthesis summary: 5 passed, 0 failed` | `hardware/vivado/build/` |
| `vivado -mode batch -nojournal -log hardware/vivado/build/my_L3.log -source hardware/vivado/scripts/synth_conv_engine.tcl -tclargs 3 10.0 impl` | synth + place & route of layer 3 at 100 MHz | WNS +2.913 ns, 369 LUT, 841 FF, 18 DSP | `hardware/vivado/build/conv_L3_impl/` |
| `vivado -mode batch -nojournal -log hardware/vivado/build/my_core.log -source hardware/vivado/scripts/synth_sr_tile_core.tcl -tclargs 10.0 impl` | whole core (~3 min) | WNS +0.723 ns, 1,896 LUT, 3,341 FF, **68 DSP**, **70 BRAM** | `hardware/vivado/build/sr_tile_core_impl/` |
| `vivado -mode batch -nojournal -source hardware/vivado/scripts/synth_sr_accel_top.tcl` | top module (core + AXI) | ~1,988 LUT, 68 DSP, 70 BRAM, WNS positive | `hardware/vivado/build/` |

Read the reports:
```bash
grep -A3 "WNS(ns)" hardware/vivado/build/sr_tile_core_impl/timing_routed.txt | sed -n 3p
grep -E "^\| (Slice LUTs|Slice Registers|DSPs|Block RAM Tile)" hardware/vivado/build/sr_tile_core_impl/utilization_routed.txt
grep -c "Synth 8-311" hardware/vivado/build/my_core.log      # must be 0 (no ignored ROM init)
```
Committed reference reports to compare with: `results/utilization/m4_*`, `m5_*`, `m6_top*`.
Open the design in the GUI: `vivado hardware/vivado/build/sr_tile_core_impl/routed.dcp &` → Reports → Timing Summary / Utilization.
GUI-project testbenches: `docs/VERIFY_YOURSELF.md` section 4.5b (`run_tb core` etc.).

---

## 6. Hardware on the ZedBoard

### 6.0 What you need
* ZedBoard, 12 V power, micro-USB in **PROG/JTAG (J17)**, boot jumpers on JTAG. UART not needed.
* **Close Vitis and the Vivado Hardware Manager** (they hold the JTAG cable).
* Terminal: `source ~/Desktop/vivado_install/Vitis/2024.1/settings64.sh` (gives `xsdb`).
* Bitstream (already built): `~/Desktop/venkat/vitis/m6_sr_0602/m6_sr.runs/impl_1/design_1_wrapper.bit` (VERSION 0x53520602). `run_board.tcl` uses it by default; another one via `SR_BIT=<path>`.
* ARM programs (already built): `software/board/build/sr_app_t1.elf` (T1), `sr_app_t2.elf` (T2), `sr_app_t3.elf` (T3, 5 frames), `sr_app_t3_20f.elf` (20 frames), `sr_app_t5.elf` (error recovery), `sr_app_t10.elf` (T6 stress). Rebuild: Part 7.2.

### 6.1 How a board run works (`software/board/run_board.tcl`)
```
xsdb software/board/run_board.tcl  <program.elf>  <input.raw | ->  <output.raw | ->  [stats.txt]
```
1. Programs the FPGA safely (PL held in reset, PS–PL level shifters off while programming), initialises the ARM side.
2. Loads the ELF (twice, L2 cache off — a measured workaround for stale cache lines).
3. Copies the input image into DDR at 0x1000_0000 (format SRIM: 16-byte header + RGB bytes).
4. Runs the program; waits for a "ready" marker at 0x1300_0000.
5. Copies the output image back from 0x1200_0000 into `<output.raw>`; writes numbers (`result`, `version`, `stat0…`) into `stats.txt`.

The image file format (`.raw` = SRIM) is defined in `software/host_tools/srim.py`; convert with `png2raw.py` / `raw2png.py`.

### 6.2 One-command demo (~25–30 s)
```bash
software/board/demo.sh             # 0602 bitstream;  --0601 = fallback;  --no-view = no picture window
```
| Input | Output |
|---|---|
| `data/board/div2k_img0193_lr_960x540.raw`, expected `data/board/div2k_img0193_expected_1920x1080.raw`, ELFs t1 + t2 | log `data/board/demo/demo_<time>.log`, `fpga_1920x1080_<time>.png`, `side_by_side_<time>.png` |

Expected screen (2026-10-12 rehearsal):
```
[1/5] board on JTAG ... OK
[2/5] ... OK  FPGA programmed, VERSION 0x53520602
[3/5] PASS  golden tile bit-exact, 20/20 repeats identical; CYCLES 926220, tile time 9.52 ms
[4/5] PASS  frame BYTE-EXACT vs the integer model (6,220,800 bytes), checksum 0xcf947f22, frame time 1311.4 ms (= 0.76 fps)
[5/5] OK ... side_by_side_<time>.png
PASS: DEMO COMPLETE in ~25 s
```
Explanation of each line and what to say: `docs/DEMO.md`.

### 6.3 The same steps by hand

**T1 – one golden tile**
```bash
xsdb software/board/run_board.tcl software/board/build/sr_app_t1.elf - - /tmp/t1.txt
cat /tmp/t1.txt
```
Input: the golden tile `real0` compiled into the program (`software/board/sr_app/golden_tile.h`, made by `software/host_tools/golden_tile_h.py` from `data/golden/real0_*`).
Expect: `result=0`, `version=0x53520602`, `stat6=20` (20/20 repeats identical), `stat0/stat1` (CYCLES min/max) ≈ 926,217–926,241, `stat5` tile time ≈ 9,521 µs.

**T2 – a whole image, byte-exact check**
```bash
# 1. make the board inputs (once): data/board/*.png + .raw
.venv/bin/python software/host_tools/make_test_images.py
# 2. expected output from the integer (golden) model
.venv/bin/python software/host_tools/expected_output.py data/board/div2k_img0193_lr_960x540.raw data/board/div2k_img0193_expected_1920x1080
# 3. run on the board
xsdb software/board/run_board.tcl software/board/build/sr_app_t2.elf data/board/div2k_img0193_lr_960x540.raw /tmp/out.raw /tmp/t2.txt
# 4. compare byte by byte
.venv/bin/python software/host_tools/compare_raw.py /tmp/out.raw data/board/div2k_img0193_expected_1920x1080.raw
```
Expect:
```
board   : /tmp/out.raw  1920x1080  fnv1a32 0xcf947f22
expected: data/board/div2k_img0193_expected_1920x1080.raw  1920x1080  fnv1a32 0xcf947f22
BYTE-EXACT: yes (6220800 bytes identical)
```
`t2.txt`: `stat0` total ≈ 1,311,xxx µs, `stat1` pad ≈ 5,900, `stat2` ARM copy ≈ 26,400, `stat3` DMA+compute ≈ 1,279,xxx.
Smaller first test: `data/board/set14_baboon_lr_128x128.raw` (4 tiles, fnv 0x91a4506d, ~38.7 ms).
To see the picture: `.venv/bin/python software/host_tools/raw2png.py /tmp/out.raw /tmp/out.png`.
(Note: img0193 is a **training** image — use it for speed and bit-exactness only, never for quality.)

**T3 – timing**
```bash
xsdb software/board/run_board.tcl software/board/build/sr_app_t3_20f.elf data/board/div2k_img0193_lr_960x540.raw /tmp/t3.raw /tmp/t3.txt
```
Expect in `t3.txt`: `stat0=20` frames, `stat1` mean ≈ 1,311,900 µs (min ≈ 1,311,400, max ≈ 1,313,200), `stat4` pad ≈ 5,900, `stat5` ARM copy ≈ 26,400,
`stat6` DMA+compute ≈ 1,279,600, `stat9..11` CYCLES ≈ 926,217 / 926,241 / 926,220. Record: `results/speed/m7_timing_20frames.md`.

**T5 – error recovery, T6 – stress** (`sr_app_t5.elf`, `sr_app_t10.elf`, inputs `- -`): T5 every case `next tile byte-exact = 1`;
T6 1000/1000 tiles for both driver orders. Records: `results/utilization/m6_system_0602.md`. Meaning of every `stat` word: `software/board/README.md` → "Stats block".

### 6.4 All 119 test images on the board (table A FPGA row, ~11 min)
```bash
.venv/bin/python software/host_tools/board_testsets.py prep    # makes data/board/testsets/<set>/<name>_lr.raw and <name>_exp.raw
software/board/run_testsets.sh                                 # runs each image on the board -> <name>_board.raw
.venv/bin/python software/ai/evaluation/run_all.py             # rebuilds results/quality/table_a_x2.{md,csv} incl. the FPGA row
```
Expected: `run_testsets: 119 byte-exact, 0 failed of 119`, and in table A the FPGA row equals the INT8 row. Last record:
`results/quality/m7_board_testsets_run.log`.

**Verify the saved board outputs without the board** ✅ (the files from 2026-10-12 are still in `data/board/`):
```bash
.venv/bin/python software/host_tools/compare_raw.py data/board/div2k_img0193_board_run1.raw data/board/div2k_img0193_expected_1920x1080.raw
#  -> BYTE-EXACT: yes (6220800 bytes identical)
.venv/bin/python software/host_tools/compare_raw.py data/board/testsets/Set5/baby_board.raw data/board/testsets/Set5/baby_exp.raw
#  -> BYTE-EXACT: yes (786432 bytes identical)
.venv/bin/python software/ai/evaluation/run_all.py ; git status --short results/quality      # nothing changed = table A reproduced exactly
```

---

## 7. Rebuilding the bitstream and the ARM program (optional, long)

### 7.1 Bitstream from the repo (~7 min, use 2 jobs — 8 froze this PC)
```bash
source ~/Desktop/vivado_install/Vivado/2024.1/settings64.sh
vivado -mode batch -nojournal -log ../m6_build.log -source hardware/vivado/scripts/build_m6_system.tcl -tclargs $PWD/../m6_build 2
```
Input: `hardware/vivado/bd/design_1_m6.tcl` (block design), all RTL, `hardware/rtl/weights/*.mem`, `hardware/vivado/ip_repo/` (M0 adder IP).
Output: `../m6_build/m6_sr.runs/impl_1/design_1_wrapper.bit`, `../m6_build/design_1_wrapper.xsa`.
Expect: `WNS 0.503  WHS 0.016` and `BUILD_OK`; the log says 12 × `.../hardware/rtl/weights/... is read successfully`.

### 7.2 ARM programs
```bash
source ~/Desktop/vivado_install/Vitis/2024.1/settings64.sh
.venv/bin/python software/host_tools/golden_tile_h.py          # -> software/board/sr_app/golden_tile.h (for T1)
for n in 1 2 3; do software/board/build_elf.sh $n; done        # -> software/board/build/sr_app_t1.elf, t2, t3
software/board/build_elf.sh 3 -DSR_T3_FRAMES=20                 # 20-frame timing build
```
On this PC `build_elf.sh` uses the existing BSP. With a new XSA (7.1) first make a platform:
`vitis -s software/board/create_platform.py $PWD/../m6_build/design_1_wrapper.xsa $PWD/../m6_ws` (→ `PLATFORM_OK`), then
`export SR_BSP=$PWD/../m6_ws/m6_platform/export/m6_platform/sw/standalone_ps7_cortexa9_0 SR_LSCRIPT=$PWD/software/board/sr_app/lscript.ld`,
and run the board with `export SR_BIT=$PWD/../m6_build/m6_sr.runs/impl_1/design_1_wrapper.bit`.
Full from-scratch record: `results/utilization/m7_clean_clone_build.md`.

### 7.3 Power estimate (Vivado, read-only)
`hardware/vivado/scripts/power_estimate_m6.tcl` on the routed checkpoint → reports like `results/utilization/m7_power_0602_toggle*.txt`.
Expected total 1.913 W (estimate, confidence Low).

---

## 8. Tables A–D: where the final numbers live

| Table | Number | File | Made by | Re-check |
|---|---|---|---|---|
| A quality | FPGA = INT8: PSNR-Y 35.02 / 31.40 / 30.53 dB | `results/quality/table_a_x2.md/.csv` | `run_all.py` (+ board outputs) | 6.4 last block |
| B speed | 1,311.9 ms/frame, 0.762 fps | `results/speed/m7_timing_20frames.md` (+ `m7_t3_20frames_stats.txt`) | board T3 | 6.3 T3 |
| C resources | 5,296 LUT, 7,831 FF, 72 BRAM, 68 DSP, WNS +0.503 ns | `results/utilization/m6_system_0602.md` (+ `_utilization.txt`, `_timing_summary.txt`) | Vivado build | 7.1 |
| D power | 1.913 W total, 0.176 W accelerator (**estimate**) | `results/utilization/m7_power.md` | `power_estimate_m6.tcl` | 7.3 |
| Board history | first runs, failures, investigation | `results/speed/m6_board.md` | board | — |
| Earlier levels | per-layer and core resources/timing | `results/utilization/m4_conv_engine.md`, `m5_tile_core.md`, `m6_top.md` | Vivado OOC | 5.5 |

---

## 9. Quick checklist — no board, ~10 minutes (all ✅ on 2026-10-13)

```bash
cd ~/Desktop/venkat/sem_project_all
P=.venv/bin/python
sha256sum software/ai/checkpoints/srnet_fp32.pt | cut -c1-16        # f1ae81f706ad3707
$P -m pyflakes $(git ls-files 'software/*.py'); echo "lint exit=$?" # lint exit=0
$P software/ai/dataset/check_dataset.py                             # OK: all files decode, no duplicates, no train/test overlap ...
$P software/ai/dataset/check_lr_protocol.py                         # OK: LR protocol reproduces the official LR files ...
$P -W error software/ai/evaluation/test_baseline.py | grep -c PASS  # 13
$P -W error software/ai/evaluation/test_model.py    | grep -c PASS  # 9
$P -W error software/ai/quantization/test_integer.py | grep -c PASS # 21
$P -W error software/ai/quantization/test_export.py  | grep -c PASS # 7
python3 software/ai/quantization/check_export_independent.py | tail -1   # ALL OK: 11 tiles
$P software/ai/evaluation/check_target_res.py | tail -1             # OK
$P software/host_tools/compare_raw.py data/board/div2k_img0193_board_run1.raw data/board/div2k_img0193_expected_1920x1080.raw | tail -1   # BYTE-EXACT: yes
$P software/ai/evaluation/run_all.py > /dev/null; git status --short results   # (nothing) = table A reproduced
hardware/verification/run_tests.sh quick | tail -1                 # == summary: 36 test runs passed, 0 failed (quick)
git status --short                                                  # only your own new files
```

---

## 10. Traps — read before you run

1. **`run_all.py --no-fpga` rewrites `results/quality/table_a_x2.*` WITHOUT the FPGA row.** If you run it, restore with
   `git checkout -- results/quality/table_a_x2.md results/quality/table_a_x2.csv` (or run `run_all.py` without the flag, which needs
   `data/board/testsets/*_board.raw`).
2. **Never overwrite `software/ai/checkpoints/srnet_fp32.pt`** (use `--out /tmp/...` when training).
3. If `data/golden` is missing, `run_tests.sh` regenerates it (and the weight files) automatically — check `git status` afterwards.
4. **Never put symlinks to `hardware/` or `data/` in a Vivado project folder**: `create_project -force` follows them and deletes the real folders.
5. Vivado builds: use **2 jobs**; 8 froze this 15 GB PC.
6. Do not run board tests while Vivado is building or while Vitis holds the JTAG cable.
7. Always `source settings64.sh` in the terminal before `vivado`, `xsdb`, `vitis`.
8. The DIV2K board image (img0193) is a training image: speed and bit-exactness only, no quality claims.
9. Power numbers are **estimates**; say so.
10. `docs/VERIFY_YOURSELF.md` was written before the board work: its counts (29 / 73 runs) and "nothing on the board" are out of date;
    this guide has the current numbers (36 / 88 runs).

---

## 11. Troubleshooting

| Symptom | Fix |
|---|---|
| `vivado` / `xsdb` / `vitis: command not found` | `source ~/Desktop/vivado_install/{Vivado,Vitis}/2024.1/settings64.sh` |
| `ModuleNotFoundError` | use `.venv/bin/python`, not `python` |
| `SKIP` in Python tests | dataset missing in `data/` → not verified; see `data/README.md` |
| RTL `FAIL: ... undefined bytes in data/golden/...` | regenerate: `export_rtl.py` then `gen_unit_vectors.py` (needs `data/train/HR` for `real*`) |
| xsdb: no targets / `AHB AP transaction error` | `xsdb software/board/dap_reset.tcl`, then retry; else power-cycle (SW8 off 10 s) |
| `FAIL board does not answer on JTAG` | power LED on? cable in J17 (not J14)? close Vitis/Hardware Manager; `pkill hw_server`; replug |
| VERSION not 0x53520602 | wrong bitstream; check the `.bit` path or use `SR_BIT=...` / `demo.sh --0601` |
| Board output NOT byte-exact | run again; then `dap_reset.tcl` + power-cycle; record it — it would be a real finding |
| Vivado `$readmem ... cannot open` | weights path (`WDIR`) must be absolute in a GUI project |
| WNS differs by ±0.1 ns | normal placement noise; DSP/BRAM counts must still match |
