# M7 table D - power and energy (Vivado ESTIMATE, not measured)

Design: the routed in-system build 0602 (`~/Desktop/venkat/vitis/m6_sr_0602`, PS7 + AXI DMA + `sr_accel_top_0` at 100 MHz), the bitstream that passed the
board regression and ran all 119 test images byte-exact. `report_power` on the routed checkpoint, **vectorless** (no simulation activity file), Vivado 2024.1,
xc7z020clg484-1, 25 C ambient, default board/thermal settings. Script: `hardware/vivado/scripts/power_estimate_m6.tcl` (opens the checkpoint read-only).
Reports: `m7_power_0602_toggle{6,12,25}.txt` (default toggle rate 6.25 / 12.5 (Vivado default) / 25 %). The 12.5 % run reproduces the build's own report
(`m6_sr_0602/reports_final/power.txt`, 1.913 W) exactly.

**Vivado rates the confidence of this estimate "Low"** (I/O activity unspecified, internal activity only partly specified). Nothing here was measured on the board:
the ZedBoard has no on-board power monitor in this setup. Quote these as "estimated".

## Power (W), estimate
| Item | toggle 6.25 % | **12.5 % (default)** | 25 % |
|---|---|---|---|
| Total on-chip | 1.911 | **1.913** | 1.915 |
| Device static | 0.155 | 0.155 | 0.155 |
| Dynamic | 1.756 | 1.758 | 1.760 |
| - PS7 (ARM cores, DDR controller, PS peripherals) | 1.563 | **1.563** | 1.565 |
| - `sr_accel_top_0` (the accelerator) | 0.176 | **0.176** | 0.176 |
| - AXI DMA + interconnects | 0.016 | 0.017 | 0.018 |

PL resources at the default rate: Block RAM 0.081 W, DSP 0.056 W, signals 0.025 W, clocks 0.025 W, slice logic 0.009 W. Junction temperature 47.1 C.

* The total hardly depends on the assumed toggle rate (+/- 0.002 W): **82 % of it is the PS7**, whose estimate comes from its configuration (CPU and DDR
  clocks), not from switching activity. The accelerator's 0.176 W is dominated by BRAM and DSP, whose estimate uses their enable rates, which the toggle-rate
  setting does not change. A simulation-based (SAIF) estimate was **not** done; it could lower the accelerator number (the engines run one after another, so
  only one engine's DSPs are busy at a time) but would not change the total much.
* The accelerator is about **9 % of the chip's power** (0.176 of 1.913 W); the PL part including DMA and interconnect is 0.193 W.

## Energy (estimated power x board-measured time)
Times are board measurements (`results/speed/m6_board.md`, 0602 regression): 1.312 s per 960x540 -> 1920x1080 frame, 9.52 ms per 64x64 tile.

| Quantity | Value |
|---|---|
| Energy per frame, whole chip (1.913 W x 1.312 s) | **~2.5 J** |
| Energy per frame, accelerator only (0.176 W x 1.312 s) | ~0.23 J |
| Energy per frame, PL incl. DMA + interconnect (0.193 W x 1.312 s) | ~0.25 J |
| Energy per tile, accelerator only (0.176 W x 9.52 ms) | ~1.7 mJ |
| Energy per output pixel (2,073,600 px), whole chip / accelerator | ~1.2 uJ / ~0.11 uJ |

Assumption behind the per-frame numbers: the estimated power holds during the whole frame. The ARM is busy for the entire frame (driver loop + copies), and the
accelerator computes during ~97 % of it (DMA+compute 1.279 of 1.312 s), so this is a reasonable but unverified assumption.
Board-level power (regulators, DDR chips, USB-UART, LEDs) is not included in any of these numbers.
