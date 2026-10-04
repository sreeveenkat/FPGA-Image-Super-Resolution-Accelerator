#!/usr/bin/env bash
# Simulate the SYNTHESIZED hardware (post-synthesis functional netlist) with Vivado's xsim, using the same self-checking testbench
# (tb_conv_layer, -DPOSTSYNTH) on the small12 tile: normal run, immediate re-run, and the reset-abort sweep.
# This catches synthesis surprises that RTL simulation cannot (e.g. a ROM initialisation Vivado silently ignores).
# Needs Vivado 2024.1.  Run from anywhere:  hardware/verification/run_postsynth.sh
set -u
cd "$(dirname "$0")/../.."
source "$HOME/Desktop/vivado_install/Vivado/2024.1/settings64.sh" > /dev/null 2>&1
B=hardware/vivado/build
pass=0; fail=0
for L in 1 2 3 4; do
    if [ ! -f $B/conv_L${L}_small/postsynth.v ]; then
        vivado -mode batch -nojournal -log $B/S$L.log -source hardware/vivado/scripts/synth_conv_engine.tcl -tclargs $L 10.0 small > /dev/null 2>&1
    fi
    W=$B/xsim_L$L; rm -rf $W; mkdir -p $W
    ( cd $W && xvlog -sv -i ../../../.. -d POSTSYNTH ../conv_L${L}_small/postsynth.v ../../../rtl/common/tile_ram.v ../../../verification/tb/tb_conv_layer.v \
          "$XILINX_VIVADO/data/verilog/src/glbl.v" > xvlog.log 2>&1 \
      && xelab -L unisims_ver -generic_top LAYER=$L -generic_top HC=6 tb_conv_layer glbl -s sim > xelab.log 2>&1 )
    out="$(xsim sim -R --xsimdir $W/xsim.dir -testplusarg TILE=small12 -log $W/xsim.log 2>&1 | grep -E '^(PASS|FAIL)|mismatch' )"
    echo "[post-synthesis L$L] $out"
    if echo "$out" | grep -q '^PASS' && ! echo "$out" | grep -q '^FAIL'; then pass=$((pass+1)); else fail=$((fail+1)); fi
done
# ---- the whole tile core (HC=6 geometry): stream in -> 4 layers -> pixel shuffle -> stream out, on the synthesized netlist
L=core
if [ ! -f $B/sr_tile_core_small/postsynth.v ]; then
    vivado -mode batch -nojournal -log $B/Score.log -source hardware/vivado/scripts/synth_sr_tile_core.tcl -tclargs 10.0 small > /dev/null 2>&1
fi
W=$B/xsim_core; rm -rf $W; mkdir -p $W
( cd $W && xvlog -sv -i ../../../.. -d POSTSYNTH ../sr_tile_core_small/postsynth.v ../../../verification/tb/tb_sr_tile.v \
      "$XILINX_VIVADO/data/verilog/src/glbl.v" > xvlog.log 2>&1 \
  && xelab -L unisims_ver -generic_top HC=6 tb_sr_tile glbl -s sim > xelab.log 2>&1 )
out="$(xsim sim -R --xsimdir $W/xsim.dir -testplusarg TILE=small12 -testplusarg TILE2=small12b -testplusarg SWEEP=6 -log $W/xsim.log 2>&1 | grep -E '^(PASS|FAIL)|mismatch|output ' )"
echo "[post-synthesis tile core HC=6] $out"
if echo "$out" | grep -q '^PASS' && ! echo "$out" | grep -q '^FAIL'; then pass=$((pass+1)); else fail=$((fail+1)); fi
rm -f clockInfo.txt xsim.jou xsim_*.backup.jou   # xsim writes these into the working directory (the project root)
echo "== post-synthesis summary: $pass passed, $fail failed"
[ "$fail" -eq 0 ]
