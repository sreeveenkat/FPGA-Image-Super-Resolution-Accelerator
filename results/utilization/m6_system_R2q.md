# R2q: INT8 weights of the re-parameterized + QAT network, in a sandbox build (branch `r2q`)

Status 2026-10-19: **built and simulated, NOT yet run on the board.** The deployed bitstream (0602), `qparams.npz` and the `main` branch are untouched;
`~/Desktop/venkat/TESTED_0602.bit` is the fallback. RTL change versus 0602: only the default `SHIFT1..4` of `sr_tile_core.v` (24/23/21/24 -> 22/22/21/22).
The VERSION register is unchanged (0x53520602), so the bitstream cannot be told apart by register: use the R2q golden tile (T1) and the R2q expected output (T2), see `docs/paper/board_checklist.md`.

## What R2q is
`software/ai/checkpoints/srnet_fp32.pt` in this branch = `rep_qat_s1` of the ladder (2 seeds, seed chosen on the 42 clean validation images), merged to the same
3x3/dw3x3/1x1/3x3 network, QAT with per-layer weight scales, `act_max` stored in the checkpoint (`quantize.py` now reads it). Exported with
`quantize.py` -> `export_rtl.py` -> `gen_unit_vectors.py`.
INT8 (integer model, PSNR-Y / SSIM-Y): Set5 35.84 / 0.9480, Set14 31.89 / 0.9003, BSD100 30.87 / 0.8806 (deployed R0: 35.02 / 31.40 / 30.53). Matches the ladder row `rep_qat_s1`.
The FP32 forward of the QAT weights (`model_fp32_x2.md`) is lower than their INT8 output (the weights are tuned for INT8): do not use that row as an "FP32 model".

## Parameters (SHIFT, M) and the requantizer product
| layer | SHIFT | M (all channels) | worst |acc*M|+rnd, sign-aware (bits) | limit |
|---|---|---|---|---|
| L1 | 22 | 49111 | 2.50e9 (32) | 49-bit signed in `requant.v` (2.8e14) |
| L2 | 22 | 64902 | 2.49e9 (32) | |
| L3 | 21 | 40454 | 4.60e9 (33) | |
| L4 | 22 | 35824 | 8.82e9 (34) | |
Accumulator worst case 13-15 bits of headroom in the 32-bit MAC (`results/quality/acc_range_R2q.txt`: theory A, theory B, observed, per layer).
Besides the analytic bound, `rq21..rq25` in `run_tests.sh` drive `requant.v` with accumulators up to +-2^31 times M up to 65535 (the full 32x16-bit range) at SHIFT 21, 22, 23, 24, 25: all pass.

## Verification (sandbox, all on the R2q weights)
| Check | Result |
|---|---|
| Python tests: test_baseline, test_model, test_integer (21), test_export, test_rep, test_anchor | all PASS (one threshold changed, see below) |
| `check_export_independent.py` (pure-Python recompute of all 11 golden tiles from the exported files) | ALL OK |
| `run_tests.sh quick` | 38/38 (was 36; two more requantizer shifts) |
| `run_tests.sh full` | 90/90 (was 88), all real-size tiles 926,201 cycles, seam 20 + 4 tiles bit-exact |
| default-SHIFT check of the core (`tb_sr_tile`) | PASS (defaults == `network_params.vh`) |
| C ARM-only model (T7 code, `test_swmodel.sh`) vs the integer model, 960x540 + 128x128 | byte-exact on the PC; R2q expected fnv1a32 0x2afbc9ae (960x540), 0x272bafbb (128x128 baboon) (deployed: 0xcf947f22) |
Changed test: `test_integer_model_close_to_fp32_on_real_image` required INT8 vs FP32 output > 42 dB (deployed PTQ: 48 dB); the QAT weights give 40.8 dB, threshold now 38 dB
(a broken quantizer is far lower; the exact layer-wise check against an independent float64 implementation is unchanged).
Post-synthesis netlist simulation (`run_postsynth.sh`, xsim, 2026-10-19): **5/5 PASS** on the R2q weights: layers 1-4 (small12 tile, re-run, reset-abort sweep) and the HC=6 tile core (2 tiles, abort sweep) are bit-exact.

## Build (Vivado 2024.1, `build_m6_system.tcl`, 2 jobs; about 7 min)
| | R2q | 0602 (deployed) |
|---|---|---|
| WNS / WHS at 100 MHz | **+0.671 / +0.020 ns** | +0.503 / +0.016 ns |
| failing endpoints | 0 of 23,882 | 0 |
| LUT / FF | 5,289 / 7,803 | 5,296 / 7,831 |
| BRAM tiles / DSP | 71.5 / 68 | 71.5 (72 est.) / 68 |
| power estimate (vectorless, low confidence) | 1.912 W | 1.913 W |
| .mem files read from the sandbox path (Synth 8-3876) | 12 of 12 | 12 of 12 |
0 CRITICAL WARNING in the synthesis/implementation run logs (the block-design creation prints the usual PS7 DDR-skew critical warnings of the board preset; same as before).
The timing difference is placement noise (the logic is identical apart from constants); do not read it as an improvement.
Artifacts (labelled R2q, outside the repo): `~/Desktop/venkat/R2q_artifacts/design_1_wrapper_R2q.{bit,xsa}` and `reports_R2q/`; project `~/Desktop/venkat/R2q_build/m6_sr_R2q`.
