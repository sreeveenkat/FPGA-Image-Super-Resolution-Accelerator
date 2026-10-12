# M6 - in-system Vivado build, VERSION 0x53520602 (`m6_sr_0602`)

Vivado 2024.1 project `/home/sreevenkat/Desktop/venkat/vitis/m6_sr_0602` = a copy of `m6_sr` (same block design: PS7 + AXI DMA + `sr_accel_top_0`,
`FCLK_CLK0` = 100 MHz), rebuilt 2026-10-12 with `hardware/vivado/scripts/rebuild_m6_bitstream.tcl ... 2` from the repo RTL (VERSION 0x53520602, adds the
7 debug registers). **Vivado post-implementation numbers, read by Claude from the reports** (copies: `m6_system_0602_utilization.txt`,
`m6_system_0602_timing_summary.txt`). The board results of this bitstream are in `docs/OVERNIGHT_LOG.md` (STEP C) and `results/speed/m6_board.md`.

## Results
| Item | 0602 (`m6_sr_0602`, this build) | 0601 (`m6_sr`, `m6_system.md`) |
|---|---|---|
| Setup slack (WNS) | **+0.503 ns**, TNS 0 | +0.239 ns |
| Hold slack (WHS) | **+0.016 ns**, THS 0 | +0.023 ns |
| Failing endpoints | 0 of 23,943 ("All user specified timing constraints are met") | 0 of 23,269 |
| Critical path | `sr_accel_top_0/.../core/ram3/mem_lo_reg_3` (BRAM) -> `core/e4/lane[7].u_mac/acc_reg/A[7]` (DSP48E1), clk_fpga_0 | - |
| LUT | 5,296 (9.95 %), of which LUT as memory 240 | 5,146 |
| FF | 7,831 (7.36 %) | 7,605 |
| Block RAM tiles | 72 (51.43 %) | 72 |
| DSP48E1 | **68** (30.91 %) | 68 |
| BUFGCTRL | 1 | 1 |
| Power estimate | 1.913 W (Vivado estimate, confidence Low; includes PS7) | 1.919 W |
| Weights | 12 of 12 `.mem` files "read successfully" (Synth 8-3876), see below | 12 of 12 |
| CRITICAL WARNING / ERROR | **0 / 0** in all run logs (9 IP synth runs, synth_1, impl_1) | - |

Differences 0602 - 0601: +150 LUT, +226 FF (the debug registers and the wider read mux), same BRAM/DSP. WNS is better (+0.503 vs +0.239 ns), WHS 7 ps
lower; both are placement-dependent (+/- 0.1 ns seen before), not an RTL improvement.

## The 12 "read successfully" lines (sr_accel_top OOC synthesis, `design_1_sr_accel_top_0_0_synth_1/runme.log`)
```
bias_L1.mem  mult_L1.mem  wrom_L1.mem    (conv_engine.v:128 / :129, weight_rom.v:22)
bias_L2.mem  mult_L2.mem  wrom_L2.mem
bias_L3.mem  mult_L3.mem  wrom_L3.mem
bias_L4.mem  mult_L4.mem  wrom_L4.mem
```
all from `/home/sreevenkat/Desktop/venkat/sem_project_all/hardware/rtl/weights/`.

## Warnings in impl_1 (none critical)
100 x DRC DPIP-1 and 4 x DPOP-2 (DSP input/output pipelining advice), 3 x PDCN-1569, 1 x RTSTAT-10 (33 unused nets inside the AXI protocol converter),
33 x Vivado_Tcl 4-919/4-921 (empty CDC waiver lists in the AXI DMA IP's own .xdc), 1 x Power 33-332, Device 21-9320/21-2174 ("Virtual grid" initialisation:
a Vivado device-database message, not about this design).

## Build
| Item | Value |
|---|---|
| Command | `vivado -mode batch -source hardware/vivado/scripts/rebuild_m6_bitstream.tcl -tclargs .../m6_sr_0602/m6_sr.xpr 2` (nice 10) |
| Build time | 5 min 34 s (Vivado session 15:13:30 -> 15:19:04; 9 OOC IP runs + synth_1 + impl_1 + bitstream + XSA) |
| Parallel jobs | 2 (the default of 8 froze the PC earlier that day) |
| Lowest available memory (watchdog, 20 s samples) | 6.5 GB of 15 GB (10 GB at the start) |
| Outputs | `m6_sr_0602/m6_sr.runs/impl_1/design_1_wrapper.bit` (15:18), `m6_sr_0602/design_1_wrapper.xsa` (15:19), reports `m6_sr_0602/reports_final/` |
