# R3q: anchor network (plain 3x3 net + nearest-neighbour residual) with QAT, sandbox build (branch `r3q`, based on `r2q`)

Status 2026-10-19: **RTL changed, simulated, built; NOT yet run on the board.** Deployed bitstream 0602, `main` and the R2q sandbox are untouched
(`~/Desktop/venkat/TESTED_0602.bit` is the fallback). **VERSION register 0x53523201** (R3q; deployed R0 = 0x53520602, R2q = 0x53522201); this tree's driver (`VERSION & 0xFFFFFF00 == 0x53523200`) refuses the other bitstreams. The golden tile and the output checksum still prove the weights
(`docs/paper/board_checklist.md`).

## Network
`software/ai/checkpoints/srnet_fp32.pt` in this branch = `plainA_qat_s1` of the ladder (anchor, QAT with per-layer weight scales, `act_max` inside). SHIFT 22/22/21/25.
INT8 (integer model, PSNR-Y / SSIM-Y): Set5 36.20 / 0.9515, Set14 32.12 / 0.9035, BSD100 31.01 / 0.8833 (seed 1; the two-seed mean is 36.05 / 32.05 / 30.96, deployed R0 35.02 / 31.40 / 30.53, R2q seed 1 35.84 / 31.89 / 30.87).
Per-image, mean of both seeds, R3q beats R2q on 118 of 119 test images (+0.14 dB mean).

## RTL change (what the estimate in `docs/paper/anchor_hw_estimate.md` turned into)
Only layer 4 changes, and **no signed 9-bit residual is ever stored**: the requantizer adds the anchor pixel inside its rounding constant,
`floor((p + 2^(S-1) + a*2^S) / 2^S) = floor((p + 2^(S-1)) / 2^S) + a`, so the final clamp to 0..255 does the whole job
(`clamp(clamp_signed(res, -255..255) + a, 0, 255) == clamp(res + a, 0, 255)`, exhaustive proof in `test_anchor.py`). No extra adder, no extra pipeline stage, **no extra cycle**.
| File | Change |
|---|---|
| `common/requant.v` | params `ADD_EN`, input `add` (uint8): `rndx = RND | (add << SHIFT)` (disjoint bits: a concatenation); `ADD_EN = 0` synthesizes to the old logic |
| `conv_engine/conv_engine.v` | params `ANCHOR`, `ANC_W`, `ANC_OFF`, `AWA`; ports `anc_addr`, `anc_data` (24-bit RGB); a raster address generator (`anc_a`, `anc_x`) that steps with the written words, a 3:1 colour mux (`k >> 2`) feeding `add` |
| `sr_core/sr_tile_core.v` | param `ANCHOR` (default 1), `SHIFT4` default 25; ram0's read port is switched to the anchor address while the state is S_L4 (ram0 keeps the input tile after layer 1); `ANC_W = 70`, `ANC_OFF = 3` (halo) |
Why the data is stable: the anchor address follows `out_cnt`-like word counting, so it names the pixel whose 12 channels are being requantized; the previous pixel's word is written
within about 16 cycles of its requantization start, and the next pixel's requantization starts 144 cycles after the previous one (PERIOD of layer 4).

## Parameters and the requantizer product (R3q)
| layer | SHIFT | M | worst |acc*M|+rnd, sign-aware (bits) | limit |
|---|---|---|---|---|
| L1 | 22 | 49093 | 2.25e9 (32) | 49-bit signed (2.8e14); the anchor adds at most 255*2^25 = 8.6e9 |
| L2 | 22 | 54977 | 3.19e9 (32) | |
| L3 | 21 | 38064 | 3.85e9 (32) | |
| L4 | 25 | 52043 | 2.77e10 (35) | |
Accumulators: 11-15 bits of headroom in 32 bits, L4 the tightest (sign-aware worst case +-532k = 21 bits, observed +-73k); `results/quality/acc_range_R3q.txt`.

## Verification (all on the R3q weights and RTL)
| Check | Result |
|---|---|
| Python: test_baseline, test_model, test_integer (21), test_export (7), test_rep, test_anchor (clamp equivalence, halo-offset mutant, 8 QAT-vs-integer combinations, tiled == whole) | all PASS. Changed: tests that built a plain net or required unsigned layer ranges now honour the anchor flag; `test_export` additionally requires golden pixels where residual + centre < 0 and > 255 |
| `check_export_independent.py` (pure Python, two-step anchor definition, all 11 golden tiles) | ALL OK |
| `run_tests.sh quick` | 42/42 (R2q: 38): + requantizer add mode at SHIFT 21/22/25 (about 13,000 vectors each, acc up to +-2^31, M up to 65535, add 0..255 incl. 0/255/1/2/253/254), layer 4 anchor on `small12` and on a randomized non-square tile with the residual saturating at both ends (`randA4`), core default `ANCHOR`/`SHIFT` check |
| `run_tests.sh full` | **95/95**: all real-size tiles 926,201 cycles (unchanged), real-size seam test 4 tiles + HC=8 seam 20 tiles bit-exact (these also exercise the halo-aligned anchor read at tile borders), AXI wrapper and top at HC=64 |
| `mutate_anchor.py --seam` (inside `full`) | 26 deliberate defects (add ignored / shifted / subtracted / halved, rounding bit dropped, no saturation, halo offset 2 and 4, row step and row wrap off by one, wrong colour mapping, R/B swapped, address not restarted for the 2nd tile, address advancing per byte, ram0 port switched in the wrong state, wrong stride, no anchor data, wrong defaults): **all caught**; 1 equivalent mutant (`|` replaced by `+` on disjoint bits) correctly survives |
| C ARM model with the anchor (`sr_swmodel.c`, `SR_ANCHOR`), `test_swmodel.sh` | byte-exact vs the integer model on the PC: 960x540 fnv1a32 **0x45dd4e2d**, 128x128 baboon 0xa1d2f75c |
Post-synthesis netlist simulation (`run_postsynth.sh`, xsim, 2026-10-19): **5/5 PASS** on the R3q weights: layers 1-4 (layer 4 synthesized with ANCHOR=1, checked against the anchored golden tile, re-run and reset-abort sweep) and the HC=6 tile core are bit-exact. The synthesis scripts `synth_conv_engine.tcl` / `synth_sr_tile_core.tcl` now pass the anchor generics when `network_params.vh` has `NET_ANCHOR = 1`.

## Build (Vivado 2024.1, `build_m6_system.tcl`, 2 jobs; about 7 min)
| | R3q | R2q | 0602 |
|---|---|---|---|
| WNS / WHS at 100 MHz | **+0.683 / +0.028 ns** | +0.944 / +0.019 | +0.503 / +0.016 |
| failing endpoints | 0 of 24,028 | 0 of 23,882 | 0 |
| LUT / FF (whole system) | 5,323 / 7,869 | 5,287 / 7,803 | 5,296 / 7,831 |
| accelerator `sr_accel_top_0` LUT / FF | 2,162 / 3,743 | 2,129 / 3,677 | - |
| BRAM tiles / DSP | 71.5 / 68 | 71.5 / 68 | 71.5 / 68 |
| power estimate (vectorless, low confidence) | 1.916 W | 1.910 W | 1.913 W |
| .mem files read from the sandbox path | 12 of 12 | 12 of 12 | 12 of 12 |
**Measured anchor cost (R3q - R2q, whole accelerator): +33 to +45 LUT (two builds each), +66 FF, 0 DSP, 0 BRAM** (layer-4 engine +31 LUT / +42 FF, core +8 LUT for the ram0 address mux, rest placement noise);
the estimate before the build was 80-120 LUT / 60-70 FF. Critical path is still ram2 -> MAC input of layer 3 (not the anchor path). Slack differences of +-0.2 ns between builds
are placement noise. 0 CRITICAL WARNING in the synthesis/implementation run logs.
The first R3q build (VERSION 0x53520602: WNS +0.490 / WHS +0.018 ns, 5,334 LUT, 7,869 FF, 1.914 W) was superseded on 2026-10-19 by the build in the first column; its files are in `R3q_artifacts/superseded_VERSION0602/`. **Anchor enabled, confirmed in the full-system synthesis log** (`design_1_sr_accel_top_0_0_synth_1/runme.log`, both builds): `Parameter ANCHOR bound to: 1`, `ANC_W 70`, `ANC_OFF 3` on the layer-4 `conv_engine` and `ADD_EN bound to: 1` on its requantizer (the other three requantizers: `ADD_EN 0`).
Artifacts (labelled R3q, outside the repo): `~/Desktop/venkat/R3q_artifacts/design_1_wrapper_R3q.{bit,xsa}`, `reports_R3q/`; project `~/Desktop/venkat/R3q_build/m6_sr_R3q_v3201`.
