# pipe: whole-frame layer pipeline, R3q weights + anchor, 125 MHz (built 2026-10-27, branch `pipe`, NOT on the board)

Design: `docs/ARCHITECTURE_PIPELINE.md`. Worktree `~/Desktop/venkat/sandbox_pipe` (branch `pipe`, off `r3q_125`). VERSION **0x53525301**; register map
`docs/REGISTER_MAP.md` (pipeline version). The tiled RTL was removed from this branch; the weights and `qparams.npz` are R3q's, unchanged
(`wpipe_L1..4.mem` are a slot-major copy of `weights_L1..4.mem`, made by `export_pipe.py`, checked by `export_pipe.py --check` in the regression).

## Simulation (this tree, final RTL of 2026-10-27; raw lines `results/utilization/pipe_sim_results.txt`; all long runs under `systemd-inhibit`)
| Check | Result |
|---|---|
| `run_tests.sh quick` (Icarus) | **48 passed, 0 failed** |
| `run_tests.sh full` (Icarus + xsim for the limit frames) | **65 passed, 0 failed** |
| mutation test (`mutate_pipe.py`, part of full) | **34 mutants: 33 caught, 1 equivalent (C4, a redundant line, must and does survive), 0 survived**; unmutated control passes every test |
| netlist simulation (`run_postsynth.sh`: synthesized netlist, MAXW = 32, xsim) | **4 passed, 0 failed** (12 of 12 weight files read, 170 DSP48E1; 6 frames, with stalls, error codes 1-4 + size refusals; cycle counts equal to the RTL simulation) |
| 960 x 540 frame (`run_fullframe.sh pfull`, xsim, DIV2K img0193 = the board's T2 input) | **bit-exact**, every stage output exact, **CYCLES 8,398,481** (441 s wall time); highest anchor-FIFO occupancy 2,892 of 4,096 |
| golden tile as a 64 x 64 frame (T1) | bit-exact, CYCLES **74,641** |
| limit frames (xsim) | 192x192 616,337 cycles; 960x24 439,697; 1018x4 (MAX_W) 139,105; 1x4096 (MAX_H) 328,153: all bit-exact |

Cycles per output pixel of layer 1: 8,398,481 / (964 x 544) = **16.01**. Predicted frame time from the simulated cycles: 8,398,481 / 125 MHz = **67.2 ms** core
+ 5.9 ms ARM padding (measured on R0) = **73.1 ms (13.7 fps)**; cache maintenance of the 1.6 MB / 6.2 MB buffers and the DMA set-up are not modelled
(upper estimate +29.2 ms = R0's per-frame overhead outside padding and tile copies: **73.1-102.3 ms**). **Prediction, not measured.** R0 on the board: 1,311.9 ms.

## Vivado, whole system (`build_m6_system.tcl ... 2`, Vivado 2024.1, 2026-10-27 00:22-00:29; reports `~/Desktop/venkat/pipe_artifacts/reports_pipe/`)
| Item | pipe (125 MHz) | r3q_125 (tiled, 125 MHz) |
|---|---|---|
| Clock | `clk_fpga_0` 8.000 ns = 125.000 MHz | same |
| Setup / hold slack | **WNS +0.267 ns, WHS +0.014 ns**, 0 failing of 39,660 endpoints | +0.393 / +0.025 ns |
| Critical path | `core/fw_reg` -> `fw + 2 - 1` compare (CARRY4 x 7) -> `core/s3/ix_reg/R`, 7.118 ns, 11 levels (a static frame-size compare; could be registered if margin is needed) | RAM -> MAC input |
| LUT / FF | **9,888 (18.6 %) / 15,782 (14.8 %)** | 5,288 / 7,881 |
| BRAM tiles / DSP | **27 / 170 (77 %)** | 71.5 / 68 |
| accelerator (`sr_pipe_core`) | 6,705 LUT, 11,560 FF, 23 BRAM, 170 DSP; L4 stage alone 3,478 LUT / 110 DSP | |
| DRC | 158, all Warning/Advisory (DPOP-2 152 = DSP M-register not used for the output, PDCN-1569 3, RTSTAT-10 1, REQP-181 2) | 26 |
| CRITICAL WARNING / ERROR in the run logs | **0 / 0** | 0 / 0 |
| Weights | 12 of 12 (`wpipe_L1..4`, `bias_L1..4`, `mult_L1..4`) read from this tree; `ANCHOR bound to: 1` | 12 of 12 |
| Power estimate | 2.290 W (`report_power` default activity, confidence Low) | 1.986 W |

Artifacts (outside the repo): `~/Desktop/venkat/pipe_artifacts/design_1_wrapper_pipe.bit` (md5 4e7a28951fd4c5b1939dcdc12b4f7777), `.xsa`
(md5 2fcec6b7f1ea8c297bc0db87d8389c37), `reports_pipe/`, `build_pipe.log`, `postsynth.log`, `fullframe_960x540.log`. Superseded builds:
`superseded_occupancy_bug/` (first build, with the FIFO bug below) and `superseded_fifo_fix_only/` (before the frame-height cap).
ELFs (git-ignored): `software/board/build/sr_app_t{1,2,3_20f,3_200f,11,11_20f}.elf`.

## Bugs found on the way (both fixed; `docs/PIPELINE_COUNTER_AUDIT.md`)
1. **Anchor-FIFO deadlock (2026-10-26).** The occupancy `(wp - rp) >= DEPTH - 4` was evaluated in 32 bits. After the 13-bit pointers wrapped (8,192 pushes),
   `full` went high with 579 entries inside, and the 960x540 frame stopped after 5 of 540 output rows. Found only by the full-size frame: no regression
   frame pushed more than 3,072 anchors, and the mutation test (30 mutants, all others caught) cannot detect a state no test reaches. Fixed with an
   occupancy in the pointers' own width (also in `pipe_fifo.v`). New: `tb_fifos.v`, limit frames, mutant F2.
2. **Frame-height overflow (audit 2026-10-27).** The 16-bit sums `fh + 6` / `fh + 3` wrapped for H >= 65,530, which the start check accepted. Now
   H <= 4,096 (ERROR_CODE 4 above). New: H = 4097 refusal check, mutant A3.
Earlier, during bring-up (2026-10-26): a missing sign extension of the tree sum (caught by the first stage test) and an unpacker reset that dropped the
first input beat (caught by the first top-level test).
