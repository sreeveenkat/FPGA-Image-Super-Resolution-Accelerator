# pipe4 system build, verification and board result (2026-11-18)

Build f of `docs/ARCHITECTURE_PIPELINE_V4.md`: `SR_DMA_MM64=1 SR_IMPL_STRATEGY=Performance_ExtraTimingOpt build_m6_system.tcl <out> 1 142.857`; Vivado 2024.1,
xc7z020clg484-1, FCLK0 142.857 MHz. Reports `m6_system_pipe4_{timing_summary,utilization,utilization_hier,drc,power}.txt` (copies of `~/Desktop/venkat/pipe4_artifacts/reports_pipe4/`).

| Item | pipe4 (6 cycles/px) | pipe3 (8 cycles/px) |
|---|---|---|
| WNS / WHS at 142.857 MHz | **+0.038 / +0.004 ns**, 0 failing | +0.132 / +0.015 ns |
| LUT / FF / BRAM / DSP | 24,783 / 30,580 / 31.5 / 213 | 13,334 / 19,938 / 29.5 / 190 |
| Vivado vectorless power (estimate) | 3.06 W | 2.685 W |
| 960x540 frame cycles (xsim, PL padding) | 3,156,214 | 4,205,054 |
| bitstream md5 | 608dbad60a22c4c9bd9d3e567a19b9cc | 042aa316fbfb41982491f2e8ddec5512 |

Verification (logs in `~/Desktop/venkat/pipe4_artifacts/`):
* 960x540 with PL padding: bit-exact, every stage output exact (`fullframe_960x540_pad1.log`).
* netlist simulation 7/7, 213 DSP48E1, 12/12 weight files (`postsynth.log`).
* quick regression on the final RTL 137/138; the failure was `test_regs.py` expecting the old `wire size_ok` text (test fixed, no RTL change). **Full regression
  177/177 passed, 0 failed, EXIT 0** (`run_tests_full.log`, incl. mutation 79: 74 caught, 5 equivalent, 0 survived).
* mutation: 79 mutants, 74 caught, 5 equivalent (V4, P3, C4 as before; N7 empty channels only write outside the output word; N12 MLAT is timing-only), 0 survived
  (`mutation.log` + the rerun of S8/S11/V1/V5/N5/N7/N12 after retargeting their patterns).

Board (main `results/board/2026-11-18/SUMMARY.md` section 1b): read-back 142.857 MHz; T1 28,374-28,384 cycles; T2 byte-exact 3,156,225 cycles; 119/119 byte-exact;
**22.10 ms = 45.2 fps** non-cacheable, 25.41 ms ARM padding, 44.11 ms cached; VERSION refusals both ways; die up to 50.4 C. Power not measured.
