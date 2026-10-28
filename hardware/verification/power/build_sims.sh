#!/usr/bin/env bash
# Recipe (the commands that were run by hand on 2026-10-28; this file documents them, it was not executed as a script).  Vivado estimate, not measured.
# Work directory W=~/Desktop/venkat/power_estimate_work with, per design t in {pipe, r0}:  t/routed_copy.dcp  (COPY of the routed in-system checkpoint),  t/vec/ (power_vectors.py)
#   1. vivado -mode batch -source hardware/vivado/scripts/power_write_impl_netlist.tcl -tclargs $W/$t/routed_copy.dcp $W/$t/impl_funcsim.v
#   2. python3 hardware/verification/power/mk_sim_wrap.py $W/$t/impl_funcsim.v $W/$t/sim_design_1.v          (instance path tb_power/design_1_i/sr_accel_top_0/inst/...)
#   3. in $W/$t/xi:  xvlog -sv -d NETLIST -d PIPE_MODE=<1|0> -d CLKNS=<8.0|10.0> ../impl_funcsim.v ../sim_design_1.v hardware/verification/power/tb_power.v $XILINX_VIVADO/data/verilog/src/glbl.v
#                    xelab -O2 -L unisims_ver -debug typical tb_power glbl -timescale 1ns/1ps -s simi
#      (RTL cross-check: mk_rtl_wrap.py + the RTL sources instead of impl_funcsim.v, snapshot simr, no glbl, no -d NETLIST)
#   4. hardware/verification/power/run_sims.sh   (xsim <snapshot> -testplusarg VEC=$W/$t/vec -tclbatch run.tcl, capped at 1 h, SAIF Tcl files in this folder)
#   5. hardware/vivado/scripts/power_saif_retry.sh <routed_copy.dcp> <file.saif> <out_prefix>   (read_saif -strip_path tb_power + report_power; retries because Vivado
#      sometimes hangs in open_checkpoint at "Preparing netlist for logic optimization")
#   6. .venv/bin/python software/analysis/power_report.py
# Do not use string generics (-generic_top) for the testbench: xsim then appends them to the scope name (tb_power(VEC=...)) and the SAIF paths no longer match.
