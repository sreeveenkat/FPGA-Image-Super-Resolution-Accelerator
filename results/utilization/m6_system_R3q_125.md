# r3q_125: R3q network (re-param + anchor + QAT weights) with the r0_125 timing change, fabric clock 125 MHz (built 2026-10-26, branch `r3q_125`, NOT on the board)

Sandbox `~/Desktop/venkat/sandbox_R3q_125` (git worktree of branch `r3q_125`, off `r3q` 8aa9b95). Change = commit e80403a of `r0_125` applied to R3q
(cherry-pick; the only conflicts were VERSION lines):
* `hardware/rtl/conv_engine/conv_engine.v`: the MAC activation is registered (`a_r`), the ROM address and `v/first/last` are one cycle later
  (`waddr_r`, `v2`, `first2`, `last2`). The anchor logic of R3q (requantizer `add`, anchor address generator) is untouched: it follows the written words,
  which are one cycle later as a whole.
* `hardware/vivado/bd/design_1_m6.tcl`: FCLK0 125 MHz; `sr_accel_top.v` `FREQ_HZ 125000000`.
* VERSION **0x53524301** (`sr_accel_top.v`, `tb_sr_accel_top.v`, `sr_regs.h`, `docs/REGISTER_MAP.md`, the board scripts' default bitstream
  `~/Desktop/venkat/R3q_125_artifacts/design_1_wrapper_R3q_125.bit`). The weights, `qparams.npz` and all `.mem` files are R3q's, unchanged.

## Simulation (Icarus + xsim, this tree)
* `run_tests.sh quick`: **42 passed, 0 failed**. `run_tests.sh full`: **95 passed, 0 failed** (same counts as R3q at 100 MHz), including the
  26-mutant anchor mutation test (`26 mutants, 0 problems`).
* `run_postsynth.sh` (netlists re-synthesized from scratch in this tree): **5 passed, 0 failed** (layers 1-4, layer 4 with the anchor, + HC=6 tile core).
* Cycles per tile: tile core **926,205** on all 9 real-size golden tiles (R3q at 100 MHz: 926,201, the anchor adds no cycle), `CYCLES` register
  926,206 (929,242 with random stalls); engines 124,873 / 69,714 / 69,721 / 589,845 (each +1). Raw lines: `results/utilization/r3q_125_sim_cycles.txt`.

## Vivado, whole system (`build_m6_system.tcl ... 2`, Vivado 2024.1, 2026-10-26; reports `~/Desktop/venkat/R3q_125_artifacts/reports_R3q_125/`, copies here)
| Item | r3q_125 (125 MHz, this build) | R3q (100 MHz, branch `r3q`, `m6_system_R3q.md`) | r0_125 (125 MHz, branch `r0_125`) |
|---|---|---|---|
| Clock | `clk_fpga_0` 8.000 ns = **125.000 MHz** | 10 ns | 8 ns |
| Setup slack (WNS) | **+0.393 ns**, TNS 0, 0 failing of 24,093 endpoints | +0.683 ns | +0.632 ns |
| Hold slack (WHS) | **+0.025 ns**, 0 failing | +0.028 ns | +0.032 ns |
| Critical path | `core/ram3/mem_lo_reg_4` (RAMB36E1) -> LUT6 + MUXF7 + LUT6 -> `core/e4/lane[11].u_mac/acc_reg/A[1]` (DSP48E1), data path 7.179 ns (logic 3.094, route 4.085) | ram2 -> layer-3 MAC input | same type (ram3 -> e4 lane[10]) |
| LUT / FF | 5,288 / 7,881 | 5,323 / 7,869 | 5,251 / 7,979 |
| BRAM tiles / DSP | 71.5 / 68 | 71.5 / 68 | 72 / 68 |
| DRC | 26 violations, all Warning/Advisory (DPIP-1 16, DPOP-2 4, PDCN-1569 3, REQP-181 2, RTSTAT-10 1) | | 42 |
| CRITICAL WARNING / ERROR in the run logs | **0 / 0** (`synth_1`, `impl_1`, IP runs); the build console's 13 CRITICAL WARNING lines are the ZedBoard preset PSU-1..4 (negative DQS-to-clock delays) and the BD Tcl version note, as in r0_125 | 0 / 0 | 0 / 0 |
| Anchor | `ANCHOR bound to: 1` on layer 4, `ADD_EN bound to: 1` on its requantizer, `ADD_EN 0` on the other three (synthesis log) | same | - |
| Weights | 12 of 12 `.mem` files read from this tree (Synth 8-3876) | 12 of 12 | 12 of 12 |
| Power estimate | 1.986 W (`report_power` default activity, confidence Low; not comparable to the 1.916 W of R3q, which used `power_estimate_m6.tcl`) | 1.916 W | 1.982 W |

Artifacts (outside the repo): `~/Desktop/venkat/R3q_125_artifacts/design_1_wrapper_R3q_125.bit` (md5 a32acd2ddc4475a18ed202fd69250343), `.xsa`
(md5 2eab523a9246cf55ef824c2e2547c3cc), `reports_R3q_125/`, `build_R3q_125.log`, `postsynth.log`. ELFs (git-ignored, this tree):
`software/board/build/sr_app_t{1,2,3_20f,3_200f,11,11_20f}.elf`, built with `build_elf.sh`; link warnings only from the BSP's `xparameters.h`.

Prediction (cycle model, the same as r0_125, since cycles per tile are the same): 135 x 926,224 (board mean + 4) / 125 MHz + 61.5 ms ARM/DMA = about 1,062 ms
per frame = **0.94 fps**. Expected output checksum = R3q's (fnv1a32 0x45dd4e2d on the img0193 960x540 frame; same weights). NOT on the board.

Not done: board run, power on the board, the AREG/fabric-register split of the 60 MAC DSPs (r0_125: 43 of 60 absorbed; it does not change cycles).
