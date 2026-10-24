# 150 MHz trial of the unchanged design, repeated 2026-10-24 (reports saved)

Repeat of the 2026-10-16 trial (`docs/paper/timing_150mhz.md`), this time with all reports kept. Whole system (PS7 + AXI DMA + `sr_accel_top` + the M0 IP) built from the repo RTL and
`hardware/vivado/bd/design_1_m6.tcl` in a scratch project (`-jobs 2`, `route_design` only, no bitstream). Only changes: PS7 FCLK0 from the DDR PLL, requested 150 MHz (actual **152.380966 MHz**, `trial_key_log_lines.txt`), and
the `FREQ_HZ 100000000` text removed from the X_INTERFACE_PARAMETER of `sr_accel_top.v` (`rtl_diff.txt` is the complete RTL difference; the block-design Tcl is unchanged).

| File | Content |
|---|---|
| `timing_summary.txt` | `report_timing_summary -max_paths 10` of the routed checkpoint |
| `worst10_setup_paths.txt` | `report_timing -max_paths 10 -nworst 1 -path_type full` (worst setup path of the 10 worst endpoints) |
| `utilization.txt`, `clocks.txt` | utilization and clock report of the same checkpoint |
| `failing_endpoints_580.txt` | all 580 failing setup endpoints (one worst path each): slack, start pin, end pin, cell types, logic levels, data path delay |
| `path_rq_to_dsp.txt`, `path_to_fdre.txt` | two reference paths used to read real setup times (a DSP input with its own register, a fabric FF) |
| `build_trial150.tcl` | the scratch build script (its own report block at the end failed because of a shell-quoting slip in my heredoc and wrote nothing; the reports were made by the scripts below) |
| `reports150.tcl`, `classes150.tcl`, `setups150b.tcl` | the Tcl used on `design_1_wrapper_routed.dcp` to produce the files above |
| `rtl_diff.txt`, `trial_key_log_lines.txt` | RTL difference to the repo and key lines of the build log |

The routed checkpoint itself (scratch, about 100 MB) is not stored. Nothing here was run on the board.
