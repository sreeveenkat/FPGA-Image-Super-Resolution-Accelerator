# Fast-clock trial of the current design: timing NOT met at 152.38 MHz (first run 2026-10-16, repeated with all reports saved 2026-10-24)

Question: does today's design (no logic change) meet timing at 150 MHz in the whole system? **No.**

**Setup (both runs).** Scratch project from the repo RTL and `hardware/vivado/bd/design_1_m6.tcl` (as `build_m6_system.tcl`), Vivado 2024.1, `-jobs 2`. Two changes, neither in the logic:
* PS7 fabric clock FCLK_CLK0: source DDR PLL, requested 150 MHz -> **152.380966 MHz** actual (the IO PLL gives 142.86 MHz; exactly 150 MHz is not reachable with the board's PLL settings).
  152.38 MHz is stricter than 150 MHz.
* `sr_accel_top.v` copy with the `FREQ_HZ 100000000` metadata removed from the `aclk` X_INTERFACE_PARAMETER (block-design validation rejected the faster clock otherwise).
  No other RTL difference: `results/utilization/timing_150mhz/rtl_diff.txt` is the complete `diff -r`; the block-design Tcl is unchanged.

**Evidence.** The 2026-10-16 run kept no reports. On **2026-10-24** the trial was repeated in a scratch project (routed, no bitstream) and its reports are stored in
`results/utilization/timing_150mhz/` (README there lists every file). **Every number of the first run was reproduced exactly** (WNS, TNS, endpoint counts, WHS, resources and the worst path to the cell), so the earlier
"cannot be re-checked" caveat is removed.

| Item | 152.38 MHz trial (repeat 2026-10-24, = first run) | 0602 board build, 100 MHz |
|---|---|---|
| WNS / TNS | **-1.693 ns** / -421.053 ns, 580 of 23,943 endpoints failing (`timing_summary.txt`) | +0.503 ns / 0 |
| WHS | +0.019 ns | +0.016 ns |
| LUT / FF / BRAM / DSP | 5,343 / 7,831 / 72 / 68 (`utilization.txt`) | 5,296 / 7,831 / 72 / 68 |
| Worst path | `core/ram3/mem_lo_reg_3` (RAMB36E1) -> LUT6 + MUXF7 + LUT6 -> `core/e4/lane[1].u_mac/acc_reg/A[7]` (DSP48E1), data path 6.192 ns (logic 3.084, route 3.108) (`worst10_setup_paths.txt`) | same path type |
| Routing tool's own estimate during the run | WNS -1.695 / TNS -423.380 (`trial_key_log_lines.txt`) | |

12 of 12 weight files read, 68 DSP (`weights_read_lines.txt`): the design itself is unchanged. The bitstream was not tried on the board (timing failed).

**What fails (new, from `failing_endpoints_580.txt`; 580 endpoints, one worst path each; 434 + 106 + 21 + 9 + 8 + 2 = 580):**

| Class of failing endpoint | Endpoints | Worst slack |
|---|---|---|
| activation RAM of layer n -> channel mux -> MAC DSP **A input**, engine 4 (from `ram3`) | 96 | -1.693 ns |
| same, engine 3 (from `ram2`) | 128 | -1.618 ns |
| same, engine 1 (from `ram0`) | 126 | -0.902 ns |
| same, engine 2 (from `ram1`) | 84 | -0.524 ns |
| inside the Xilinx AXI DMA / datamover and interconnect (`sig_btt_*`, `sig_regfifo_dout_reg`, `dmacr_i_reg`, `m_payload_i_reg`, `M_AXI_WDATA_I_reg`, ...) | 106 | -0.885 ns (`sig_btt_eq_0_reg`) |
| requantizer feed in engine 4 (`rq_i_reg` -> result mux -> requantizer DSP A/B) | 21 | -0.392 ns |
| weight ROM (`q_reg`) -> engine 4 DSP B input | 8 | -0.153 ns |
| our AXI-Lite registers (`slv_reg3_reg`, `dbg_pre_reg`; reset-synchronizer fan-out to the R pins) | 9 | -0.174 ns |
| tile-core output word (`ram4` -> `ow_reg`) | 2 | -0.091 ns |

Setup requirements read from the same checkpoint: a DSP48E1 **A pin without an input register** (the MAC operand) 1.928 ns; a DSP input **with** its own input register (the requantizer, `path_rq_to_dsp.txt`) 0.362 ns;
a fabric flip-flop (`path_to_fdre.txt`) 0.062 ns. The RAMB36E1 clock-to-output on the worst path is 2.454 ns (no output register).

**Reading.** The design does not run at 150 MHz as it is. The critical class is the activation-RAM read through the split-RAM output multiplexer and the engine's channel select into the MAC's DSP input, which has no input register.
One register stage there (one cycle of latency per engine run) removes most of it, see `docs/paper/fmax_plan.md` (a proposal only; no RTL was changed). Even then the AXI DMA IP (-0.885 ns) would limit a 152 MHz build.
A rough upper bound from this run is period + |WNS| = 8.26 ns (~121 MHz); that is an extrapolation, not a timing-clean build.
For the cycle model this means: 125/150 MHz columns stay predictions that need RTL pipelining first.
