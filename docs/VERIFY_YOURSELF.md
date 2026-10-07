# Verify everything yourself — step-by-step guide (software in VS Code, RTL with Vivado)

This guide lets you re-check **every claim of the project on your own machine**, in order, without trusting me. For each step you get:
**what to run → what you should see → what it proves → what it does NOT prove → what to do if it differs.**

Legend: ✅ = I ran exactly this command in this project and it printed what is shown. 🖱️ = a Vivado GUI step: the menu names are from Vivado 2024.1,
but I cannot click through a GUI, so these were **not** executed by me (the equivalent Tcl/command-line versions were).

Project folder on this machine: `/home/sreevenkat/Desktop/venkat/sem_project_all` (called **ROOT** below). **Every command is run from ROOT.**

---

## 0. Plan and time budget

| Part | What | Time | Where |
|---|---|---|---|
| 1 | Setup and sanity checks | 10 min | VS Code terminal |
| 2 | Software M1 – M3 (data, baseline, FP32 model, INT8 model) | 25 min (+35 min if you retrain) | VS Code terminal |
| 3 | RTL M4 – M5 in simulation (Icarus Verilog) | 3 min quick / ~25 min full | VS Code terminal |
| 4 | RTL in Vivado: simulation with waveforms, synthesis, place and route, GUI reports | 40 min | Vivado |
| 5 | "Try to break it" exercises (proves the tests can fail) | 20 min | VS Code terminal |
| 6 | Master table of expected numbers, limits, troubleshooting | reference | — |

Suggested order: Part 1 → 2 → 3 → 4 → 5. Do not skip Part 5: a test that cannot fail proves nothing.

---

## 1. Setup

### 1.1 Open the project in VS Code
1. VS Code → **File → Open Folder…** → choose ROOT.
2. Open a terminal: **Terminal → New Terminal**. It starts in ROOT. Check with `pwd`.
3. Choose the Python interpreter: `Ctrl+Shift+P` → **Python: Select Interpreter** → pick `ROOT/.venv/bin/python`. (The commands below call `.venv/bin/python` explicitly, so this is only for the editor.)

### 1.2 Check the tools ✅
```bash
.venv/bin/python --version          # Python 3.12.3
iverilog -V | head -1               # Icarus Verilog version 12.0 (stable)
source ~/Desktop/vivado_install/Vivado/2024.1/settings64.sh
vivado -version | head -1           # Vivado v2024.1 ...
git status -sb | head -3            # branch main, ideally "## main...origin/main" and no modified files
git log --oneline | head -3         # newest commit message: "Updated project log for M5 and the re-audit" (or newer)
```
If a command is not found, see Part 6.3. You must `source …/settings64.sh` in **every new terminal** before using `vivado`, `xvlog`, `xelab`, `xsim`.

### 1.3 Check the data is present ✅
```bash
ls data/train/HR | wc -l            # 192
ls data/test/HR                     # BSD100  Set14  Set5
ls data/golden | head -3            # full255_in.hex  full255_L1.hex  full255_L2.hex ...   (golden test vectors, git-ignored but present)
```
If `data/golden` is empty, run `.venv/bin/python software/ai/quantization/export_rtl.py` (Part 2.7). On a **different** computer you also need the datasets:
see `data/README.md` and run `software/ai/scripts/fetch_div2k_subset.sh 192` (needs internet; I did not re-run it).

### 1.4 Check the frozen model file ✅
```bash
sha256sum software/ai/checkpoints/srnet_fp32.pt | cut -c1-16     # f1ae81f706ad3707
```
Everything (INT8 numbers, RTL weights, golden tiles) was derived from exactly this file. If the hash differs, nothing below will match.

---

## 2. Software verification (M1, M2, M3)

All of this is Python in the VS Code terminal. Start with the one-line summary of what each milestone claims, then verify it.

### 2.1 Lint (syntax and obvious mistakes) ✅
```bash
.venv/bin/python -m pyflakes $(git ls-files -c -o --exclude-standard 'software/*.py')
echo "exit=$?"
```
**Expect:** no output, `exit=0`. **Proves:** every Python file compiles and has no unused/undefined names. **Does not prove:** the logic is right (that is what the tests below do).

### 2.2 M1 — dataset and low-resolution protocol ✅
```bash
.venv/bin/python software/ai/dataset/check_dataset.py
.venv/bin/python software/ai/dataset/check_lr_protocol.py
```
**Expect:**
```
train images: 192   test images: 119
train size range: min 816 px short side; max 2040 px long side
OK: all files decode, no duplicates, no train/test overlap, all test LR present
Set5    even-sized: 5/5 bit-exact | odd-sized (intentionally re-aligned): 0
Set14   even-sized: 11/11 bit-exact | odd-sized (intentionally re-aligned): 3
BSD100  even-sized: 0/0 bit-exact | odd-sized (intentionally re-aligned): 100
OK: LR protocol reproduces the official LR files exactly wherever they are well-defined
```
**Proves:** train and test images are different files (by exact hash); our low-res images equal the official benchmark ones wherever that is well defined.
**Does not prove:** there are no *near*-duplicates (resized copies) between train and test; I checked that by eye earlier, the script cannot.

### 2.3 M1 — baseline numbers (bicubic / nearest) ✅
```bash
.venv/bin/python software/ai/evaluation/eval_baseline.py
git diff --exit-code -- results/quality ; echo "diff exit=$?"
```
**Expect:** the script finishes quietly; `diff exit=0` means **it reproduced the committed result files byte for byte**.
Open `results/quality/baseline_x2.md` in VS Code and compare:

| Set | Nearest PSNR-Y | Bicubic PSNR-Y | Bicubic SSIM-Y |
|---|---|---|---|
| Set5 | 30.86 | **33.67** | 0.9303 |
| Set14 | 28.58 | **30.32** | 0.8698 |
| BSD100 | 28.42 | **29.56** | 0.8434 |

Look at the pictures: in VS Code open `results/images/baseline_Set14_zebra.png` and `zoom_Set14_zebra.png` (left → right: nearest | bicubic | ground truth).
Nearest should look blocky, bicubic smooth, neither shifted nor colour-swapped. (These images are generated, git-ignored, and created by the command above.)

### 2.4 M1/M2 unit tests ✅
```bash
.venv/bin/python -W error software/ai/evaluation/test_baseline.py     # 13 lines "PASS ..."
.venv/bin/python -W error software/ai/evaluation/test_model.py        # 9 lines "PASS ..."
```
**Expect:** only `PASS` lines, **no `SKIP`**, exit code 0 (`echo $?`). A `SKIP` means a dataset was missing and that test did not run — treat it as *not verified*.
The tests cover: PSNR/SSIM definitions, colour order (RGB vs BGR), no pixel shift, rounding/clamping of the model output, replicate padding, tiled == whole image, and that the model beats bicubic by > 0.5 dB on real images.

### 2.5 M2 — the FP32 model ✅
```bash
.venv/bin/python software/ai/evaluation/eval_model.py
git diff --exit-code -- results/quality ; echo "diff exit=$?"      # 0 = reproduced exactly
.venv/bin/python software/ai/evaluation/check_target_res.py
.venv/bin/python software/ai/evaluation/border_effect.py
```
**Expect** (`results/quality/model_fp32_x2.md`):

| Set | Bicubic PSNR-Y | FP32 CNN PSNR-Y | Gain | Images better than bicubic |
|---|---|---|---|---|
| Set5 | 33.67 | **35.21** | +1.53 dB | 5 of 5 |
| Set14 | 30.32 | **31.51** | +1.18 dB | 14 of 14 |
| BSD100 | 29.56 | **30.60** | +1.04 dB | 100 of 100 |

`check_target_res.py` prints (timing may differ on your CPU):
```
img0373.png: whole image (540, 960) -> (1080, 1920) in 0.07s (CPU)
PSNR-Y model 41.31 dB vs bicubic 40.38 dB
tiles 135 | float max diff 6.56e-07 | uint8 values differing 98 of 6220800 (max diff 1)
OK
```
That is the **real target size** (960×540 → 1920×1080) and the 135-tile check: the FP32 model gives tiny float differences between tiled and whole (98 of 6.2 million values off by 1) — this is rounding in floating point; the **integer model (Part 2.6) has exactly 0 differences**.
`border_effect.py` prints interior gain +0.98 dB vs outer-8-pixel band +0.83 dB (a known, small border effect).
Open `results/images/modelzoom_fp32_Set14_barbara.png` (bicubic | model | truth): edges and stripes should be sharper in the middle picture; fine random texture is not recovered (expected for 2.6 K parameters).

### 2.6 M2 — training (three levels, choose how much time you have)

**Level 0 — smoke test, 6 seconds ✅** (proves the training loop runs; the numbers are meaningless after 3 steps):
```bash
.venv/bin/python software/ai/training/train.py --epochs 1 --steps 3 --images 192 --val 12 --threads 2 --out /tmp/tiny.pt
```
**Expect:** `train 180 imgs, val 12 imgs; params=2620 MACs/px=2560` and one `ep   1 ...` line, exit 0.

**Level 1 — read the existing training log (no waiting).** `software/ai/checkpoints/srnet_fp32.log.json` has one entry per epoch (100). The validation PSNR-Y (on the 12 held-out training images) rises from ≈ 28.9 dB in epoch 1 to ≈ 34.95 dB at the end (best 34.954); open `results/quality/training_curves.png` to see the curve.

**Level 2 — retrain from scratch, ≈ 30–35 minutes on CPU** (not run again by me; the command and time are from the project log):
```bash
.venv/bin/python software/ai/training/train.py --epochs 100 --steps 500 --images 192 --val 12 --threads 4 \
    --out /tmp/srnet_retrain.pt
```
⚠️ **Use a different `--out` path. Never overwrite `software/ai/checkpoints/srnet_fp32.pt`** — the INT8 weights, the RTL and all golden tiles depend on it.
Then evaluate your retrained model without touching the committed results:
```bash
.venv/bin/python software/ai/evaluation/eval_model.py --ckpt /tmp/srnet_retrain.pt --tag retrain
```
**Expect:** training is *statistically* reproducible, **not bit-exact** (thread count changes float summation order; my own rerun differed by 0.02 dB on validation, seed-to-seed 0.03–0.09 dB).
So your `results/quality/model_retrain_x2.md` PSNR-Y should be within about **±0.1 dB** of the table in 2.5. A gain of +1.0 to +1.5 dB over bicubic and "better than bicubic on all images" should hold. Exactly identical numbers are *not* expected and not required.
(The retrained model does not feed the RTL; re-quantizing it would be a new experiment and would change the golden files.)

### 2.7 M3 — INT8 quantization and the integer golden model ✅
```bash
.venv/bin/python -W error software/ai/quantization/test_integer.py     # 21 PASS
.venv/bin/python -W error software/ai/quantization/test_export.py      # 7 PASS
python3 software/ai/quantization/check_export_independent.py           # ALL OK: 11 tiles
```
The last one is the strongest check: **plain Python (no NumPy, no project code)** reads only the exported `.mem/.vh/.hex` files and recomputes all four layers and the pixel shuffle of every golden tile; it must equal the golden dumps. It prints `OK <tile>` lines and `ALL OK: 11 tiles, time ~12 s`.

Re-create the quantized parameters and check they are **identical** to the committed file:
```bash
.venv/bin/python software/ai/quantization/quantize.py --out /tmp/q_check.npz | head -3
.venv/bin/python -c "
import numpy as np
a=np.load('software/ai/quantization/qparams.npz'); b=np.load('/tmp/q_check.npz')
print('identical:', all((a[k]==b[k]).all() for k in a.files))"          # identical: True
```
Quality of the INT8 model (takes several minutes):
```bash
.venv/bin/python software/ai/evaluation/eval_int8.py
git diff --exit-code -- results/quality ; echo "diff exit=$?"            # 0 = reproduced exactly
```
**Expect** (`results/quality/model_int8_x2.md`, PSNR-Y):

| Set | Bicubic | FP32 | **INT8** | mean drop FP32→INT8 | worst single image |
|---|---|---|---|---|---|
| Set5 | 33.67 | 35.21 | **35.02** | 0.18 dB | 0.31 dB |
| Set14 | 30.32 | 31.51 | **31.40** | 0.11 dB | 0.29 dB |
| BSD100 | 29.56 | 30.60 | **30.53** | 0.08 dB | 0.41 dB |

INT8 still beats bicubic on 119 of 119 images. Optional (about 4 min): `eval_int8.py --sweep` reproduces how the quantization settings were chosen (on the 12 *validation* images only): percentile 99.99 with per-layer weights is the best row (−0.22 dB); 99 % is catastrophic (−5.3 dB). File: `results/quality/m3_ptq_sweep.md`.

Regenerate the RTL files and golden tiles and confirm the tracked ones do not change ✅:
```bash
.venv/bin/python software/ai/quantization/export_rtl.py | head -3
.venv/bin/python software/ai/quantization/gen_unit_vectors.py | tail -2
git status --short hardware/rtl/weights        # must print nothing (the exported weights are unchanged)
```

**What Part 2 proves:** the software chain PyTorch FP32 → NumPy integer model works, gives the stated quality, and the files the hardware uses are exactly derived from it.
**What it does not prove:** that the numbers hold on images outside Set5/Set14/BSD100, or that the network is "good" in an absolute sense (it is 2,620 parameters; fine texture is not recovered).

---

## 3. RTL verification in simulation (M4, M5) — Icarus Verilog, VS Code terminal

### 3.1 What is being tested
| Module (in `hardware/rtl/…`) | Purpose |
|---|---|
| `common/mac_unit.v` | one multiply-accumulate lane (uint8 × int8 → int32) |
| `common/requant.v` | `(acc·M + 2^(SHIFT−1)) >> SHIFT`, clamp 0…255 |
| `common/weight_rom.v`, `tile_ram.v`, `tile_ram_split.v` | weight ROM and activation RAMs |
| `conv_engine/conv_engine.v` | one layer: sequences the MACs, requantizer, RAM addresses |
| `sr_core/sr_tile_core.v` | whole tile: byte-stream in → 4 layers → pixel shuffle → byte-stream out |

The **reference** for every test is the Python integer model (Part 2.7): its outputs were written to `data/golden/*.hex`. The testbenches (`hardware/verification/tb/*.v`) feed the golden input into the RTL and compare **every output byte** with the golden output. A pass means "bit for bit identical", not "close".

### 3.2 The quick regression ✅ (about 2 minutes)
```bash
hardware/verification/run_tests.sh quick
echo "exit=$?"
```
**Expect:** a list of `PASS …` lines in sections *unit tests / conv engine / randomized parameters / tile_ram_split / full tile core / seam* and the last line
```
== summary: 29 test runs passed, 0 failed (quick)
```
and `exit=0`. Any `FAIL` line, or an exit code other than 0, is a failure. Typical lines:
```
PASS requant SHIFT=24: 12981 vectors bit-exact
PASS layer 1 tile small12: 100 pixels (10x10) x 16 ch bit-exact, 2723 cycles (27 per pixel, PERIOD 27), re-run + abort/recover OK
PASS sr_tile_core HC=6 tile small12: 432 output bytes bit-exact, layer buffers exact, 10957 cycles, re-run + 2nd tile + abort sweep OK
[seam hc=8] 20 tiles simulated, 0 failed
PASS seam hc=8: 20 RTL tiles assembled == whole-image integer model, 74x58 pixels bit-exact
```

### 3.3 The full regression ✅ (about 20–25 minutes — start it and do something else)
```bash
hardware/verification/run_tests.sh full
```
**Expect:** `== summary: 73 test runs passed, 0 failed (full)`. In addition to quick it runs all four layers on all 9 real-size tiles, the whole core at the real size (70×70 → 128×128, including two runs with random stalls) and the real-size seam test (4 tiles → 200×180 pixels).
Cycle numbers you should see, **identical for every tile** (they do not depend on the data):

| Item | Cycles |
|---|---|
| Layer 1 / 2 / 3 / 4, one 64×64 tile | 124,871 / 69,712 / 69,719 / 589,843 |
| Whole core, one tile, no stalls | **926,197** |

### 3.4 Run ONE test by hand and read the output ✅ (so you see it is real)
```bash
RTL="hardware/rtl/common/mac_unit.v hardware/rtl/common/requant.v hardware/rtl/common/weight_rom.v hardware/rtl/common/tile_ram_split.v hardware/rtl/conv_engine/conv_engine.v hardware/rtl/sr_core/sr_tile_core.v"
iverilog -g2012 -Wall -I . -o /tmp/core6.vvp -P tb_sr_tile.HC=6 $RTL hardware/verification/tb/tb_sr_tile.v
vvp /tmp/core6.vvp +TILE=small12 +TILE2=small12b
```
**Expect:** exactly one result line:
`PASS sr_tile_core HC=6 tile small12: 432 output bytes bit-exact, layer buffers exact, 10957 cycles, re-run + 2nd tile + abort sweep OK`
(`-Wall` prints only a harmless "timescale" note.) Useful options of the testbench: `+STALL=1` (random pauses on both streams), `+TILE=<name>` (any tile in `data/golden`), `+NOEXTRA` (single run).
HC=6 is a *small* tile (for speed); the real size is HC=64: `iverilog … -P tb_sr_tile.HC=64 …` then `vvp … +TILE=real0` (about 50 s).

### 3.5 What the simulation tests prove and do not prove
**Prove:** the RTL computes exactly the integer model, for the golden tiles, for randomized weights (different multiplier per channel), non-square tiles, with stalls on the streams, after re-runs and after one-cycle resets at 60 different moments; and a whole image cut into tiles gives the same result as the whole image (seam test).
**Do not prove:** behaviour on a board (clocks, DMA, ARM, real AXI), or timing of the full system. There is no AXI/DMA wrapper yet.

---

## 4. RTL in Vivado (all steps below start in a terminal with `source …/settings64.sh` done)

Why scripts and not a hand-made Vivado project? The RTL has **file-path parameters** (`WDIR`, the `.mem` files) and the testbenches read `data/golden/…` with **relative paths from ROOT**. A normal Vivado project simulates in its own sub-folder, so those relative paths break. The scripts below always run from ROOT. You can still **look at everything in the GUI** (4.3 and 4.4).

### 4.1 Simulate the RTL with Vivado's own simulator (xsim) ✅
This is a second, independent simulator (Icarus was the first). Vivado's xsim is stricter: it needs `-timescale`.
```bash
source ~/Desktop/vivado_install/Vivado/2024.1/settings64.sh
W=hardware/vivado/build/xsim_core_demo ; rm -rf $W ; mkdir -p $W ; R=../../../rtl
( cd $W && xvlog -sv -i ../../../.. $R/common/mac_unit.v $R/common/requant.v $R/common/weight_rom.v \
      $R/common/tile_ram_split.v $R/conv_engine/conv_engine.v $R/sr_core/sr_tile_core.v ../../../verification/tb/tb_sr_tile.v \
  && xelab -timescale 1ns/1ps -generic_top HC=6 tb_sr_tile -s sim )
xsim sim -R --xsimdir $W/xsim.dir -testplusarg TILE=small12 -testplusarg NOEXTRA
rm -f clockInfo.txt xsim.jou xsim_*.backup.jou        # xsim leaves these in ROOT; they are git-ignored anyway
```
**Expect (about 3 seconds):** `PASS sr_tile_core HC=6 tile small12: 432 output bytes bit-exact, layer buffers exact, 10957 cycles`.
The `xvlog/xelab` part runs inside `$W` (so its files land there), but `xsim` is started **from ROOT** so the testbench can find `data/golden/…`.

🖱️ **Waveforms (not clicked by me):** replace the last `xsim` line by
`xsim sim --xsimdir $W/xsim.dir -testplusarg TILE=small12 -testplusarg NOEXTRA -gui`.
In the GUI: *Scope* window → expand `tb_sr_tile` → `dut`; drag signals (`state`, `in_valid`, `in_ready`, `out_valid`, `out_data`, `e1.step`, `e1.running` …) into the *Wave* window; in the Tcl console at the bottom type `run all`.
What to look at: `dut.state` steps 1 (load) → 2,3,4,5 (layers 1–4) → 6 (output) → 0; `in_ready` is high only in state 1; `out_valid` only in state 6; `out_last` pulses once, on the last output byte.

### 4.2 Simulate the SYNTHESIZED hardware (post-synthesis netlist) ✅ (about 2.5 minutes)
```bash
hardware/verification/run_postsynth.sh
```
**Expect:** four `[post-synthesis L1…L4] PASS …` lines, one `[post-synthesis tile core HC=6] PASS … bit-exact (netlist: internal buffers not visible, not checked), 10957 cycles …` line, and
`== post-synthesis summary: 5 passed, 0 failed`.
This is the check that catches "works in simulation but Vivado built something different" (it once did: a ROM that RTL simulation accepted but Vivado ignored). The cycle counts must equal the RTL simulation's (2723 / 1040 / 1047 / 5203 / 10957).

### 4.3 Synthesis and place-and-route with reports ✅
One layer (about 1 minute) and the whole core (about 3 minutes). `impl` = synthesis **and** place and route.
```bash
source ~/Desktop/vivado_install/Vivado/2024.1/settings64.sh
vivado -mode batch -nojournal -log hardware/vivado/build/my_L3.log \
       -source hardware/vivado/scripts/synth_conv_engine.tcl -tclargs 3 10.0 impl
vivado -mode batch -nojournal -log hardware/vivado/build/my_core.log \
       -source hardware/vivado/scripts/synth_sr_tile_core.tcl -tclargs 10.0 impl
```
`10.0` is the clock period in ns (100 MHz). Results land in `hardware/vivado/build/conv_L3_impl/` and `…/sr_tile_core_impl/` (git-ignored). Compare with the committed reports in `results/utilization/`:
```bash
grep -A3 "WNS(ns)" hardware/vivado/build/sr_tile_core_impl/timing_routed.txt | sed -n 3p
grep -E "^\| (Slice LUTs|Slice Registers|DSPs|Block RAM Tile)" hardware/vivado/build/sr_tile_core_impl/utilization_routed.txt
grep -c "^ERROR" hardware/vivado/build/my_core.log        # 0
grep -c "Synth 8-311" hardware/vivado/build/my_core.log   # 0  (0 = no "ignored initial block" problem)
grep -c "Synth 8-327" hardware/vivado/build/my_core.log   # 0  (0 = no inferred latches)
```
**Expect for the whole core:** `0.234  0.000  …  0.081` (WNS 0.234 ns, TNS 0, hold slack 0.081 ns, 0 failing endpoints), LUT 1,900, registers 3,337, **DSPs 68**, **Block RAM Tile 70**.
Per layer (routed): L1 360 LUT / 850 FF / 18 DSP / 2 BRAM, WNS +0.135 ns · L2 397 / 952 / 18 / 0, +0.261 · L3 361 / 840 / 18 / 0, +0.582 · L4 347 / 692 / 14 / 1.5, +0.698.
Vivado is deterministic for identical inputs: my reruns reproduced these numbers exactly. **WNS > 0 means the 100 MHz clock is met**; it is small for L1 (0.135 ns) and for the core, so the margin is thin.

### 4.4 🖱️ Look at the design in the Vivado GUI (checkpoints; steps not clicked by me, files are ✅)
The scripts save the finished design as checkpoints (`post_synth.dcp`, `routed.dcp`). Open one:
```bash
source ~/Desktop/vivado_install/Vivado/2024.1/settings64.sh
vivado hardware/vivado/build/sr_tile_core_impl/routed.dcp &
```
In the GUI (Vivado 2024.1 menus):
1. **Reports → Timing → Report Timing Summary…** → OK. *Design Timing Summary* must show Worst Negative Slack = **0.234 ns** (green), Failing endpoints 0. Click the *Setup* worst path: you should see the requantizer path (`…/res_reg → …/u_rq/p1_reg`, one DSP48E1).
2. **Reports → Report Utilization…** → *Summary*: **DSP 68**, **Block RAM 70**, LUT ≈ 1,900. Click *Block RAM* in the table: RAMB36 68 and RAMB18 4 (the activation buffers + weight ROMs).
3. **Window → Device**: the placed design on the XC7Z020 chip; **Window → Schematic** shows the hierarchy (`e1…e4` engines, `ram0…ram4`).
4. In the **Tcl console** (bottom) you can also type (these two are ✅ on the L3 checkpoint):
   `report_utilization` and `puts [get_property SLACK [get_timing_paths -max_paths 1 -setup]]` → `0.234` for the core.
If your numbers differ by a few LUTs but WNS and DSP/BRAM agree, that is placement/tool-version noise. If **DSP ≠ 68** or **BRAM ≠ 70**, something changed in the RTL — stop and investigate.

### 4.5 🖱️ (Optional, harder) Build your own Vivado GUI project — not tested by me
Only do this if you want to practise Vivado; Parts 3, 4.1–4.4 already cover the verification.
1. **File → Project → New…** → RTL Project → *Do not specify sources* → part **xc7z020clg484-1** (ZedBoard) → Finish.
2. **Add Sources → Add or create design sources** → add all of `hardware/rtl/common/*.v`, `hardware/rtl/conv_engine/conv_engine.v`, `hardware/rtl/sr_core/sr_tile_core.v` (uncheck "copy sources").
3. In *Sources*, right-click `sr_tile_core` → **Set as Top**.
4. **Settings → General → Generics** (or Tcl): `HC=64`, and **an absolute path** for the weights: `WDIR="/home/sreevenkat/Desktop/venkat/sem_project_all/hardware/rtl/weights/"` (note the trailing `/` and the quotes). A relative path will not be found because the project's run directory is not ROOT.
5. **Flow Navigator → Run Synthesis**, then **Run Implementation**. Add a clock constraint first (Add Sources → constraints, one line: `create_clock -period 10.000 -name clk [get_ports clk]`) or timing will say "no clocks".
6. Compare utilization and timing with 4.3. Typical stumbling blocks: wrong `WDIR` (messages `$readmem … cannot open file`), forgetting the clock constraint, "port not connected" warnings (normal: the core has no top-level pins assigned in out-of-context use).
The testbenches need extra steps in a GUI project (their data paths are relative to ROOT): see 4.5b.

### 4.5b ✅ Run ALL testbenches inside a Vivado GUI project (run by the owner on 2026-10-07: 25 PASS, 0 FAIL)
Works in any project you already created (the tested one was `ray_tracing_example`). Start Vivado from anywhere, open the project, then type in the **Tcl Console** (bottom of the window):
```tcl
source /home/sreevenkat/Desktop/venkat/sem_project_all/hardware/vivado/scripts/add_to_open_project.tcl
source /home/sreevenkat/Desktop/venkat/sem_project_all/hardware/vivado/scripts/sim_helpers.tcl
run_tb core            ;# expect: PASS sr_tile_core HC=6 tile small12 ... 10957 cycles
```
`add_to_open_project.tcl` adds all RTL + the weight files + all 6 testbenches and **copies** `hardware/rtl/weights` and `data/golden` into the project's simulation folder (`<project>/<name>.sim/sim_1/behav/xsim/`), because the testbenches open files like `data/golden/x.hex` relative to that folder. `data/golden` must exist first (`export_rtl.py`, `gen_unit_vectors.py`; the `real*` tiles need `data/train/HR`).
All commands (each prints one `PASS ...` line; `FAIL` = problem):
```tcl
run_tb core_stall        run_tb conv 1   (also 2 3 4)       run_tb conv_rand 1   (also 2 3 4)
run_tb requant 8         (1 2 3 8 21 23 24)                  run_tb mac    run_tb ram    run_tb splitram
run_tb rom 1             (1 2 3 4)                           run_tb core64 real0    ;# real size, ~15 s in xsim
```
* Do **not** type `run all` after a `run_tb`: the testbench has already reached `$finish`; the extra `run` hangs.
* If you regenerate `data/golden` or the weights, re-run the `add_to_open_project.tcl` line to refresh the copies.
* The warnings `filemgmt 56-199`, `glbl does not have a parameter named ...` and `Wavedata 42-489` are harmless.
* `hardware/vivado/scripts/create_project.tcl` builds a fresh project called `sr_accel` the same way (`vivado -source ...` from the project root).
* ⚠️ **Never put symbolic links to `hardware/` or `data/` inside a Vivado project folder.** `create_project -force` follows links and **deletes the real folders** (this happened on 2026-10-07; restored from git + regeneration). The scripts above use copies for this reason.

### 4.6 What Part 4 proves and does not prove
**Proves:** the design synthesizes without errors, ignored initializers or latches; uses 68 DSPs and 70 block RAMs (half the chip); meets 100 MHz after place and route (out-of-context); and the synthesized netlist behaves like the RTL.
**Does not prove:** anything about the real board: there are no pin assignments, no AXI/DMA/ARM, no I/O timing, no power measurement, and no image has been upscaled on hardware. The frame time of ≈ 1.25 s (≈ 0.8 fps) is **simulated cycle counting** (135 tiles × 926,197 cycles ÷ 100 MHz), not a measurement.

---

## 5. Try to break it — proof that the tests are real (do this in a SANDBOX copy)

Never experiment in ROOT. Make a throw-away copy of the tracked files:
```bash
SB=/tmp/sandbox ; rm -rf $SB ; mkdir $SB
git ls-files -c -o --exclude-standard -z | xargs -0 -I{} cp --parents {} $SB/
ln -s $PWD/data/train $SB/data/train ; ln -s $PWD/data/test $SB/data/test ; ln -s $PWD/.venv $SB/.venv
cp -r data/golden/. $SB/data/golden/
cd $SB
```
(The copy of `data/golden` matters: if it is missing, `run_tests.sh` regenerates the weight files and silently repairs your damage — that happened to me once in a first, invalid control.)

| # | Break this (in the sandbox) | Run | You should see |
|---|---|---|---|
| 1 | Corrupt one weight: `python3 -c "p='hardware/rtl/weights/wrom_L1.mem';L=open(p).read().split('\n');L[5]=L[5][:-2]+'%02x'%((int(L[5][-2:],16)+1)&255);open(p,'w').write('\n'.join(L))"` | `.venv/bin/python -W error software/ai/quantization/test_export.py` and `hardware/verification/run_tests.sh quick` | both **exit 1**; `FAIL weight_rom layer 1`, `FAIL layer 1 tile small12: … wrong bytes` ✅ |
| 2 | In `hardware/rtl/common/requant.v` change `s2 <= p1 + RND;` to `s2 <= p1;` (removes rounding) | `run_tests.sh quick` | `FAIL requant SHIFT=…: … errors` (many) ✅ (equivalent breakage was caught in my run) |
| 3 | In `hardware/rtl/sr_core/sr_tile_core.v` swap `{oc[1:0], oy[0], ox[0]}` to `{oc[1:0], ox[0], oy[0]}` (pixel-shuffle order) | `run_tests.sh quick` | `FAIL sr_tile_core …` (output bytes wrong) ✅ |
| 4 | Make a golden file short or remove it: `head -n 100 data/golden/small12_out.hex > /tmp/x && cp /tmp/x data/golden/small12_out.hex` (or `rm data/golden/small12_out.hex`) | `hardware/verification/run_tests.sh quick` | exit **1**: `FAIL: 332 undefined bytes in data/golden/small12_out.hex` (for the deleted file: `432 undefined bytes`) ✅. This guards against a test that passes because *nothing* was compared. (Only deleting `small12_in.hex` makes the runner regenerate everything.) |
| 5 | Flip one byte in `data/golden/seam/hc8_t1_1_rtl.hex` (after running the quick suite once) | `.venv/bin/python software/ai/quantization/seam_test.py check --hc 8` | `FAIL seam hc=8: 1 wrong pixels`, exit 1 ✅ |
| 6 | In `software/ai/quantization/integer_reference.py` change `255` in `np.clip(y, 0, 255)` to `254` | `.venv/bin/python -W error software/ai/quantization/test_integer.py` | a test fails with a traceback, exit non-zero ✅ (I ran 22 such breakages on this file family; all were caught) |

After each experiment restore with `cp` from ROOT (or just delete `/tmp/sandbox` and redo the copy). **If any breakage above passes silently, tell me: that would be a hole in the tests.**

---

## 6. Reference

### 6.1 Master table: every number and where to check it
| Claim | Value | How to check |
|---|---|---|
| Model size | 2,620 parameters, 2,560 MACs per input pixel | `test_model.py` (`test_counts_match_docs`), train smoke test prints it |
| FP32 gain over bicubic (PSNR-Y) | +1.53 / +1.18 / +1.04 dB (Set5/Set14/BSD100), 119/119 images | 2.5 |
| INT8 vs FP32 | mean drop 0.18 / 0.11 / 0.08 dB, worst image 0.41 dB | 2.7 |
| Tiled == whole image (integer model) | exactly equal | `test_integer.py`, seam test (3.2) |
| RTL == integer model | bit-exact, all layers, 9 real tiles + random layers | 3.2 / 3.3 |
| Cycles per tile (core) | 926,197 (engines 854,145 + byte-wide I/O ≈ 72,052) | 3.3 |
| Frame time estimate | ≈ 1.25 s at 100 MHz (≈ 0.8 fps), **simulated** | arithmetic, section 4.6 |
| Resources, whole core | 1,900 LUT, 3,337 FF, 68 DSP, 70 BRAM tiles | 4.3 |
| Timing at 100 MHz (routed, out-of-context) | WNS +0.234 ns, hold +0.081 ns (thin and placement-dependent: it was +0.146 ns before a small fix) | 4.3 / 4.4 |

### 6.2 What is NOT verified (be honest in any report)
* Nothing has run on the **ZedBoard** (no board available): no UART, AXI, DMA, ARM driver, HDMI, power or real fps. Milestones M0, M6, M7 are not done.
* The post-synthesis simulation covers only the small 12×12 tile, and for the core only the stream interface.
* Timing numbers are **out-of-context** (no I/O constraints) and the margin is thin.
* Near-duplicate images between train and test are not machine-checked.
* Training is not bit-reproducible; the committed checkpoint is the frozen artifact.
* The early estimates in `docs/PROJECT_PLAN.md` (e.g. ~6 fps) are superseded by the measured/simulated values above.

### 6.3 Troubleshooting
| Symptom | Likely cause / fix |
|---|---|
| `vivado: command not found` | run `source ~/Desktop/vivado_install/Vivado/2024.1/settings64.sh` in this terminal |
| `iverilog: command not found` | `sudo apt install iverilog` (project used 12.0) |
| `ModuleNotFoundError` (numpy/torch/skimage) | you are not using `.venv/bin/python`; `torch` etc. come from the system packages (`--system-site-packages`) |
| `SKIP` lines in the Python tests | datasets missing in `data/` — the result is "not verified", fetch the data (`data/README.md`) |
| Everything `FAIL`s with "undefined bytes in …" | `data/golden` is missing/short: `.venv/bin/python software/ai/quantization/export_rtl.py` and `gen_unit_vectors.py` |
| `run_tests.sh` changes files in `hardware/rtl/weights` | it regenerated them because `data/golden` was missing; `git status` / `git diff` afterwards — they must be unchanged |
| xsim: "Module … doesn't have a timescale" | add `-timescale 1ns/1ps` to `xelab` (see 4.1) |
| xsim: testbench cannot open `data/golden/…` | `xsim` was started from the wrong folder: run it from ROOT |
| GUI project: `FAIL: ... undefined bytes in data/golden/<tile>_in.hex` | the file is missing in `data/golden` (e.g. `real0` needs `data/train/HR` before `export_rtl.py`) or the project's copy is stale: regenerate, then re-run `add_to_open_project.tcl` (4.5b) |
| Netlist simulation does nothing / times out | the testbench must wait for `glbl.GSR` (already done); with your own testbench wait ≥ 100 ns before stimulus |
| Vivado: `$readmem … cannot open` | file path (`WDIR`/`W_FILE`) not absolute inside a GUI project (4.5) |
| Different WNS by ± 0.1 ns | normal placement noise after any netlist change; DSP/BRAM counts must still match |
| Stray `clockInfo.txt`, `xsim*.jou` in ROOT | created by xsim; safe to delete (git-ignored) |

### 6.4 Where things are
`README.md` (overview) · `CLAUDE.md` (running log, all measured numbers) · `HANDOFF.md` (state, environment, next steps) · `docs/milestones/M0…M8.md` (explanations + results sections) ·
`results/quality/` (accuracy tables) · `results/utilization/` (Vivado reports, cycle counts) · `CLAUDE_AUTONOMOUS.md` (the exact verified commands in short form).
