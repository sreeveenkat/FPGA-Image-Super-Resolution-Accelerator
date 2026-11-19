# Vivado power estimate with real switching activity (SAIF) -- ESTIMATE, NOT MEASURED

Date 2026-10-28. Pipeline at 125 MHz (`vitis/m6_sr_pipe3`, bitstream md5 4e7a2895..., the one run on the board) and R0 at 100 MHz (`vitis/m6_sr_0602`, bitstream md5 a44744b2...).
Everything below is a Vivado 2024.1 estimate. Nothing here was measured on the board. Work was done on COPIES of the routed checkpoints (`~/Desktop/venkat/power_estimate_work/{pipe,r0}/routed_copy.dcp`, md5 65d41d94... / cfe32609..., equal to the build outputs, which were not touched).
Full tables: `tables.md`, `tables.csv`. Raw reports and logs: `raw/`. Scripts: `hardware/vivado/scripts/power_*.{tcl,sh}`, `hardware/verification/power/`, `software/analysis/power_{vectors,report}.py`.

## 1. Baseline (vectorless, default settings)
| | Pipeline 125 MHz | R0 100 MHz |
|---|---|---|
| Total on-chip | **2.290 W** | **1.913 W** |
| Dynamic / static | 2.128 / 0.162 W | 1.758 / 0.155 W |
| Clocks / Slice logic / Signals | 0.058 / 0.096 / 0.154 W | 0.025 / 0.009 / 0.025 W |
| BRAM / DSP / I/O | 0.022 / 0.235 / <0.001 W | 0.081 / 0.056 / <0.001 W |
| PS7 (Zynq processing system, Vivado's fixed model) | 1.564 W (68 % of total) | 1.562 W (82 %) |
| Confidence | Low | Low |
(Design resources, as Vivado lists them in the power report: pipeline 170 DSP, 27 BRAM, 9,373 LUT as logic; R0 68 DSP, 72 BRAM, 5,056 LUT as logic.)

## 2. Activity: what was simulated
Stimulus = real images of the 119-image set, results checked bit-exact against the integer model in the testbench (`tb_power.v`, DMA sink always ready, source always valid, no stalls):
* **Pipeline:** Set5 `baby` (256 x 256 LR, one frame = 1,083,793 cycles, 196,608 output beats). **Post-implementation functional netlist** of the core cell (`write_verilog -mode funcsim -cell design_1_i/sr_accel_top_0` from the routed checkpoint copy, so net names equal the in-system design), xsim, 30,000 warm-up cycles, then SAIF windows of 75,000 cycles. **Only 2 windows = 150,000 cycles in steady state completed**: the netlist simulates at about 50-60 cycles/s, and the 1-hour cap killed the run during window 3. This is less than the requested "several hundred thousand cycles". Cross-check: an **RTL** simulation of the same frame (100,000 warm-up + a 400,000-cycle window, 7 minutes), applied the same way.
* **R0:** Set5 `bird`, one 64 x 64 core tile with its real 3-pixel neighbours (tile (1,1) of the 144 x 144 image; 926,2xx cycles, 12,288 output beats; every tile takes the same number of cycles). Post-implementation functional netlist, **the whole tile** in 5 SAIF windows (4 x 190,000 + the last ~166,000 cycles; the 5th window also holds ~0.24 ms of idle time after the tile), 20 minutes wall time. The RTL run of the whole tile (PASS, bit-exact, CYCLES register 926,202 = the simulated value) is the cross-check.
* Correctness of the simulated netlists: the testbench compares every output beat; no mismatch ("FAIL") was printed in any of the four runs, and the R0 netlist run delivered all 12,288 output beats (m_axis_tvalid high for 12,288 cycles in window 5). **Not verified:** the "PASS" summary line did not print in the R0 netlist run although its whole tile had been delivered (the testbench's final register read did not complete in the netlist; cause not found; the same testbench prints PASS in the R0 and full-frame pipeline RTL runs, 12,288 and 196,608 beats bit-exact, CYCLES 926,202 and 1,083,793). The pipeline netlist run was stopped by the 1-hour cap long before the end of its frame, so it could not print PASS either. A first attempt with the post-SYNTHESIS netlist of the IP matched only 12 % of the nets (R0, `raw/r0_postsynth_w1_probe_*`) and was dropped for the post-implementation netlist.

## 3. SAIF applied (`read_saif -strip_path tb_power`, SAIF paths `tb_power/design_1_i/sr_accel_top_0/inst/...`)
| Run | Total W | vs vectorless | DSP W | Signals W | BRAM W | Nets matched (whole design) | Nets matched (core instance) | Confidence |
|---|---|---|---|---|---|---|---|---|
| Pipeline, post-impl, 2 windows (150k cycles) | **2.219** | -3.1 % (-0.071 W) | 0.202 (-14 %) | 0.134 | 0.017 | **67 % (26,250 / 38,954)** | **88 % (26,248 / 29,963)** | Low overall (internal nodes: High) |
| Pipeline, RTL, 400k-cycle window | 2.213 | -3.4 % | 0.210 | 0.123 | 0.017 | 25 % (9,680 / 38,954) | 32 % | Low |
| R0, post-impl, whole tile (time-weighted) | **1.903** | -0.5 % (-0.010 W) | 0.044 (-21 %) | 0.020 | 0.089 (+10 %) | **13 % (2,664 / 20,821)** | **24 % (2,662 / 11,313)** | Low overall (internal nodes: Medium) |
| R0, RTL, whole tile | 1.904 | -0.5 % | 0.052 | 0.022 | 0.080 | 7 % (1,488 / 20,821) | 13 % | Low |
* Window-to-window spread: pipeline w1 2.219 / w2 2.219 W; R0 w1..w5 1.907 / 1.910 / 1.900 / 1.900 / 1.900 W (per-engine phases differ only slightly in total).
* **Confidence stays "Low" in every run** because the row "I/O nodes activity" is Low ("more than 75 % of inputs are missing user specification": the design's 16 package I/Os are not driven by the simulation); internal-node confidence rose to High for the pipeline (Medium for R0).
* **R0 matching is below 50 % and the R0 SAIF result is weak.** Observed: Vivado applied the SAIF to the wrapper, the RAMs and the top-level nets of the core, but to **no net inside the four conv-engine instances e1-e4** (8,216 of the 11,313 core nets stayed at default activity), although those net names exist in the SAIF (97 % of the core net names are present, checked by name). The matched count is identical in all five windows, so it is structural, not a property of the activity. The cause was not identified. R0 uses 4 distinct engine modules (parameterised `conv_engine` copies); the pipeline's stages matched. The DSP and BRAM primitives did respond (DSP -21 %, BRAM +10 %), so the R0 number is not equal to the vectorless one, but it rests on partial information. The R0 PL total is only ~0.34 W, so the effect on the total is small either way.
* The pipeline's SAIF changes the estimate by 3 %, the RTL window agrees with the post-implementation windows to 0.3 % (2.213 vs 2.219 W), which supports that the 150k-cycle window is representative of the steady state. A window length effect (fill/drain, other images) was not studied.

## 4. Energy per frame (Vivado estimate, not measured), E = P x t with today's measured frame times
"PL" = total on-chip minus PS7 (so it includes the device static power); "PL dynamic" = dynamic minus PS7. Primary figures use the SAIF power for the whole frame ("simple"); "refined" uses it only while the core computes and an idle estimate (SAIF power minus the dynamic power of logic, signals, BRAM and DSP) for the rest of the frame.
| Case | Frame time | P total (SAIF) | E total on-chip | E PL (incl. static) | E PL dynamic only | refined E total / E PL |
|---|---|---|---|---|---|---|
| Pipeline, default build | 95.4 ms | 2.219 W | **212 mJ** | **62 mJ** (0.655 W) | 47 mJ (0.495 W) | 199 / 50 mJ |
| Pipeline, non-cacheable DMA buffers | 70.5 ms | 2.219 W | **156 mJ** | **46 mJ** | 35 mJ | 155 / 45 mJ |
| R0 at 100 MHz (**lower confidence**: 24 % of core nets matched, cause not found) | 1,312.5 ms | 1.903 W | **2,498 mJ** | **448 mJ** (0.341 W) | 245 mJ (0.187 W) | 2,488 / 438 mJ |
Vectorless baseline in the same units: pipeline 218 mJ total / 69 mJ PL (95.4 ms), 161 / 51 mJ (70.5 ms); R0 2,511 / 461 mJ.
**Reading:** the PS7 model (1.56 W, fixed) is 70-82 % of the on-chip total, so whole-chip energy per frame is dominated by the processor system and is nearly proportional to the frame time (pipeline 12x less than R0: 212 vs 2,498 mJ). The accelerator's own energy (PL incl. static) is 62 mJ per frame for the pipeline against 448 mJ for R0 (7x less). The energy is for the PL/PS7 power rails Vivado models; it does not include DDR, the board's regulators, the USB-UART bridge, LEDs, etc.

## 4b. Efficiency, GOPS/W (Vivado estimate, not measured)
Work per frame: 2,560 MAC per input pixel x 960 x 540 = 1.327 G MAC = 2.654 GOP (1 MAC = 2 operations). GOPS = 2.654 GOP / frame time; GOPS/W = GOPS / power. "Total" uses the total on-chip power with SAIF (2.219 W), "PL-only" the total minus PS7 (0.655 W, includes the device static power). "refined" = 2.654 GOP / the refined energy of section 4.
| Case | GOPS | GOPS/W total on-chip | GOPS/W PL-only | refined total / PL-only |
|---|---|---|---|---|
| Pipeline, default build (95.4 ms) | 27.8 | **12.5** | **42.5** | 13.3 / 53.1 |
| Pipeline, non-cacheable DMA buffers (70.5 ms) | 37.7 | **17.0** | **57.5** | 17.1 / 59.0 |
| R0 at 100 MHz (1,312.5 ms), **lower confidence** (see section 3) | 2.0 | 1.1 | 5.9 | 1.1 / 6.1 |
These are lower bounds on the efficiency (see the next note). They are Vivado-estimated power, not board measurements.

**PL energy per frame is an upper bound.** The SAIF windows are steady-state busy periods of the core (the compute phase). In the default pipeline build the core computes for only 67.2 ms of the 95.4 ms frame (70 %): the PL idles during the ARM padding (5.8 ms) and the cache maintenance (22.3 ms), but the simple figures (P x t) charge the busy power for the whole frame. The "refined" columns, which use an idle estimate for the rest, are 5-20 % lower for the PL (50 vs 62 mJ default, 45 vs 46 mJ non-cacheable, where the core is busy for 95 % of the frame). The idle estimate itself was not simulated. The same reasoning makes the GOPS/W above lower bounds.

**R0 estimate: lower confidence.** Only 24 % of the core nets (13 % of the design nets) received SAIF activity; every net inside the four conv engines e1-e4 stayed at default activity, cause not found (section 3). The R0 energy and GOPS/W rows must be read as less reliable than the pipeline rows (67 % / 88 % matched).

## 5. Limits
* All numbers are Vivado estimates from a zero-delay functional simulation (no glitching, no real DMA timing) of one image / one tile; the PS7 power does not depend on what the ARM does (Vivado's default PS7 settings); 25 C ambient/typical process assumptions of the tool apply.
* Pipeline: 150,000 simulated cycles only, in the post-implementation run (requested: several hundred thousand); the RTL cross-check has 400,000 cycles but matches only 25 % of the nets.
* R0: partial matching (see above); the testbench's last register read did not complete in the netlist runs.
* Not measured: board power (no board power session will be done). These are on-chip estimates of the Zynq only; they must not be compared with measured board power of other work as if they were the same quantity.
* Vivado hung intermittently in `open_checkpoint` ("Preparing netlist for logic optimization", futex wait); `power_saif_retry.sh` retries with a timeout; no result depends on a hung run.

## 6. pipe3 and pipe4 (added 2026-11-19) -- ESTIMATE, NOT MEASURED
Board-tested builds: pipe3 = `vitis/m6_sr_pipe3_143d` (bitstream md5 042aa316..., routed checkpoint md5 9260d3c0...), pipe4 = `vitis/m6_sr_pipe4_f` (608dbad6..., c93e52bc...), both at 142.857 MHz; work on copies in `~/Desktop/venkat/power_estimate_work/{pipe3,pipe4}/`.
Stimulus: Set5 `baby` (256 x 256 LR) streamed RAW with CONFIG.PAD_EN = 1 (the PL pads, as in the board runs), `power_vectors.py pipe_raw`, `tb_power.v` with `-d PADEN -d CLKNS=7.0`.
Check first: RTL simulation of the whole frame bit-exact (196,608 beats) for both, 543,486 (pipe3) and 408,278 (pipe4) cycles. SAIF from the post-implementation functional netlist (30,000 warm-up cycles, then 75,000-cycle windows); no FAIL line in any netlist run (outputs are compared beat by beat as they appear).
Scripts: `hardware/verification/power/{prep_pipe34.sh, apply_saif.sh, saif_netlist_windows.tcl}`; tables regenerated with `software/analysis/power_report.py` (rows of the other designs unchanged).

| | pipe3 | pipe4 |
|---|---|---|
| Vectorless, total on-chip | 2.685 W (PL incl. static 1.120 W) | 3.059 W (PL 1.494 W) |
| RTL SAIF, 300k cycles | 2.661 W, 25 % of design nets matched | 2.863 W, 15 % matched |
| **Post-implementation netlist SAIF** | **2.691 W** (3 windows, 225k cycles: 2.689 / 2.693 / 2.692); **73 %** design / 86 % core nets matched | **3.013 W** (1 window, 75k cycles; stopped after window 1, ~1.7 h per window); **55 %** design / 60 % core nets matched |
| Confidence | Low (I/O nodes) | Low (I/O nodes) |
| Energy per frame, non-cacheable build | 29.44 ms: **79 mJ** total, **33 mJ** PL | 22.10 ms: **67 mJ** total, **32 mJ** PL |
| Energy per frame, cached build | 51.45 ms: 138 mJ total, 58 mJ PL | 44.11 ms: 133 mJ total, 64 mJ PL |
| GOPS/W (2.654 GOP per frame, non-cacheable) | 90.2 GOPS: 33.5 total / 80.1 PL-only | 120.1 GOPS: 39.9 total / 82.9 PL-only |
| fps per W (on-chip estimate) | 34.0 / 2.691 = 12.6 | 45.2 / 3.013 = 15.0 |

* The core computes for almost the whole non-cacheable frame (frame CYCLES / clock = 29.44 and 22.09 ms), so the simple and refined energies agree there.
* pipe4's matching (60 % of core nets) is lower than pipe3's (86 %); the unmatched nets keep Vivado's default/propagated activity. Not investigated (likely net renaming around the LUT multipliers). The vectorless and SAIF totals differ by 1.5 %.
* Same Vivado warning as in every earlier run (Power 33-332, high-fanout reset nets asserted for long periods).
* fps/W here is on-chip (Zynq only, PS7 modelled as a fixed 1.56 W); it must not be compared with measured board power of other work.
