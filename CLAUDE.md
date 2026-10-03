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
│   │   ├── dataset/  models/  training/  quantization/  evaluation/  scripts/  checkpoints/
│   ├── arm_driver/            ← C code for the Zynq ARM (Vitis, bare-metal)
│   └── host_tools/            ← PC helper scripts (png↔raw conversion, serial/JTAG helpers)
├── hardware/                  ← everything that becomes FPGA logic
│   ├── rtl/                   ← Verilog: common/ conv_engine/ sr_core/ axi_wrapper/ top/
│   ├── verification/          ← cocotb/ testbenches, vectors/, reference/ (golden model glue)
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
| M3 INT8 + integer model | no | **next — not started** (spec in HANDOFF.md section 8; M3 guide sketch corrected to VALID convs) |
| M4 Conv engine RTL | simulation only | not started |
| M5 Full network RTL | simulation only | not started |
| M6 AXI/DMA/ARM driver | yes | not started |
| M7 Benchmark + report | yes | not started |
| M8 Optional extensions | — | not started |

## 6. Measured results (fill in only real numbers)

| Item | Value |
|---|---|
| Bicubic x2 (PSNR RGB / SSIM RGB / PSNR Y / SSIM Y) | Set5: 31.79 / 0.9088 / 33.67 / 0.9303; Set14: 28.30 / 0.8426 / 30.32 / 0.8698; BSD100: 28.23 / 0.8299 / 29.56 / 0.8434 |
| Nearest x2 (same metrics) | Set5: 29.08 / 0.8783 / 30.86 / 0.9001; Set14: 26.72 / 0.8202 / 28.58 / 0.8464; BSD100: 27.10 / 0.8117 / 28.42 / 0.8251 |
| FP32 CNN x2 final (PSNR RGB / SSIM RGB / PSNR Y / SSIM Y) | Set5: 33.12 / 0.9244 / 35.21 / 0.9449; Set14: 29.29 / 0.8688 / 31.51 / 0.8975; BSD100: 29.24 / 0.8673 / 30.60 / 0.8785 (PSNR-Y gain over bicubic: +1.53 / +1.18 / +1.04 dB; wins 119/119) |
| INT8 integer model PSNR/SSIM | — |
| FPGA resources (LUT/FF/BRAM/DSP) | — |
| Time per frame / FPS | — |

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
- `requirements.txt` pins package versions. A git repo now exists INSIDE this folder (`git init` done 2026-10-03, branch main); checkpoints (14 KB each) are tracked, datasets/images/.venv ignored. First commit NOT made yet (waiting for user).

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
