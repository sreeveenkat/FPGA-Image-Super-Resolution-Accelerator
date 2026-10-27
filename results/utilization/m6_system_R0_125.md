# r0_125: deployed network (R0 weights), one more register per engine run, fabric clock 125 MHz (built 2026-10-25, branch `r0_125`, run on the board 2026-10-27 at a 100 MHz PL clock, not 125 MHz: byte-exact, VERSION and checksum as expected, frame time in `results/board/2026-10-27/SUMMARY.md` on main; 125 MHz untested)

Sandbox `~/Desktop/venkat/sandbox_R0_125` (git worktree of branch `r0_125`, off main `ad20b81`). Change = exactly what `docs/paper/fmax_plan.md` proposes, plus the clock and a VERSION:
* `hardware/rtl/conv_engine/conv_engine.v`: the channel-selected activation is registered (`a_r`, one per MAC lane); the weight-ROM address, `v`, `first` and `last` are delayed by one cycle so data, weights and control stay aligned (`waddr_r`, `v2`, `first2`, `last2`). `mac_unit.v`, the requantizer and the weights are unchanged; no `.mem` file changed.
* `hardware/vivado/bd/design_1_m6.tcl`: `PCW_FPGA0_PERIPHERAL_FREQMHZ` 100 -> 125 (+ `PCW_ACT_FPGA0_PERIPHERAL_FREQMHZ`, `PCW_CLK0_FREQ`); `sr_accel_top.v`: `FREQ_HZ 125000000` in the X_INTERFACE_PARAMETER.
* VERSION 0x53524201 (`sr_accel_top.v`, `tb_sr_accel_top.v`, `sr_regs.h`, `docs/REGISTER_MAP.md`, the board scripts' default bitstream), so the driver of this tree refuses the other bitstreams (and theirs refuse this one). R0 stays 0x53520602.

## Simulation (Icarus, this tree)
* `run_tests.sh quick`: **36 passed, 0 failed**. `run_tests.sh full`: **88 passed, 0 failed** (same counts as the deployed design). Raw lines: `results/utilization/r0_125_sim_cycles.txt`.
* Cycles per tile, same test in both trees: tile core **926,201 (deployed) -> 926,205 (r0_125) = +4** on all 9 real-size golden tiles; `CYCLES` register 926,202 -> 926,206; engines L1-L4 124,873 / 69,714 / 69,721 / 589,845 (+1 each, 854,153 together vs 854,149). The deployed numbers were re-run from main on 2026-10-25 with the same commands.
* The register costs a cycle in the RTL regardless of where Vivado places it: 43 of the 60 MAC DSPs have AREG=1 in the routed netlist (engine 1: 16/16, engine 2: 16/16, engine 3: 4/16, engine 4: 7/12), the other 17 keep a fabric flip-flop; the cycle count is the same either way.
* Test tree needs: `data/golden` (copied from main), 10 training images in `data/train/HR` for the seam test, `data/board/*128x128*` and the img0193 files for the host-tool tests (all git-ignored copies).

## Vivado, whole system (`build_m6_system.tcl ... 2`, Vivado 2024.1, 17:30-17:37, 7 min; reports in `~/Desktop/venkat/R0_125_artifacts/reports_R0_125/`, log `build_R0_125.log`)
| Item | r0_125 (125 MHz, this build) | R0 / 0602 (100 MHz, `results/utilization/m6_system_0602.md`) |
|---|---|---|
| Clock | `clk_fpga_0` period 8.000 ns = **125.000 MHz** (`timing_summary.txt`) | 10 ns |
| Setup slack (WNS) | **+0.632 ns**, TNS 0, 0 failing of 24,167 endpoints | +0.503 ns, 0 failing of 23,943 |
| Hold slack (WHS) | **+0.032 ns**, 0 failing | +0.016 ns |
| Critical path | `core/ram3/mem_lo_reg_10` (RAMB36E1) -> LUT6 + MUXF7 + LUT6 -> `core/e4/lane[10].u_mac/acc_reg/A[1]` (DSP48E1), data path 6.928 ns (logic 3.089, route 3.839), setup requirement at the DSP **0.362 ns** (= with the input register; 1.928 ns without) | same path type, 100 MHz |
| LUT | 5,251 (9.87 %), LUT as logic 5,007 | 5,296 |
| FF | 7,979 (7.50 %) | 7,831 (+148 FF, estimate in the plan: below 250) |
| Block RAM tiles / DSP48E1 | 72 / 68 | 72 / 68 |
| DRC | 42 violations, all Warning/Advisory (DPIP-1 32, DPOP-2 4, REQP-181 2, ...)| not compared (no stored DRC of the 0602 build) |
| CRITICAL WARNING / ERROR | **0 / 0 in all 15 run logs** (13 IP synthesis runs, `synth_1`, `impl_1`); the build console shows 13 CRITICAL WARNING lines from block-design creation (board preset PSU-1..4: negative DQS-to-clock delays of the ZedBoard preset; the BD Tcl version note), not in any run log | 0 / 0 |
| Weights | 12 of 12 `.mem` files read (Synth 8-3876 in the `sr_accel_top` synthesis log) | 12 of 12 |
| Power estimate | 1.982 W (`report_power` default activity, confidence Low; **not comparable** to the 1.913 W of `power_estimate_m6.tcl` (vectorless, toggle 12.5 %), a different method) | 1.913 W |

Artifacts (outside the repo): `~/Desktop/venkat/R0_125_artifacts/design_1_wrapper_R0_125.bit` (md5 ecceb98270f5cf1a0ba4b413f26ee11d), `.xsa` (md5 42266f06c844a03cb4e57a817ccbaf3b), `reports_R0_125/`. The bitstream was NOT loaded on a board.

## Plan versus result (all numbers from the plan are estimates, `docs/paper/fmax_plan.md`)
| Quantity | Plan (estimate) | Built |
|---|---|---|
| Extra cycles per tile | +4 | **+4** (926,201 -> 926,205, measured in simulation) |
| Extra FF | below 250 | +148 |
| LUT / BRAM / DSP | 0 / 0 / 0 | -45 LUT (placement/synthesis noise) / 0 / 0 |
| Worst RAM -> MAC A slack at 125 MHz | about +1.31 ns (engine 4) | **+0.632 ns** (same path type, engine 4): the estimate was optimistic by about 0.7 ns because placement changed (the data path is 6.928 ns here vs 6.192 ns in the 152 MHz trial, which the plan said was not modelled) |
| DMA IP slack at 125 MHz | about +0.553 ns | not reported separately; every one of 24,167 endpoints has slack >= +0.632 ns |
| 125 MHz closes timing | "looks reachable" | **yes, in Vivado (post-route)**; not tested on the board |

Not done: board run (checklist in `docs/paper/board_expected.md`, section "R0 at 125 MHz"), post-synthesis netlist simulation, mutation study on the new engine, power on the board.
