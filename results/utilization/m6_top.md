# M6 step 1 - accelerator top `sr_accel_top` (AXI4-Lite + AXI-Stream + tile core)

Out-of-context synthesis and place and route, Vivado 2024.1, part xc7z020clg484-1, `aclk` 100 MHz (10 ns), 2026-10-11.
Script: `hardware/vivado/scripts/synth_sr_accel_top.tcl` (run from the project root). **No generics are passed**: this is the DEFAULT build the block design
will use (HC = 64, WDIR = the absolute path inside `sr_accel_top.v`). Raw reports: `m6_top_*.txt` in this folder. Estimates from tools, nothing measured on a board.

| Item | Synthesis | After place and route |
|---|---|---|
| Slice LUT | 2,121 | **1,988** (3.74 %; 20 of them LUT-as-memory) |
| Slice registers (FF) | 3,479 | **3,479** (3.27 %) |
| Block RAM tiles | 70 | **70** (50 %; 68 x RAMB36 + 4 x RAMB18) |
| DSP48 | 68 | **68** (30.9 %) |
| Setup slack (WNS) at 100 MHz | - | **+0.677 ns** (0 failing endpoints of 12,083) |
| Hold slack (WHS) | - | **+0.085 ns** (0 failing) |
| Routing | - | 0 nets with routing errors |
| Power (Vivado estimate, out-of-context, confidence medium, no I/O) | - | 0.279 W total (0.170 dynamic, 0.109 static) |

Compared with the bare core (M5, `m5_tile_core.md`): 1,896 LUT / 3,341 FF / 68 DSP / 70 BRAM / WNS +0.723 ns. The top adds about 92 LUT and 138 FF
(AXI-Lite registers, word packing, status logic) and costs 0.05 ns of slack (placement noise level).

Pass conditions of the task: DSP = 68 (weights were loaded: yes), BRAM about 70 (yes), WNS >= 0 (yes).

## Synthesis-log check (`hardware/vivado/build/sr_accel_top/vivado.log`)
* `$readmem` ... "is read successfully": 12 of 12 files (`wrom`, `bias`, `mult` for L1..L4), read through the default absolute WDIR.
* "could not open" / "cannot open": none. `Synth 8-311`: none. `Synth 8-4445`: none. CRITICAL WARNING count: 0.
* Warnings that are expected: `Synth 8-7129` unused ports (`s_axi_awprot`, `s_axi_arprot`, `s_axi_araddr[1:0]`), `Synth 8-3936` trimmed `w_data_reg`/`w_strb_reg`
  (only bits 0 and 1 of CONTROL are used), `Synth 8-6014` unused `ci1_reg` in a conv engine.

## Interface inference (throwaway check, scratch project, NOT the block design)
A module reference of `sr_accel_top` in a fresh Vivado project showed: interfaces `s_axi` (aximm slave), `s_axis` (axis slave), `m_axis` (axis master);
`aclk` ASSOCIATED_BUSIF = `s_axi:s_axis:m_axis`, ASSOCIATED_RESET = `aresetn`, FREQ_HZ 100000000; `aresetn` POLARITY ACTIVE_LOW; user parameters only
`HC` (64) and `WDIR` (the absolute path).

## Limits
Out-of-context: no I/O constraints, no PS, no DMA. The absolute `WDIR` ties the synthesis to this machine. The AXI-Lite and stream timing with the
real PS7 and DMA is not covered. Power is a tool estimate.

## Version 0x53520602: with the debug registers (2026-10-11, out-of-context, same script, NOT yet in a bitstream on that date; built into the board bitstream 0602 on 2026-10-12, see `m6_system_0602.md`)
`hardware/rtl/top/sr_accel_top.v` with the 7 read-only debug registers (0x18-0x30, `docs/REGISTER_MAP.md`). Reports: `m6_top_dbg_utilization_routed.txt`, `m6_top_dbg_timing_routed.txt`.

| Item | 0x53520601 (above, in the board bitstream) | 0x53520602 (debug registers) |
|---|---|---|
| Slice LUT (routed) | 1,988 | 2,114 |
| Slice registers | 3,479 | 3,705 |
| Block RAM tiles | 70 | 70 |
| DSP48 | 68 | 68 |
| WNS / WHS at 100 MHz | +0.677 / +0.085 ns | +0.305 / +0.081 ns (0 failing of 12,691) |

12 of 12 `.mem` files read (Synth 8-3876), no Synth 8-311 / 8-4445. The lower WNS is placement of a slightly bigger design (the debug counters are not on the
old critical path); still met, but a full in-system build must be re-checked if this version is ever put into the block design.
