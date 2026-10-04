# CLAUDE.md — Project memory for Claude Code

> **New session? Read `HANDOFF.md` first** (state, GitHub/commit rules, environment, exact next steps for M3).

> **Rule: update this file after EVERY change to the project** (new file, finished step, decision, measured number).
> Add one line to the Update Log (Section 8) and refresh the Status table (Section 5).

## 1. Project in one paragraph
FPGA-accelerated image super-resolution on a **ZedBoard (Zynq XC7Z020-CLG484)**. A small INT8 CNN upscales
**960×540 → 1920×1080 (×2)**. Trained on the PC (PyTorch), quantized to INT8, run by a Verilog tile-engine in the FPGA
fabric (PL), controlled by an ARM bare-metal C program (PS) over AXI-Lite + AXI DMA. **No 4K** (not realistic on 220 DSPs).
Input is plain **RGB** (no depth/normals; a ray-tracer front end is an optional extra, see docs/milestones/M8).

## 2. Owner context
- Has a Verilog RISC-V (PL-only) background; **new** to Zynq PS/PL, AXI, DMA, CNN hardware, PyTorch quantization.
- **Does not have the ZedBoard yet** (will borrow from college). Do all PC-only work first: M1, M2, M3, then RTL
  simulation for M4/M5. Board-dependent: M0 and M6.
- Wants beginner-friendly explanations, tidy folders, and each step documented.

## 3. Folder layout (keep software, hardware, data and docs SEPARATE)

```
sem_project_all/
├── HANDOFF.md                 ← start here in a new session (state, GitHub, env, next steps)
├── CLAUDE.md                  ← this file (project memory + update log)
├── README.md                  ← public overview (GitHub front page)
├── .gitignore
├── docs/                      ← all documentation, no code
│   ├── PROJECT_PLAN.md        ← overall plan and feasibility
│   ├── milestones/            ← README + M0…M8 step-by-step guides
│   └── resources/             ← original planning .md files + reference papers (PDF)
├── software/                  ← everything that runs on a PC or on the ARM
│   ├── ai/                    ← Python: dataset, models, training, quantization, evaluation
│   │   ├── dataset/  models/  training/  quantization/  evaluation/  scripts/  checkpoints/   (quantization/: quantize, integer_reference, export_rtl, qparams.npz, tests)
│   ├── arm_driver/            ← C code for the Zynq ARM (Vitis, bare-metal)
│   └── host_tools/            ← PC helper scripts (png↔raw conversion, serial/JTAG helpers)
├── hardware/                  ← everything that becomes FPGA logic
│   ├── rtl/                   ← Verilog: common/ conv_engine/ sr_core/ axi_wrapper/ top/ + weights/ (exported .mem, M3)
│   ├── verification/          ← tb/ (Verilog testbenches), run_tests.sh, cocotb/ vectors/ reference/ (unused so far)
│   └── vivado/                ← scripts/ (Tcl) and constraints/ (.xdc); build output is git-ignored
├── data/                      ← datasets and golden test vectors (large files git-ignored)
│   ├── train/HR/  test/HR/  test/LR/  golden/
└── results/                   ← measured numbers only: quality/ speed/ utilization/ images/
```

Rules:
- No Python in `hardware/` except cocotb tests; no Verilog in `software/`.
- Generated files (Vivado builds, checkpoints, datasets) are never committed.
- Milestone guides are in `docs/milestones/`; follow them in order and tick each exit checklist.

## 4. Technical decisions already made
- Scale ×2; network: Conv3×3(3→16)+ReLU → Depthwise3×3(16)+ReLU → Conv1×1(16→16)+ReLU → Conv3×3(16→12) → PixelShuffle(2).
  2,620 parameters, 2,560 MACs per input pixel.
- INT8: uint8 activations, int8 symmetric weights, int32 accumulators, requantize `(acc·M + round) >> SHIFT`, clamp.
- Reference chain: **PyTorch FP32 → NumPy integer model (golden) → RTL**. RTL is compared with the integer model, bit-exact.
- Golden model convention: replicate-pad the whole input by **3 px** (decided, used in M2 training and eval), then **valid** convolutions.
- Tile engine: 64×64 core tile + 3 px halo = 70×70 input, ping-pong BRAM, pixel-major 128-bit words, folded MACs (P=16 first).
- Pixel shuffle channel order: `k = 4·c + 2·dy + dx` (PyTorch convention).
- OpenCV loads BGR; choose and document one colour-order convention in every script.
- Estimates (to be verified by measurement): ~1 fps for the first RTL version at 100 MHz; ~5–10 fps after optimization.

## 5. Status

| Milestone | Needs board? | Status |
|---|---|---|
| M0 Zynq basics | yes | not started (waiting for board) |
| M1 Software baseline | no | **DONE** (hardened 2026-10-03: 3 test sets, official-LR validated, 9 tests, all images reviewed) |
| M2 Train FP32 CNN | no | **DONE** 2026-10-03 (hardened: 180-image model, ablations, repro + border checks, full visual review) |
| M3 INT8 + integer model | no | **DONE** 2026-10-04 (PTQ, drop 0.08-0.18 dB mean PSNR-Y, tiled == whole exactly, exports + golden tiles, 22/22 mutations caught) |
| M4 Conv engine RTL | simulation only | **DONE** 2026-10-04 (all 4 layers bit-exact on 10 golden tiles + randomized layers, 57 sim runs, re-run + reset-abort sweep, synthesized netlists simulate exact, 32 RTL breakages caught, routed 100 MHz met out-of-context) |
| M5 Full network RTL | simulation only | **DONE** 2026-10-04 (tile core bit-exact on 9 real-size tiles, layer buffers + output stream, seam test 20 + 4 tiles, 73 sim runs, netlist sim, 21 breakages caught, routed 100 MHz met with only +0.234 ns) |
| M6 AXI/DMA/ARM driver | yes | not started |
| M7 Benchmark + report | yes | not started |
| M8 Optional extensions | — | not started |

## 6. Measured results (fill in only real numbers)

| Item | Value |
|---|---|
| Bicubic x2 (PSNR RGB / SSIM RGB / PSNR Y / SSIM Y) | Set5: 31.79 / 0.9088 / 33.67 / 0.9303; Set14: 28.30 / 0.8426 / 30.32 / 0.8698; BSD100: 28.23 / 0.8299 / 29.56 / 0.8434 |
| Nearest x2 (same metrics) | Set5: 29.08 / 0.8783 / 30.86 / 0.9001; Set14: 26.72 / 0.8202 / 28.58 / 0.8464; BSD100: 27.10 / 0.8117 / 28.42 / 0.8251 |
| FP32 CNN x2 final (PSNR RGB / SSIM RGB / PSNR Y / SSIM Y) | Set5: 33.12 / 0.9244 / 35.21 / 0.9449; Set14: 29.29 / 0.8688 / 31.51 / 0.8975; BSD100: 29.24 / 0.8673 / 30.60 / 0.8785 (PSNR-Y gain over bicubic: +1.53 / +1.18 / +1.04 dB; wins 119/119) |
| INT8 integer model (PSNR RGB / SSIM RGB / PSNR Y / SSIM Y) | Set5: 32.83 / 0.9160 / 35.02 / 0.9420; Set14: 29.15 / 0.8617 / 31.40 / 0.8948; BSD100: 29.11 / 0.8609 / 30.53 / 0.8756 (PSNR-Y drop vs FP32: 0.18 / 0.11 / 0.08 dB mean, worst image 0.41 dB; still wins 119/119 over bicubic) |
| FPGA resources (LUT/FF/BRAM/DSP) | **Whole tile core (M5, after place&route, out-of-context): 1,900 LUT, 3,337 FF, 68 DSP (31 %), 70 BRAM tiles (50 %), routed WNS +0.234 ns / WHS +0.081 ns at 100 MHz**; synthesis 2,028 LUT. Per-engine (M4): L1 360/850/2/18, L2 397/952/0/18, L3 361/840/0/18, L4 347/692/1.5/14 (LUT/FF/BRAM36/DSP), routed WNS +0.135/+0.261/+0.582/+0.698 ns. No AXI/DMA wrapper yet. |
| Time per frame / FPS | Not measured on a board. **Simulated whole tile core: 926,197 cycles per 64x64 tile (identical on all 9 golden tiles) x 135 tiles = 125.0 M cycles = ~1.25 s (~0.80 fps) at 100 MHz**, compute + byte-wide stream I/O, excluding DMA/ARM. (Engines alone: 854,145 per tile, ~1.15 s.) |

## 6b. Environment and data notes
- FPGA tools: Vivado/Vitis/Vitis HLS 2024.1 in `~/Desktop/vivado_install/`; Icarus Verilog 12 installed; cocotb/Verilator not; ZedBoard board files not installed; an older `~/Desktop/VITIS_WORKSPACE` exists (unverified). GitHub repo renamed: origin = `git@github.com:sreeveenkat/FPGA-Image-Super-Resolution-Accelerator.git` (details in HANDOFF.md section 6).
- Python env: `.venv/` in project root (created with `--system-site-packages`; numpy, opencv, matplotlib come from the system, scikit-image installed in the venv). Run scripts with `.venv/bin/python` from the project root. PyTorch 2.12 (+cu130) comes from system site-packages and now sees the GPU (see section 6c).
- Training data: General-100's original link is dead, so 60 DIV2K *training* images (img0193–img0252, 1092–2040 px) were downloaded from the HF mirror `ScooterTaylor/DIV2K_captioned_subset` into `data/train/HR/` with `software/ai/scripts/fetch_div2k_subset.sh [COUNT]` (resumable; up to 192 available, ~1 MB/s). Add more in M2 if needed. Test sets stay Set5/Set14 only; `check_dataset.py` verifies no train/test overlap.
- pip downloads are slow/flaky on this machine: install in the background (`nohup ... &`) and poll.
- Test data (original names): Set5 (5), Set14 (14), BSD100 (100) from HF `eugenesiow/*` into `data/test/HR/<set>/`; official x2 LR in `data/test/LR_official/`. See `data/README.md` (also has the old img_NNN -> name map).
- **LR protocol:** modcrop HR to even sides, then Pillow BICUBIC downscale. Bit-exact with official LR for all even-sized images (Set5 5/5, Set14 11/11); odd-sized images (3 in Set14, all 100 BSD100) are re-aligned on purpose (official files resize the uncropped HR, 2.005x, misaligned). So BSD100/odd-image numbers differ slightly from literature. Verified by `software/ai/dataset/check_lr_protocol.py`.
- Metrics: SSIM = Gaussian 11x11 sigma 1.5 (paper definition); skimage default SSIM kept only as a CSV column. Y = BT.601, 2-px shave. `bicubic` = Pillow bicubic upscale; `bicubic_cv2` (OpenCV) is comparison only and is ~0.2 dB higher.
- Earlier first-draft numbers (OpenCV LR, no anti-alias) were discarded; do not compare with them.
- Colour convention: RGB uint8 everywhere in Python (loaders convert from OpenCV BGR).
- `requirements.txt` pins package versions. A git repo now exists INSIDE this folder (`git init` done 2026-10-03, branch main); checkpoints (14 KB each) are tracked, datasets/images/.venv ignored. Commits are made only when the user asks (see HANDOFF.md section 6).

## 6c. M2 facts
- Model: `software/ai/models/srnet.py`; all convs VALID, input padded by HALO=3 (replicate for full images, real neighbours when tiling/training). 2,620 params, 2,560 MACs/px (asserted in tests).
- **Final checkpoint** `software/ai/checkpoints/srnet_fp32.pt` = experiment A (L1, ch16) trained on 180 DIV2K images (img0193-0384 minus last 12 = validation), selected on validation only. Command: `.venv/bin/python software/ai/training/train.py --epochs 100 --steps 500 --images 192 --val 12 --threads 4 --out software/ai/checkpoints/srnet_fp32.pt` (~33 min CPU when 4 jobs share the machine). Old 55-image model kept as `srnet_fp32_v1.pt`; experiment checkpoints in `checkpoints/exp/` (all git-ignored; back up before deleting).
- Training is statistically but NOT bit-reproducible (rerun differs by 0.02 dB val; thread count affects float order). Treat the checkpoint, then the M3 exported weights, as the frozen artifact.
- Ablations (SSIM loss, edge windows, ch24) all within noise of plain L1/ch16 -> keep simplest. Details: `results/quality/m2_training_summary.md`, `training_curves.png`.
- Border effect measured (`evaluation/border_effect.py`): outer-8px gain +0.83 dB vs interior +0.98 dB; not fixable by edge-aware training; ignore.
- Eval: `evaluation/eval_model.py` -> `results/quality/model_fp32_x2.{md,csv}`, figures `results/images/model_fp32_*`, `modelzoom_fp32_*`. Tests: `test_model.py` (9 tests incl. tiled == whole-image, SSIM loss vs skimage, rounding/clamp, replicate padding, real-image win over bicubic by >0.5 dB) and `test_baseline.py` (13). Tests needing datasets print SKIP when data is missing.
- Visual review done on all 19 Set5/Set14 zoom crops + 4 BSD100 (worst/median/best) + 1 full frame: sharper edges/text/stripes, no checkerboard or colour shift; fine random texture (gravel, fur, Barbara cloth) not recovered.
- Seed spread (seed 0 vs 1): 0.03-0.09 dB on test sets; quote gains as ~+1.0 to +1.5 dB (+/-0.1). Target-res check (`evaluation/check_target_res.py`): 960x540->1080p works (~0.1 s CPU), 135 tiles == whole image to 6.6e-7 float. Training images visually reviewed, no near-duplicates with test sets. Eval rerun byte-identical.
- 1 training "epoch" = 500 steps x 32 patches = 16k patches (~0.14 pass over data); 100 epochs = ~14 passes.
- GPU: RTX 3050 6GB laptop, **working since 2026-10-03** (installed prebuilt `linux-modules-nvidia-595-server-open-7.0.0-34-generic` + driver 595.91.07; `torch.cuda.is_available()` = True, CUDA 13.0). Step is ~2.3x faster than CPU but training is dominated by NumPy patch sampling, so the end-to-end gain is smaller; `train.py` has no `--device` flag yet (CPU). GPU conv uses TF32, so CPU/GPU forward differs ~1e-4 (irrelevant for the integer model).

## 6d. M3 facts
- Scheme: uint8 activations (one scale/layer), int8 symmetric weights [-127,127] **per-layer scale** (per-channel was slightly worse), int32 bias, `M` uint16 per out channel + `SHIFT` per layer (24, 23, 21, 24), requant `(acc*M + 2^(SHIFT-1)) >> SHIFT` clamp [0,255]; input scale 1/255, last-layer output scale 1/255. `acc*M` needs ~40 bits; acc fits int32 (tested).
- Settings chosen on the 12 VALIDATION images only (`results/quality/m3_ptq_sweep.md`): activation range = 99.99th percentile of all post-ReLU values over 100 training crops. 99 % is catastrophic (-5.3 dB), 99.9 % -0.43, 99.99 % -0.22, max -0.28. PTQ is enough; QAT not needed.
- Golden model: `software/ai/quantization/integer_reference.py` (`upscale`, `upscale_tiled`, `run_tile`, `forward_layers`); parameters in `quantization/qparams.npz` (tracked, 11 KB, deterministic re-quantization verified). Never regenerate with a different FP32 checkpoint without redoing the sweep/exports.
- Exports (tracked): `hardware/rtl/weights/{weights,bias,mult}_L{1..4}.mem`, `network_params.vh`, README (layout `[co][ci][ky][kx]`). Golden tiles (git-ignored, regenerate with `export_rtl.py`): `data/golden/<tile>.npz` + byte-per-line `.hex` dumps `[y][x][c]`; 10 tiles incl. zeros/full255/noise/pixel/ramp/small12/real/border; between them every layer hits both 0 and 255.
- Verification: `test_integer.py` (21), `test_export.py` (7), a pure-Python recompute of all 10 golden tiles from only the exported .mem/.vh/.hex files (matches; corrupting one weight is detected), a clean-copy rebuild (qparams, .mem, .vh and golden files byte-identical), layerwise check against an independent float64 torch implementation (<=1 LSB, 0.004-0.06 % of values differ), INT8 vs FP32 output 48 dB on a test image, tiled == whole exactly (also non-multiples of 64, real image), 22 deliberate breakages all caught, `eval_int8.py` rerun byte-identical. `torch.ao` quantization was NOT used as a reference (deliberate, documented in the M3 guide).
- Drop per set (mean PSNR-Y): Set5 0.18, Set14 0.11, BSD100 0.08; worst single image 0.41 dB (BSD100). SSIM-Y drop ~0.003.
- Integer model speed on this CPU (measured once): 0.4 s for 481x321, 1.6 s for 960x540 (NumPy int64); the sweep (8 configs x 12 images) takes ~4 min.

## 6e. M4 facts
- Engine: `hardware/rtl/conv_engine/conv_engine.v` (+ `common/{mac_unit,requant,tile_ram,weight_rom}.v`). ONE INSTANCE PER LAYER, compile-time params `C_IN,C_OUT,K,DEPTHWISE,IN_W,IN_H,SHIFT` + files `wrom_Ln.mem, bias_Ln.mem, mult_Ln.mem`. VALID conv. Memories are outside the engine: read port `in_addr -> in_data` (1-cycle latency), write port `out_we/out_addr/out_data`; word = pixel-major, channel c at bits `8c+:8`, address `y*width+x`; input word width `8*C_IN` (L1: 24 bits), output `8*C_OUT` (L4: 96 bits). Interface: `rst` (sync, a ONE-cycle reset is enough and leaves the engine quiet), `start` pulse, `busy`, `done` pulse, `cycles`. Restart after `done` works (tested).
- Schedule: STEPS = K*K*(depthwise ? 1 : C_IN); a new pixel every PERIOD = max(STEPS, C_OUT) cycles (one shared requantizer, 3-stage, overlapped with next pixel's MACs). Measured per pixel: L1 27, L2 16 (not 9!), L3 16, L4 144. Per 64x64 tile: 124,871 / 69,712 / 69,719 / 589,843 cycles (data independent, identical in the netlist simulation).
- Weight ROM: the RTL loads `wrom_Ln.mem` (step-major, written by `export_rtl.py` next to the canonical `weights_Ln.mem`). DO NOT rebuild ROM layout in an `initial` loop: simulation passes but Vivado ignores it (Synth 8-311) and removes the logic.
- Vivado traps: small 9x8 multiplies go to LUTs unless `(* use_dsp = "yes" *)` (set on `mac_unit`); always check `grep 8-311` / DSP count in the synthesis log (Vivado keeps `*.backup.log` copies of old runs: do not glob them). Netlist simulation must wait for `glbl.GSR`. Script: `hardware/vivado/scripts/synth_conv_engine.tcl <layer> [clk_ns] [small|impl]` from the project root (build output git-ignored; copies of the reports in `results/utilization/`).
- Tests: `hardware/verification/run_tests.sh quick|full` (iverilog 12, Verilog self-checking TBs, NOT cocotb) and `run_postsynth.sh` (xsim on the synthesized netlists, small tile, ~1 min). Vectors: `gen_unit_vectors.py` -> `data/golden/unit/` (requant vectors for shifts 1,2,3,8,21,23,24 and randomized layers randL1-4 with distinct M per channel, non-square 10x8 tiles). Testbench stimulus is driven on the falling edge (driving at the rising edge raced with the DUT). Every small/randomized run also does: poisoned output RAM, immediate re-run, PERIOD+6 one-cycle-reset aborts with an idle monitor, fresh run.
- Verification summary: 57 runs in `full` (13 unit + 40 layer + 4 randomized), 25 in `quick`; 4/4 post-synthesis netlists exact. 32 RTL breakages all caught on the final RTL (equivalent mutants: `> 254` clamp, MAC valid reset gate which was removed). The randomized tests are the ONLY ones catching a shared-M-for-all-channels bug and a wrong row stride on non-square tiles; the reset sweep is the ONLY thing catching missing reset gates.
- Timing: routed, out-of-context (no I/O timing): WNS +0.135 (L1) / +0.261 / +0.582 / +0.698 ns at 10 ns, hold >= +0.10; critical path = `rq_i` -> result mux -> requantizer DSP. Little margin above 100 MHz (register the mux output first).
- Memory finding: a 70x70x128-bit `tile_ram` infers 32 RAMB36, not ~20: two ping-pong buffers = 64 of 140 BRAM36. M5 must plan for it.
- Not done in M4 (deliberately): chained layers (M5), ping-pong buffer wiring, pixel shuffle, AXI; the post-synthesis simulation covers only the small 12x12 tile (full 70x70 netlist simulation not run, too slow); nothing measured on a board. The layer tests feed each layer the GOLDEN output of the previous one.

## 6f. M5 facts
- Core: `hardware/rtl/sr_core/sr_tile_core.v` (params `HC`=64, `SHIFT1..4` = 24,23,21,24 = the exported ones (testbench-checked), `WDIR`). Ports: `rst` (sync, 1 cycle enough), `start` pulse, `busy`, `done` pulse, byte stream in (`in_valid/in_data/in_ready`; ready only during the load phase, exactly (HC+6)^2*3 bytes, RGB raster [y][x][c]), byte stream out (`out_valid/out_data/out_ready/out_last`, 2HC x 2HC x 3 bytes), `cycles`.
- Structure: input loader -> ram0 (24 b) -L1-> ram1 (128 b) -L2-> ram2 -L3-> ram3 -L4-> ram4 (96 b) -> pixel shuffle (k = 4c+2dy+dx) + packer. Four `conv_engine`s run one after the other (sequencer = FSM in the same file); ONE RAM per boundary (no ping-pong). RAMs are `common/tile_ram_split.v` (power-of-two part + remainder; `peek()` helper for testbenches).
- Block RAM: a plain 4624x128 RAM = 32 RAMB36 (Vivado rounds cascade depth to a power of two); split RAM = 18.5. Whole core = 70 BRAM tiles (50 %), 68 DSP. Do not go back to the plain RAM.
- Cycles per tile 926,197 = engines 854,145 + ~72,052 I/O (load 14,700, output 49,152 bytes + ~8,200 fetch cycles; derived). Load, compute and output are not overlapped: a future speed-up is double buffering at tile level (more RAM) or a wider stream.
- Tests (`run_tests.sh quick` ~2 min / 29 runs; `full` ~20 min / 73 runs): `tb_sr_tile.v` (+TILE/+TILE2/+STALL/+REPEAT/+NOEXTRA/+SWEEP/+IN/+OUT/+MID/+DUMP plusargs) checks ram1..ram4 byte for byte, the output stream incl. count and `out_last`, protocol (no output before ready, `in_ready` only in LOAD), poison pattern, re-run, 2nd tile, 60 one-cycle-reset aborts + quiet check, default SHIFT parameters. Seam test: `software/ai/quantization/seam_test.py gen|check` (HC=8: 37x29 LR region -> 20 tiles; HC=64: 100x90 -> 4 tiles), data in `data/golden/seam/` (git-ignored).
- Netlist: `synth_sr_tile_core.tcl [clk_ns] [impl|small]`; `run_postsynth.sh` also simulates the HC=6 core netlist (stream interface only; internals are not visible). Routed WNS only +0.234 ns (critical path e1 requantizer feed): do not add logic on that path without pipelining it.
- Breakage checks on the core: 21 deliberate breakages all caught; the one that first survived (wrong DEFAULT shift, because the TB overrode the parameters) led to the default-parameter check. Vacuous-pass guards: missing/short golden files FAIL; seam checker catches one flipped byte.
- Known limits: byte-wide streams (slow), no AXI/DMA wrapper, no board run, netlist simulation only at HC=6, out-of-context timing without I/O constraints.

## 7. Conventions
- Python 3, type hints where useful, fixed random seeds, scripts runnable from the project root.
- Commit scripts, constraints, `.mem` weight files, small test vectors, reports. Don't commit build folders.
- Never claim a number that wasn't measured. Be honest about failures in the README.
- Keep `docs/milestones/*.md` as the source of explanation; keep this file as the source of status.

## 8. Update Log (newest last)

| Date | Change |
|---|---|
| 2026-10-03 | Read all planning docs and the 3 reference papers in `resources/`. |
| 2026-10-03 | Wrote `docs/PROJECT_PLAN.md` (feasibility, architecture, milestones). Decided: drop 4K, target 960×540→1080p ×2, plain RGB. |
| 2026-10-03 | Wrote milestone guides `docs/milestones/README.md` and `M0…M8`. |
| 2026-10-03 | Created tidy folder structure (`docs/ software/ hardware/ data/ results/`), moved docs, fixed paths in milestone guides, added `.gitignore` and this `CLAUDE.md`. |
| 2026-10-03 | **M1 done.** Added `software/ai/dataset/pairs.py`, `software/ai/evaluation/{metrics,eval_baseline,test_baseline}.py`; created `.venv`; fetched Set5/Set14; baseline numbers in `results/quality/baseline_x2.{md,csv}`, comparison images in `results/images/`. 4 unit tests pass; re-run is bit-identical. |
| 2026-10-03 | M1 data step completed: downloaded 60 DIV2K train images (`fetch_div2k_subset.sh`), added `software/ai/dataset/check_dataset.py` (decode, no duplicates, no train/test overlap, LR present) — passes. Fixed premature checklist tick in M1 doc. |
| 2026-10-03 | **M1 hardened.** Added BSD100; restored original image names; new LR protocol (Pillow bicubic, modcrop) validated vs official LR; Gaussian SSIM; divide-by-zero warning removed; zoomed edge crops + all 19 Set5/Set14 figures reviewed visually; 9 tests incl. real data/CSV; `requirements.txt`, `data/README.md`; full re-run byte-identical (159 files). Baseline numbers REPLACED (earlier ones used a non-standard LR). |
| 2026-10-03 | **M2 done.** Added `models/srnet.py`, `training/train.py`, `evaluation/eval_model.py`, `evaluation/test_model.py`; trained FP32 model; wins on all 119 test images (+1.0 to +1.4 dB PSNR-Y). Diagnosed GPU: driver module missing for kernel 7.0.0-34 (needs sudo). |
| 2026-10-03 | **M2 hardened.** Reproducibility rerun (0.02 dB, not bit-exact); downloaded 192 DIV2K images; added `--ssim/--edge-aug/--images/--val/--threads` to train.py; ablations A-D (no meaningful differences); final model retrained on 180 images; `border_effect.py`; loss curves; all outputs reviewed; tests 7 (model) + 9 (baseline) pass; `m2_training_summary.md`. Numbers above REPLACE the first v1 numbers. |
| 2026-10-03 | **Verification pass on M1+M2.** Target-res + tiled-vs-whole check (script), training-image review + near-duplicate check, seed-1 run (spread 0.03-0.09 dB), doc numbers cross-checked against CSVs (fixed +1.54/+1.19 -> +1.53/+1.18), eval rerun byte-identical, stale text fixed in M2/M5 guides (padding decision = replicate), `git init` in project folder, `.gitignore` updated. |
| 2026-10-03 | **Recheck pass.** Fixed 3 bugs (`--val 0` slice, curl `-f` + PNG check, torch pin). Mutation-tested the code (18 deliberate breakages): first run exposed 6 test gaps, added 6 tests + clean SKIP; now 18/18 caught. Fresh GitHub clone: compile/pyflakes OK, 22 tests pass, regenerated baseline + model results byte-identical to committed. Repo pushed to GitHub (still has old long name; rename pending on user's side). |
| 2026-10-03 | GitHub repo renamed by user to `FPGA-Image-Super-Resolution-Accelerator`; local `origin` updated. GPU fixed (prebuilt NVIDIA module for kernel 7.0.0-34 + driver upgrade to 595.91.07); PyTorch CUDA verified. |
| 2026-10-03 | Wrote `HANDOFF.md` (full state, GitHub rules, environment, M3 spec, verification commands). Fact-checked environment: Vivado/Vitis 2024.1 + iverilog present, cocotb/Verilator/board files missing; Pillow is a system package. Corrected the M3 guide's code sketch (valid convs, last-layer clamp 0-255) and executed it. |
| 2026-10-04 | **Doc consistency pass.** Fixed wrong file names in M2 guide (`srnet.py`, `eval_model.py`) and M7 script path; ticked M1/M2 exit checklists after re-verifying (22 tests pass, dataset check OK, eval rerun leaves `results/quality` unchanged, checkpoint sha256 `f1ae81f706ad3707`). Nothing committed. |
| 2026-10-04 | **M3 done.** Added `quantization/{quantize,integer_reference,export_rtl,test_integer,test_export}.py`, `evaluation/eval_int8.py`, `qparams.npz`, `hardware/rtl/weights/*`, `data/golden/README.md` (+ generated golden tiles), `results/quality/{m3_ptq_sweep,model_int8_x2}.*`. PTQ sweep on validation images -> 99.99 pct, per-layer weights, drop 0.08-0.18 dB. 27 tests pass, 22/22 mutations caught, eval rerun identical. Updated README, M3 guide, HANDOFF. Not committed yet. |
| 2026-10-04 | **M4 done and re-audited.** Added `hardware/rtl/common/{mac_unit,requant,tile_ram,weight_rom}.v`, `hardware/rtl/conv_engine/conv_engine.v`, `hardware/verification/{run_tests.sh,run_postsynth.sh,tb/*}`, `hardware/vivado/scripts/synth_conv_engine.tcl`, `software/ai/quantization/gen_unit_vectors.py`, `wrom_Ln.mem` export, `results/utilization/m4_*`. Found and fixed: ROM built in an `initial` loop ignored by Vivado (sim passed, synthesis removed the engine); LUT multipliers instead of DSPs; invalid requant vectors (acc beyond int32); TB start race; incomplete reset (valid flags not cleared) and untested restart/abort (added re-run + one-cycle-reset sweep); netlist TB must wait for GSR. Final: 57 sim runs, 4/4 netlist sims exact, 32 RTL breakages caught, routed 100 MHz met (L1 margin +0.135 ns), 68 DSPs, activation buffer 32 BRAM36. Not committed yet. |
| 2026-10-04 | **M4 verification pass 3 + autonomous-run setup.** Found that two testbench checks could pass vacuously (tb_requant with a missing vector file printed `PASS 0 vectors`; tb_conv_layer passed when BOTH the input and expected golden files were missing, X === X): added explicit guards and confirmed they fire. Re-ran synthesis + place&route for all 4 layers and diffed against `results/utilization` (identical); 57 sim runs, 4/4 netlist sims, Python suites and clean-copy runs pass; verify commands confirmed to exit non-zero on a corrupted weight (a first negative control was invalid because the runner regenerated the files). `run_postsynth.sh` now removes the xsim files it leaves in the project root (`clockInfo.txt`, `xsim*.jou`). Added `CLAUDE_AUTONOMOUS.md` (verified commands, definition of done, workflow rules) and `RUN_PROMPT.md` (template, `<TASK>` placeholder). Nothing committed. |
| 2026-10-04 | **M5 done.** Added `hardware/rtl/sr_core/sr_tile_core.v`, `hardware/rtl/common/tile_ram_split.v`, `hardware/verification/tb/{tb_sr_tile,tb_tile_ram_split}.v`, `software/ai/quantization/seam_test.py`, `hardware/vivado/scripts/synth_sr_tile_core.tcl`, second small golden tile `small12b`, `results/utilization/m5_*`. Findings: plain 4624x128 RAM costs 32 RAMB36 (power-of-two depth rounding) -> split RAM 18.5; wrong-default-parameter mutant first survived -> default-parameter check; my `pkill -f` killed my own shell (do not use). Final: 73 sim runs (full), 29 (quick), seam 20 + 4 tiles exact, netlist sim exact, 21 breakages caught, whole core 68 DSP / 70 BRAM / routed WNS +0.234 ns, 926,197 cycles per tile. Not committed yet. |
| 2026-10-04 | **Full re-audit M1-M5.** Re-ran everything from scratch: lint, M1/M2 data checks and tests, evaluations (baseline, FP32, INT8) reproduce results and qparams byte-identically, M3 tests + independent recompute, RTL `full` (73 runs) and netlist simulations: all exit 0. Code re-read from M1 to M5. Fixed: tile core `cycles` not reset and `out_last` undefined/high without `out_valid` (testbench check added and shown to catch the old behaviour); `docs/PROJECT_PLAN.md` early estimates now carry a dated measured-update box (plan said ~6 fps, simulated design is ~0.8 fps). Routed slack of the core re-measured: +0.234 ns (was +0.146 before the fix; placement noise ~0.1 ns, margin fragile). Not committed yet. |
