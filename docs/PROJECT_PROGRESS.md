# Project progress: what we want to do, what we have done, where we are

Written 2026-10-19 from the local project notes (not in the repository), `README.md`, `docs/STATUS.md` and `docs/paper/*`. Every number points to a measured file; estimates and predictions are marked as such.

---

## 1. What we want to do (the goal)

Build an **FPGA image super-resolution accelerator** on a **ZedBoard (Zynq XC7Z020)**:

* A small INT8 CNN (2,620 parameters) upscales **960x540 to 1920x1080 (x2)**.
* It is trained on the PC (PyTorch), quantized to INT8, and run by a Verilog tile engine in the FPGA fabric (PL).
* An ARM bare-metal C program (PS) controls it over AXI-Lite and moves image tiles with AXI DMA.
* The output must match a software integer model **bit for bit**.
* The original idea (sparse ray tracing + 4K reconstruction) was dropped: 220 DSPs are too few for 4K. A ray-traced front end stays an optional extension (M8).

Longer-term goals now:

1. **Better image quality** with the same hardware shape (the "ladder": R2q, R3q).
2. **Higher speed** (today 0.76 fps; a redesign is predicted to reach about 2-4 fps, not built).
3. **A conference paper** about the measured design, the utilization-gap analysis and the verification flow.

---

## 2. Milestones: what is finished

| Milestone | What | Status | Key result |
|---|---|---|---|
| M0 | Zynq basics (UART, GPIO, own AXI-Lite IP, DMA loopback) | **Done** 2026-10-11, on the board | `docs/milestones/M0_lab_record.md` |
| M1 | Bicubic baseline, metrics, datasets | **Done**, hardened | Bicubic PSNR-Y Set5/Set14/BSD100: 33.67 / 30.32 / 29.56 dB |
| M2 | Train the FP32 CNN | **Done**, hardened | 35.21 / 31.51 / 30.60 dB; better than bicubic on 119/119 images |
| M3 | INT8 quantization + integer golden model | **Done** 2026-10-04 | 35.02 / 31.40 / 30.53 dB (drop 0.08-0.18 dB); tiled equals whole image exactly |
| M4 | Convolution engine in RTL | **Done** 2026-10-04 (simulation + synthesis) | All 4 layers bit-exact; 32 deliberate RTL breakages caught |
| M5 | Full network RTL (tile core) | **Done** 2026-10-04 (simulation + synthesis) | 926,201 cycles per 64x64 tile; seam test exact; 21 breakages caught |
| M6 | AXI wrapper, DMA, ARM driver, on the board | **Done** 2026-10-11 (0602 build 2026-10-12) | Byte-exact 960x540 frame on the board; 8,000-tile stress test with 0 errors |
| M7 | Benchmark + report | **4 of 5** | Tables A-D measured; report PDF is outdated, LaTeX source not found |
| M8 | Optional extensions (HDMI, x4, ray tracing...) | Not started | |

### The deployed design (R0, bitstream 0602, VERSION 0x53520602), measured on the board

| Item | Value | Source |
|---|---|---|
| Frame time, 960x540 to 1080p, mean of 20 frames | **1,311.9 ms = 0.762 fps** | `results/speed/m7_timing_20frames.md` |
| Correctness | **119 of 119** test images byte-exact against the integer model | `results/quality/table_a_x2.md` |
| Resources (whole system, routed) | 5,296 LUT, 7,831 FF, 72 BRAM, 68 DSP | `results/utilization/m6_system_0602.md` |
| Timing at 100 MHz | Met: WNS +0.503 ns, WHS +0.016 ns | same file |
| Power | 1.913 W, a Vivado **estimate** (confidence Low), not measured | `results/utilization/m7_power.md` |
| Robustness | 2 x 1,000 tiles without error; 50 fresh loads; error recovery 10/10 | `m6_system_0602.md` |

Verification chain: PyTorch FP32, then the NumPy integer model (golden), then RTL (Icarus, xsim, synthesized netlists), then the board. RTL and board are compared bit for bit with the integer model, never with PyTorch.

Regressions on `main`: `run_tests.sh quick` 36/36, `full` 88/88.

---

## 3. What we are doing now

### 3a. Image-quality ladder (software done 2026-10-18)

Same network shape, better weights. Two candidates beat the deployed one in the integer model (INT8 PSNR-Y, 2-seed means, Set5 / Set14 / BSD100):

| Rung | What | PSNR-Y (dB) | RTL change? |
|---|---|---|---|
| R0 (2-seed mean: deployed + a retrain) | baseline | 34.93 / 31.35 / 30.48 (the deployed checkpoint alone: 35.02 / 31.40 / 30.53) | none |
| R2q | re-parameterized blocks + quantization-aware training | 35.79 / 31.85 / 30.83 | none (only SHIFT constants) |
| R3q | plain net + nearest-neighbour anchor + QAT | 36.05 / 32.05 / 30.96 | small (anchor) |

* R3q beats R2q by +0.13 to +0.26 dB, more than the seed spread; it wins on 118 of 119 images.
* Settings were chosen on 42 clean validation images only. The train/test overlap check found no overlap.

### 3b. R2q and R3q sandboxes (2026-10-19, PC side done)

Two git worktrees (local, not pushed): `~/Desktop/venkat/sandbox_R2q` (branch `r2q`) and `~/Desktop/venkat/sandbox_R3q` (branch `r3q`). `main`, the deployed checkpoint, `qparams.npz` and `hardware/` are untouched.

| Check | R2q | R3q |
|---|---|---|
| `run_tests.sh full` | 90/90 | 95/95 (26 anchor mutants all caught) |
| Post-synthesis netlist simulation | 5/5 | 5/5 |
| Vivado, 100 MHz | WNS +0.944 ns, 5,287 LUT | WNS +0.683 ns, 5,323 LUT |
| VERSION register | 0x53522201 | 0x53523201 |
| Expected 960x540 checksum (fnv1a32) | 0x2afbc9ae | 0x45dd4e2d |

The anchor costs +33 to +45 LUT, +66 FF, 0 DSP, 0 BRAM and no extra cycles (measured by synthesis; the earlier estimate was about 100 LUT). **Nothing of R2q or R3q has run on the board.**

### 3c. Speed analysis (model only, nothing built)

* The design keeps only **17.2 %** of its 68 DSPs busy, because only one of the four layer engines works at a time.
* Predictions (`docs/paper/cycle_model.md`): a line-buffer layer pipeline at 68 DSP gives about 3.9 fps at 100 MHz; one shared engine gives 2.2 / 2.8 fps at 100 MHz (I/O as today / overlapped).
* **150 MHz does not close timing today:** the unchanged design at 152.38 MHz had WNS -1.693 ns. The worst path is activation RAM, split-RAM mux, MAC DSP input. A pipeline register is the obvious fix. The raw reports of this trial were not saved.

### 3d. Paper preparation

* Done: cycle model, PC baseline (GPU 7.9 ms per frame, CPU about 100-130 ms), novelty search, venue shortlist, ARM-only baseline code (T7).
* Finding: the layer pipeline and bit-exact golden verification are **not new ideas** (existing work found). Plausible contributions: measured utilization gap on a low-cost Zynq, mutation-tested RTL with board-level byte-exactness, energy against the on-chip ARM and a GPU.
* Deadlines: ISCAS 2027 on 22 Oct 2026 and ARC 2027 on 25 Oct 2026 (both tight); FPL, GLSVLSI and VDAT 2027 are expected around March-April 2027 (not announced).
* Mutation study run 2026-10-24: 20 RTL mutants, all caught by the quick suite, no survivors (`docs/paper/mutation_study.md`). Simulation only.

---

## 4. Where it stopped (exact point)

Completed up to here:

* Everything on the PC side for R0, R2q and R3q: training, quantization, RTL, simulation, netlist simulation, Vivado builds, ARM ELFs, expected checksums.
* The board checklist is written and ready: `docs/paper/board_checklist.md`.

**Not done, in order (the NEXT step is the first row):**

| # | Step | Needs |
|---|---|---|
| 1 | Re-run T1/T2 on R0 (main.c changed on 2026-10-16) | board + owner |
| 2 | T7: run the ARM-only baseline (never run on the board) | board |
| 3 | R2q on the board: T1, T2, negative controls, 20-frame timing, optionally 119 images | board |
| 4 | Power measurement with a meter (P0, P1, P2, P3 states; replaces the 1.91 W estimate) | board + power meter |
| 5 | R3q on the board (only after R2q passes) | board |
| 6 | Apply the merge criteria and decide which branch goes into `main` | owner decision |

Proposed merge criteria (the owner confirms): byte-exact T1/T2 and 119/119; 20-frame mean within +-2 ms of 1,311.9 ms; max - min <= 3 ms; CYCLES per tile 926,210-926,241; 100 MHz timing met.

Other open items:

* Report PDF outdated (LaTeX source missing); the README should be updated after the board results.
* Choose paper venue and deadline.
* Repeat the 150 MHz trial and keep its reports; a pipelining change is needed before any 125/150 MHz claim.
* Commit pending files: 7 modified docs/scripts, plus `timing_150mhz.md`, `mutation_study.py` and the Demo Run Sheet PDF. The PDF names a person in its byline, so check it before committing.
* Add the MIT license (decided, not added).

---

## 5. Honest limits

* 0.76 fps is not real time: the layer engines run one after another, and tile load, compute and output are not overlapped.
* Power is an estimate; 82 % of it is the ARM side.
* Two single first-tile failures seen on 2026-10-11 are still unexplained; none occurred in thousands of tiles after the PL-isolation fix.
* Images go in and out over JTAG, not from an SD card or a video input.
* No speed or energy comparison with a CPU/GPU exists on the board side yet (PC side measured only).
* The 2-seed means describe the training recipe; the sandboxes build one seed (seed 1).
* Fine random texture (gravel, fur, fabric) is not recovered by a 2,620-parameter network.

## 6. Standing rules

* Kill background jobs by PID only; never `pkill -f`.
* Choose settings on the 42 validation images only.
* Do not touch the deployed checkpoint, `qparams.npz` or `hardware/` without the owner.
* Commit only when asked, short past-tense messages, **no trailers**, no `gh`.
* Never symlink `hardware/` or `data/` into a Vivado project.
* Never claim a number that was not measured.
