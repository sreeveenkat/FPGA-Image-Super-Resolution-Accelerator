# HANDOFF — read this first in a new session

Last updated: 2026-10-04 (M4 done, not yet committed at the time of writing; check `git status`). Everything needed to continue the project without the previous conversation.
Companion files: `CLAUDE.md` (running log of decisions/results), `README.md` (public overview), `docs/milestones/` (step-by-step guides).

---

## 1. One-paragraph summary

FPGA image **super-resolution** accelerator for a **ZedBoard (Zynq XC7Z020-CLG484)**. A tiny INT8 CNN (2,620 parameters) upscales
**960×540 → 1920×1080 (×2)**. Trained on a PC (PyTorch), quantized to INT8, then to be implemented as a Verilog tile engine on the FPGA,
controlled by bare-metal ARM C code over AXI-Lite + AXI DMA. 4K was dropped (220 DSPs is too few). Input is plain RGB. The original idea
(FPGA ray tracer + 4K reconstruction) lives in `docs/resources/*.md` and is only an optional extension (M8).

## 2. Current state (exact)

| Milestone | Status |
|---|---|
| M0 Zynq basics (UART, AXI GPIO, own AXI-Lite IP, DMA loopback) | **not started — owner has no ZedBoard yet** (will borrow from college) |
| M1 Bicubic baseline, metrics, datasets | **DONE and hardened** |
| M2 FP32 CNN training/eval | **DONE and hardened** |
| M3 INT8 quantization + integer Python golden model | **DONE 2026-10-04** (results in section 8) |
| M4 conv engine RTL (simulation + synthesis) | **DONE 2026-10-04** (results in section 8) |
| **M5 full network RTL** (simulation only, Icarus) | **NEXT — not started**, no board needed |
| M6–M7 AXI/DMA/ARM driver, benchmark | planned, board needed |
| M8 optional extensions | optional |

Frozen artifact: `software/ai/checkpoints/srnet_fp32.pt` (sha256 starts `f1ae81f706ad3707`). **Do not retrain or overwrite it during M3.**

### Measured results (x2, Y-channel PSNR with 2-px shave; the numbers to quote)
| Set | Bicubic | FP32 CNN | Gain | SSIM-Y bicubic → CNN |
|---|---|---|---|---|
| Set5 (5) | 33.67 | 35.21 | +1.53 dB | 0.9303 → 0.9449 |
| Set14 (14) | 30.32 | 31.51 | +1.18 dB | 0.8698 → 0.8975 |
| BSD100 (100) | 29.56 | 30.60 | +1.04 dB | 0.8434 → 0.8785 |

Wins on 119/119 images (worst +0.46 dB). Seed-to-seed spread 0.03–0.09 dB → quote "about +1.0 to +1.5 dB, ±0.1".
960×540→1080p works on CPU in ~0.1 s; 135 tiles (64×64 core + 3 px halo) equal the whole-image output to 6.6e-7 (float rounding only).
INT8 (PTQ) is measured: mean PSNR-Y drop 0.18 / 0.11 / 0.08 dB on Set5 / Set14 / BSD100 (section 8). Nothing about hardware, resources, timing or fps has been measured yet — do not claim any.

## 3. The network and conventions (all decided, do not change casually)

```
input RGB uint8 (replicate-padded by 3 px)
 → Conv3×3 3→16 + ReLU → Depthwise3×3 16 + ReLU → Conv1×1 16→16 + ReLU → Conv3×3 16→12 → PixelShuffle(2) → RGB uint8 2H×2W
```
* Code: `software/ai/models/srnet.py` (`SRNet`, `HALO=3`, `predict_full`). 2,620 params, 2,560 MACs per input pixel.
* **All convolutions are VALID (no padding).** Input carries a 3-px border: replicate-padding for whole images, real neighbours for tiles.
* Tile plan for hardware: 64×64 core + 3 px halo = 70×70 in → 68 → 66 → 66 → 64 (12 ch) → shuffle → 128×128 out. 960×540 pads to 960×576 → 15×9 = 135 tiles.
* PixelShuffle channel order `k = 4·c + 2·dy + dx` (PyTorch). Pixel values are `x/255` in training.
* Reference chain: **PyTorch FP32 → NumPy integer model (golden) → RTL.** RTL is compared with the integer model, bit-exact, never with PyTorch.
* Colour convention: RGB uint8 everywhere in Python (OpenCV loads BGR; loaders in `dataset/pairs.py` convert).
* LR protocol: modcrop HR to even sides, then **Pillow BICUBIC** downscale (bit-exact with the official Set5/Set14 LR files for even-sized images; odd-sized images are re-aligned on purpose).
* SSIM = Gaussian 11×11, σ=1.5 (paper definition). "Y" = BT.601 luma, 2-px border shaved.
* INT8 plan: uint8 activations, int8 symmetric weights, int32 accumulators, requantize `(acc·M + 2^(SHIFT-1)) >> SHIFT`, clamp.

## 4. Repository map

```
HANDOFF.md  CLAUDE.md  README.md  requirements.txt  .gitignore
docs/PROJECT_PLAN.md  docs/milestones/{README,M0..M8}.md  docs/resources/*.md (+ papers/ PDFs, NOT in git)
software/ai/dataset/     pairs.py (load/save/LR protocol), check_dataset.py, check_lr_protocol.py
software/ai/models/      srnet.py
software/ai/training/    train.py
software/ai/evaluation/  metrics.py eval_baseline.py eval_model.py border_effect.py check_target_res.py test_baseline.py test_model.py
software/ai/quantization/  quantize.py integer_reference.py export_rtl.py qparams.npz test_integer.py test_export.py   (M3; evaluation/eval_int8.py is the INT8 evaluator)
software/ai/scripts/     fetch_div2k_subset.sh
software/ai/checkpoints/ srnet_fp32.pt (FINAL), *_v1.pt (old 55-img model), exp/ (ablation runs A–D, seed 1)
software/arm_driver/  software/host_tools/   (empty, later)
hardware/rtl/weights/ (M3 export: weights/wrom/bias/mult *.mem, network_params.vh, README = formats)  hardware/rtl/common/{mac_unit,requant,tile_ram,weight_rom}.v  hardware/rtl/conv_engine/conv_engine.v (M4)  hardware/verification/{run_tests.sh, tb/*.v}  hardware/vivado/scripts/synth_conv_engine.tcl  (empty so far: rtl/{sr_core,axi_wrapper,top}, verification/{cocotb,vectors,reference}, vivado/constraints)  results/utilization/ (M4 reports)
data/ (git-ignored: train/HR 192 DIV2K imgs, test/HR + test/LR + test/LR_official for Set5/Set14/BSD100, golden/)   data/README.md = sources + name map
results/quality/ (tracked: baseline_x2.*, model_fp32_x2.*, m2_training_summary.md, training_curves.png)   results/images/ (git-ignored, regenerable)
```
Rules: no Python in `hardware/` except cocotb tests; no Verilog in `software/`; generated files never committed; keep `CLAUDE.md` updated after every change.

## 5. Environment

* Machine: Dell G15, Ubuntu 24.04, kernel 7.0.0-34, 16 CPU threads, 15 GB RAM. Project folder: `/home/sreevenkat/Desktop/venkat/sem_project_all`.
* Python 3.12. Use **`.venv/bin/python`** from the project root. The venv was created with `--system-site-packages` (numpy, opencv, matplotlib, pillow and **torch 2.12.0+cu130** come from the system; only scikit-image and pyflakes are installed inside the venv). Pinned versions: `requirements.txt`.
* **GPU works** (RTX 3050 6GB, driver 595.91.07, `torch.cuda.is_available()` True). Fixed on 2026-10-03 by installing the prebuilt module `linux-modules-nvidia-595-server-open-7.0.0-34-generic`. `train.py` is CPU-only (no `--device` flag). GPU convs use TF32 (≈1e-4 forward difference vs CPU) — irrelevant for the integer model.
* **FPGA tools (verified 2026-10-03):** Vivado, Vitis and Vitis HLS **2024.1** are installed under `~/Desktop/vivado_install/{Vivado,Vitis,Vitis_HLS}/2024.1/` (binaries `…/Vivado/2024.1/bin/vivado`, `…/Vitis/2024.1/bin/{vitis,xsct}`; source `settings64.sh` in each to put them on PATH). Icarus Verilog 12.0 is installed (`/usr/bin/iverilog`, `vvp`). **Not installed:** cocotb, Verilator, GTKWave, Yosys (not needed: the M4 testbenches are plain Verilog run with Icarus; cocotb is optional).
* **ZedBoard board files are NOT installed** (Vivado's `data/boards/board_files` does not exist). For M0 either install Digilent's board files (github.com/Digilent/vivado-boards) or create the project for part `xc7z020clg484-1` and configure the Zynq PS manually/with the ZedBoard preset.
* `~/Desktop/VITIS_WORKSPACE/` already contains `hello_world`, `zynq_platform`, `logs` (from earlier work, board and status **unverified** — look before redoing M0 step 1). Home also holds Vivado logs from a session on 2026-10-03; the owner's earlier designs (RISC-V, posit/FP32 MACs) live in folders on `~/Desktop/`.
* `pip install` from PyPI is slow/flaky here: run it in the background (`nohup … &`) and poll. The shell blocks long `sleep`; wait with `until <cond>; do sleep 5; done` (use `run_in_background` for long waits).
* Never `pkill -f "<text>"` from the same command line (it matches and kills its own shell).
* `sudo` needs the owner's password: Claude cannot run it. Ask the owner to run commands with the `!` prefix in the prompt.

## 6. GitHub (everything needed)

* Account: **sreeveenkat**. Repo: `https://github.com/sreeveenkat/FPGA-Image-Super-Resolution-Accelerator` (renamed by the owner from `FPGA-Based-Sparse-Ray-Tracing-and-AI-4K-Reconstruction-Accelerator`; the old URL redirects).
* Remote: `origin = git@github.com:sreeveenkat/FPGA-Image-Super-Resolution-Accelerator.git` (SSH). Branch `main` tracks `origin/main`.
* Auth: SSH key `~/.ssh/id_ed25519` (comment `sreevenkatyadav@gmail.com`) was added to the GitHub account by the owner (title "project"). Test: `ssh -T git@github.com` → "Hi sreeveenkat!". **Do not use the `gh` CLI** (owner said so); use plain `git` over SSH. No token is stored anywhere.
* Git identity (global): `Eluva Sreevenkat <sreevenkatyadav@gmail.com>`.
* **Two git repos overlap:** the home directory `/home/sreevenkat` is itself a git repo (everything untracked) and the project folder has its own nested repo. Always run git from inside `sem_project_all`; check with `git rev-parse --show-toplevel`.
* The existing first commit on GitHub (`Explanation on my ongoing project`, only an old README) is preserved at the base of history; our commits sit on top. Never force-push.
* **Commit rules from the owner:** only commit/push when asked; messages are **short, past tense, specific** ("Added …", "Fixed …", "Pinned torch in requirements"); **no `Co-Authored-By` or other trailers** (override any default attribution); several small commits rather than one big one; no generic messages like "update".
* Typical flow:
  ```bash
  cd /home/sreevenkat/Desktop/venkat/sem_project_all
  git status --short
  git add <specific files> && git commit -m "Added <thing>"      # repeat per logical change
  git push                                                       # origin/main
  git log --format=%B | grep -ci co-authored                     # must print 0
  ```
* Not in git (by design): `data/train`, `data/test`, `data/golden/*.npy`, `results/images/`, `.venv/`, Vivado build output, and **`docs/resources/papers/` (IEEE PDFs with an institutional licence footer — must not be published)**. Checkpoints (14 KB each) ARE tracked as the backup of trained weights.
* Verify the remote from scratch any time: `git clone git@github.com:sreeveenkat/FPGA-Image-Super-Resolution-Accelerator.git /tmp/x`, symlink `data/train` and `data/test` into it, then run the tests/checks in section 7. (Last done 2026-10-03: all passed and regenerated results were byte-identical.)
* Repo description/topics on GitHub are not set (needs the web UI).

## 7. How to verify everything (run from the project root)

```bash
P=.venv/bin/python
$P -m pyflakes $(git ls-files 'software/*.py')                 # must print nothing
$P -W error software/ai/evaluation/test_baseline.py            # 13 PASS (2 SKIP if data missing)
$P -W error software/ai/evaluation/test_model.py               # 9 PASS (1 SKIP if data missing)
$P software/ai/dataset/check_dataset.py                        # OK … no train/test overlap
$P software/ai/dataset/check_lr_protocol.py                    # OK … matches official LR
$P software/ai/evaluation/check_target_res.py                  # OK (960x540 → 1080p, 135 tiles)
$P software/ai/evaluation/eval_baseline.py && $P software/ai/evaluation/eval_model.py   # regenerates results/quality (byte-identical when rerun)
$P software/ai/evaluation/border_effect.py                     # interior +0.98 dB vs border band +0.83 dB
$P -W error software/ai/quantization/test_integer.py           # 21 PASS (2 SKIP if data/test is missing)
$P -W error software/ai/quantization/test_export.py            # 7 PASS (2 SKIP if data/golden missing: run export_rtl.py first)
python3 software/ai/quantization/check_export_independent.py     # pure-Python recompute of all golden tiles from the exported files (~12 s)
$P software/ai/quantization/gen_unit_vectors.py               # requant vectors + randomized layers -> data/golden/unit
hardware/verification/run_tests.sh quick                       # RTL regression, ~30 s, must end with '25 test runs passed, 0 failed' (full: 57, ~5 min)
hardware/verification/run_postsynth.sh                         # xsim on the synthesized netlists (Vivado needed, ~1 min): '4 passed, 0 failed'
$P software/ai/evaluation/eval_int8.py                         # regenerates results/quality/model_int8_x2.* (byte-identical, ~5 min)
```
**Rebuilding data on a new machine:** `software/ai/scripts/fetch_div2k_subset.sh 192` (DIV2K subset from the Hugging Face mirror `ScooterTaylor/DIV2K_captioned_subset`, files img0193–img0384; train = first 180, validation = last 12).
Benchmarks: `https://huggingface.co/datasets/eugenesiow/{Set5,Set14,BSD100}/resolve/main/data/{SetN}_HR.tar.gz` and `…_LR_x2.tar.gz` (extract to `data/test/HR/<set>/` and `data/test/LR_official/<set>/`; files keep their original names). Then run `eval_baseline.py` to create `data/test/LR/`.
Retrain the final model: `.venv/bin/python software/ai/training/train.py --epochs 100 --steps 500 --images 192 --val 12 --threads 4 --out software/ai/checkpoints/srnet_fp32.pt` (statistically, not bit-for-bit, reproducible).
All 18 deliberate-breakage ("mutation") checks were caught by the test suite on 2026-10-03; when adding code, add tests that would catch a wrong constant/order/rounding.

## 8. M3 and M4 results (DONE) and NEXT TASK: M5

**What M3 produced** (details: `docs/milestones/M3_int8_quantization.md` section 4, `CLAUDE.md` section 6d):
* `software/ai/quantization/integer_reference.py` = THE golden model (pure NumPy integers): `upscale(net, lr)`, `upscale_tiled`, `run_tile(net, tile70x70x3 -> 128x128x3)`, `forward_layers` (all intermediate layers). Params in `qparams.npz`.
* Arithmetic (the RTL must match bit for bit): `acc = bias + sum(uint8 * int8)`; `y = clamp((acc*M[co] + 2^(SHIFT-1)) >> SHIFT, 0, 255)` (arithmetic shift, round half up); L1..L4 SHIFT = 24, 23, 21, 24; M is uint16 per output channel (all channels of a layer currently share one value); biases int32; weights int8 in [-127, 127]; `acc` fits int32, `acc*M` needs ~40 bits.
* Exports for the RTL in `hardware/rtl/weights/` (`weights_Ln.mem` order `[co][ci][ky][kx]`, `bias_Ln.mem`, `mult_Ln.mem`, `network_params.vh`, README). Golden tiles in `data/golden/` (git-ignored; run `export_rtl.py` to regenerate): zeros, full255, noise, pixel, ramp, small12 (12x12 -> 12x12), real0-2, real_corner; each has `.npz` and byte-per-line `.hex` files for every layer (`[y][x][c]`).
* Quality: PSNR-Y FP32 -> INT8: Set5 35.21 -> 35.02, Set14 31.51 -> 31.40, BSD100 30.60 -> 30.53 (worst image -0.41 dB); still beats bicubic on 119/119.
* Quantization choices were made on the 12 validation images only (99.99th percentile, per-layer weights). If the FP32 checkpoint ever changes, redo `eval_int8.py --sweep`, `quantize.py`, `export_rtl.py` and all tests.
* Not done on purpose: no `torch.ao` quantized model (not our reference); no QAT (drop already < 0.3 dB).

**M4 result (DONE, re-audited)** (details: `docs/milestones/M4_conv_engine_rtl.md` section 4b, `results/utilization/m4_conv_engine.md`, `CLAUDE.md` section 6e):
* `conv_engine` = one layer, one instance per layer, VALID conv, memories outside (read port 1-cycle latency, write port), compile-time params `C_IN,C_OUT,K,DEPTHWISE,IN_W,IN_H,SHIFT` + `wrom/bias/mult` files. Interface: `rst` (sync; one cycle is enough), `start` pulse, `busy`, `done` pulse, `cycles`; can be restarted right after `done`. Bit-exact with the golden model on all 4 layers x 10 golden tiles and on randomized layers (distinct M per channel, non-square), and the synthesized netlists are bit-exact too (small tile). Cycles per output pixel 27 / 16 / 16 / 144; per 64x64 tile 124,871 / 69,712 / 69,719 / 589,843 (sum 854,145 = ~1.15 s per frame at 100 MHz for 135 tiles, SIMULATED compute only).
* Place and route (out-of-context, one engine at a time): 347-397 LUT, 692-952 FF, 14-18 DSP, 0-2 BRAM per layer; 68 DSP total for four instances; routed WNS at 100 MHz +0.135 (L1) / +0.261 / +0.582 / +0.698 ns; critical path: requantizer feed (register the result mux to gain margin).
* **Memory finding for M5:** a 70x70x128-bit `tile_ram` infers 32 RAMB36 (23 % of the chip). Two ping-pong buffers = 64 of 140. Plan the activation memory before wiring (e.g. one buffer per boundary only where needed, narrower/other word organisation, or smaller tile).
* Traps already hit (do not repeat): ROM layout built in an `initial` loop is ignored by Vivado (use the exporter's `wrom_Ln.mem` + `$readmemh`); small multipliers need `(* use_dsp = "yes" *)`; TB stimulus must be driven on the falling edge; netlist simulation must wait for `glbl.GSR`; Vivado keeps `*.backup.log` files (do not glob `L*.log`); check `grep 8-311` and the DSP count after every synthesis.
* Verification commands: `hardware/verification/run_tests.sh quick|full` (25 / 57 runs), `hardware/verification/run_postsynth.sh` (4 netlists, ~1 min, needs the `small` netlists: it generates them if missing), `software/ai/quantization/gen_unit_vectors.py` first on a fresh clone (the runner does it automatically).
* Layers were tested one at a time on GOLDEN inputs. Chaining them is the M5 job. Not covered: full 70x70 netlist simulation, board behaviour, I/O timing.

**NEXT: M5 — full network in RTL** (guide: `docs/milestones/M5_full_network_rtl.md`). Suggested order:
1. `sr_tile_core.v`: four `conv_engine` instances (L1 70x70 -> L2 68x68 -> L3 66x66 -> L4 66x66 -> 64x64 out) with activation RAMs between them (`tile_ram`: word widths 24 / 128 / 128 / 128 / 96 bits; the RAMs can be shared ping-pong A/B as in the guide, or one RAM per boundary first for simplicity) and a layer sequencer that pulses `start` of the next engine on `done` of the previous one. Compare EVERY intermediate RAM with `data/golden/<tile>_Ln.hex` (same hex format, `[y][x][c]`).
2. Pixel shuffle + output packer: `out(2y+dy, 2x+dx, c) = L4[4c+2dy+dx](y,x)`, raster RGB bytes of the 128x128 tile; compare with `<tile>_out.hex`.
3. Input loader (stream of 70x70x3 bytes into the L1 input RAM) and output stream; then the seam test (tiled == whole image, bit-exact), border tiles (`real_corner`), and a cycle count per tile (expect about 854 k + chaining overhead).
4. Synthesize the whole core (`synth_conv_engine.tcl` is per-layer; write a core script), check DSP (68 expected from engines), BRAM (activation buffers are the big item: ONE 70x70x128-bit buffer is 32 RAMB36 as measured), timing.
Open design question for M5: keep four engines (68 DSP, simplest) or share one engine with runtime config (fewer DSPs, more control logic). Four engines is the suggested start. Do not start M6 before the M5 checklist is ticked.

## 9. Known caveats / honest limits

* Fine random texture (gravel, fur, fabric) is not recovered by a 2.6 K-parameter net; this is expected.
* Edge band (outer 8 px) gains ~0.15 dB less than the interior; edge-aware training did not fix it; ignore.
* SSIM loss, 24 channels and edge-window sampling gave no meaningful gain over plain L1/16 ch (all within noise) — kept the simplest.
* Y-PSNR uses float BT.601 (not MATLAB's 8-bit rounding) → can differ ~0.1 dB from some papers (e.g. our Set14 bicubic 30.32 vs 30.24 published).
* `--edge-aug` in `train.py` is correct but slow (re-pads per sample); only used in a rejected experiment.
* All speed/fps figures for hardware (≈1 fps first version, 5–10 fps optimized) are estimates, not measurements.
* Papers verified against the PDFs: WRTX (Virtex-4, 48 MHz, ~1.3 M rays/s); NIT Calicut QFSRCNN (ZCU104, 214.53 MHz, 24.12 fps for 1080p→4K ×2, 6,065 params, 1,114 DSPs); URSI 2024 Zynq SRCNN (HLS; its "4.35 ns" processing time is not an end-to-end latency — treat with scepticism).

## 10. How the owner likes to work (keep doing this)

* Beginner-friendly explanations: say what a step is, why it exists and what output it produces. The owner knows Verilog (RISC-V project, PL-only) but is new to Zynq PS/PL, AXI/DMA, CNN hardware and PyTorch quantization.
* **Brutal honesty:** report what is verified vs assumed; admit mistakes; no overclaiming. When asked "is it done?", list the real gaps. Verify claims by running things (tests, mutation checks, clean-clone reruns) rather than asserting.
* Tidy structure; software / hardware / data / docs kept separate; every change recorded in `CLAUDE.md`.
* Do PC-only work first (M3, then RTL simulation) because the board is not available yet.
* Ask before anything outward-facing or destructive; commit/push only on request.

## 11. First steps in a new session

1. `cd /home/sreevenkat/Desktop/venkat/sem_project_all && git status -sb && git log --oneline | head -5`
2. Read this file, then `CLAUDE.md` sections 5, 6, 8.
3. Run the checks in section 7 (about 3 minutes) to confirm the environment still works.
4. Start M5 per section 8 (or ask the owner if the board has arrived, which would unlock M0). Check `git status` first: M4 files may still be uncommitted.
