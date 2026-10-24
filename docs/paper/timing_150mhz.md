# Fast-clock trial of the current design (2026-10-16): timing NOT met

Question: does today's design (no logic change) meet timing at 150 MHz in the whole system?

**Setup.** Scratch copy of `hardware/vivado/scripts/build_m6_system.tcl` (not committed), Vivado 2024.1, -jobs 2. Two changes, neither in the logic:
* PS7 fabric clock FCLK_CLK0: source DDR PLL, requested 150 MHz -> **152.38 MHz** actual (the IO PLL gives 142.86 MHz; exactly 150 MHz is not
  reachable with the board's PLL settings). 152.38 MHz is stricter than 150 MHz.
* `sr_accel_top.v` copy with the `FREQ_HZ 100000000` metadata removed from the `aclk` X_INTERFACE_PARAMETER (block-design validation rejected
  the faster clock otherwise). No other RTL difference (`diff -r` checked).

**Evidence caveat (audit 2026-10-19).** The raw `report_timing_summary` / utilization files of this trial were not saved in the repo or under
`~/Desktop/venkat` (the trial ran in a scratch project). The numbers below were copied from the run and cannot be re-checked from a stored file;
treat them as reported-by-the-run until the trial is repeated and its reports are kept under `results/utilization/`.

**Result (routed, `report_timing_summary`):**

| Item | 152.38 MHz trial | 0602 board build, 100 MHz |
|---|---|---|
| WNS / TNS | **-1.693 ns** / -421.053 ns, 580 of 23,943 endpoints failing | +0.503 ns / 0 |
| WHS | +0.019 ns | +0.016 ns |
| LUT / FF / BRAM / DSP | 5,343 / 7,831 / 72 / 68 | 5,296 / 7,831 / 72 / 68 |
| Worst path | `core/ram3/mem_lo_reg_3` (BRAM) -> 2 x LUT6 + MUXF7 -> `core/e4/lane[1].u_mac/acc_reg/A[7]` (DSP48E1), data path 6.192 ns (logic 3.084, route 3.108) | same path type at 100 MHz |

12/12 weight files read, 68 DSP: the design itself is unchanged. The bitstream was not tried on the board (timing failed).

**Reading.** The design does not run at 150 MHz as it is. The critical path is the activation-RAM read through the split-RAM output
multiplexer into the MAC's DSP input: a register stage there (one cycle of latency per engine run) is the obvious fix, but that is a logic change
and was not made. A rough upper bound from this run is period + |WNS| = 8.26 ns (~121 MHz); that figure is an extrapolation, not a timing-clean build.
For the cycle model this means: 125/150 MHz columns stay predictions that need RTL pipelining first.
