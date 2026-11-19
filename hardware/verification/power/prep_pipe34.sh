#!/usr/bin/env bash
# 2026-11-19: prepare the SAIF power simulations for pipe3 / pipe4 (Vivado estimate, not measured).  Usage: prep_pipe34.sh <pipe3|pipe4>
set -e
t=$1; W=~/Desktop/venkat/power_estimate_work; R=~/Desktop/venkat/sem_project_all; T=~/Desktop/venkat/sandbox_$t
source ~/Desktop/vivado_install/Vivado/2024.1/settings64.sh >/dev/null 2>&1
cd $W/$t
echo "== netlist $(date +%T)"
for a in 1 2 3; do
  timeout -k 5 900 vivado -mode batch -nojournal -nolog -source $R/hardware/vivado/scripts/power_write_impl_netlist.tcl -tclargs $W/$t/routed_copy.dcp $W/$t/impl_funcsim.v > netlist_vivado.log 2>&1 < /dev/null && [ -s impl_funcsim.v ] && break
  echo "retry netlist $a"
done
grep -E '^CELL|CORE_' netlist_vivado.log
python3 $R/hardware/verification/power/mk_sim_wrap.py impl_funcsim.v sim_design_1.v
python3 $R/hardware/verification/power/mk_rtl_wrap.py impl_funcsim.v $T/hardware/rtl/weights/ rtl_wrap.v
echo "== vectors $(date +%T)"
$R/.venv/bin/python $R/software/analysis/power_vectors.py pipe_raw $T $R/data/board/testsets/Set5/baby_lr.raw $W/$t/vec
echo "== RTL check $(date +%T)"
rm -rf rtl; mkdir rtl; cd rtl
xvlog -sv -d PIPE_MODE=1 -d CLKNS=7.0 -d PADEN $T/hardware/rtl/common/*.v $T/hardware/rtl/pipe/*.v $T/hardware/rtl/top/*.v ../rtl_wrap.v ../sim_design_1.v $R/hardware/verification/power/tb_power.v > xvlog_out.log 2>&1
xelab -O2 -debug typical tb_power -timescale 1ns/1ps -s simr > xelab_out.log 2>&1
echo "run all; quit" > full.tcl
xsim simr -testplusarg VEC=$W/$t/vec -tclbatch full.tcl -log sim.log > /dev/null 2>&1
grep -E 'PASS|FAIL|INFO' sim.log
cd ..
echo "== netlist compile $(date +%T)"
rm -rf xi; mkdir xi; cd xi
xvlog -sv -d NETLIST -d PIPE_MODE=1 -d CLKNS=7.0 -d PADEN ../impl_funcsim.v ../sim_design_1.v $R/hardware/verification/power/tb_power.v $XILINX_VIVADO/data/verilog/src/glbl.v > xvlog_out.log 2>&1
xelab -O2 -L unisims_ver -debug typical tb_power glbl -timescale 1ns/1ps -s simi > xelab_out.log 2>&1
echo "== prep done $(date +%T)"
