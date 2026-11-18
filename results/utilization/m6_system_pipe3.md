# pipe3 system build and verification (2026-11-18; PC only, NOT run on a board)

Build d of `docs/ARCHITECTURE_PIPELINE_V3.md`: `build_m6_system.tcl <out> 1 142.857` with `SR_DMA_MM64=1`; Vivado 2024.1, xc7z020clg484-1, FCLK0 142.857 MHz.
Reports: `m6_system_pipe3_{timing_summary,utilization,utilization_hier,drc,power}.txt` (copies of `~/Desktop/venkat/pipe3_artifacts/reports_pipe3/`).

| Item | pipe3 (142.857 MHz) | pipe2p (125 MHz) |
|---|---|---|
| WNS / WHS | **+0.132 / +0.015 ns**, 0 failing endpoints | +0.450 / +0.007 ns |
| LUT / FF / BRAM / DSP | 13,334 / 19,938 / 29.5 / 190 | 13,323 / 19,688 / 27 / 190 |
| Vivado vectorless power (estimate) | 2.685 W | 2.51 W |
| bitstream md5 | 042aa316fbfb41982491f2e8ddec5512 | 07dd0689d625... |

Verification (logs in `~/Desktop/venkat/pipe3_artifacts/`):
* quick regression 104/104 (`run_tests_quick.log`; run before the input-side invariants were added to the testbench); **full regression 135/135, EXIT 0** (`run_tests_full.log`: all quick tests incl. the new invariants, real frames with PL padding, limit frames p192 / pw960x24 / pmaxw / ptall in xsim with PAD_EN 0 and 1, board program build, mutation test).
* 960x540 with PL padding: bit-exact in xsim, every stage output exact, 4,205,054 cycles (`fullframe_960x540_pad1.log`).
* netlist simulation 7/7 incl. 3 PL-padding runs; 12/12 weight files, 190 DSP48E1 (`postsynth.log`).
* mutation: 66 mutants, 63 caught, 3 equivalent (V4, P3, C4), 0 survived (C7, C8, D13 caught after the testbench invariants; C2 pattern fixed).
