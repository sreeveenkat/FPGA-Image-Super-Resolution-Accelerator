#!/usr/bin/env bash
# xi = post-IMPLEMENTATION functional netlist of the core cell written from the routed checkpoint copy (write_verilog -mode funcsim -cell design_1_i/sr_accel_top_0): net names equal the in-system design.
# Starts the four SAIF simulations in the background (each capped at 1 hour of wall time) from the work directory ~/Desktop/venkat/power_estimate_work.
# Vivado estimate, not measured.  Needs the snapshots built by build_sims.sh (not in the repo: see results/power_estimate/SUMMARY.md for the recipe).
W=~/Desktop/venkat/power_estimate_work; H=$(cd "$(dirname "$0")" && pwd)
source ~/Desktop/vivado_install/Vivado/2024.1/settings64.sh >/dev/null 2>&1
echo "source $H/saif_pipe_netlist.tcl" > $W/pipe/xi/run.tcl
echo "source $H/saif_r0_netlist.tcl"   > $W/r0/xi/run.tcl
echo "source $H/saif_pipe_rtl.tcl"     > $W/pipe/rtl/run.tcl
echo "set saif_name r0_rtl.saif; source $H/saif_whole_run.tcl" > $W/r0/rtl/run.tcl
for d in pipe/xi:simi r0/xi:simi pipe/rtl:simr r0/rtl:simr; do
  dir=${d%%:*}; snap=${d##*:}; v=$W/${dir%%/*}/vec
  ( cd $W/$dir && nohup /usr/bin/time -v timeout 3600 xsim $snap -testplusarg VEC=$v -tclbatch run.tcl -log sim.log > time.log 2>&1 & echo "$dir pid $!" )
done
