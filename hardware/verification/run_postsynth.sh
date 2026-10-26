#!/usr/bin/env bash
# Simulate the SYNTHESIZED pipeline accelerator (branch `pipe`: sr_accel_top + sr_pipe_core, post-synthesis functional netlist) with Vivado's xsim, using the
# same self-checking top testbench (tb_sr_pipe_top.v, -d POSTSYNTH) on small frames: back to back, with random stalls, error codes 1-4 + frame-size refusal.
# The netlist is synthesized with MAXW = 32 (line buffers of 32 pixels, MAX_W = 26) so that it stays small; everything else is the real design
# (DSP inference, ROM contents from $readmemh, BRAM/LUTRAM mapping).  This catches synthesis surprises that RTL simulation cannot.
# Needs Vivado 2024.1.  Run from anywhere:  hardware/verification/run_postsynth.sh
set -u
cd "$(dirname "$0")/../.."
source "$HOME/Desktop/vivado_install/Vivado/2024.1/settings64.sh" > /dev/null 2>&1
B=hardware/vivado/build
N=$B/sr_pipe_small/postsynth.v
pass=0; fail=0
[ -f data/golden/pipe/gtile_meta.txt ] || .venv/bin/python software/ai/quantization/gen_pipe_vectors.py > /dev/null || exit 1
if [ ! -f $N ] || [ -n "$(find hardware/rtl -name '*.v' -newer $N -o -name '*.mem' -newer $N | head -1)" ]; then
    vivado -mode batch -nojournal -log $B/pipe_small.log -source hardware/vivado/scripts/synth_sr_pipe.tcl -tclargs 8.0 small > /dev/null 2>&1
fi
[ -f $N ] || { echo "FAIL: netlist not written (see $B/pipe_small.log)"; exit 1; }
nread=$(grep 'Synth 8-3876' $B/pipe_small.log | grep -o 'weights/[A-Za-z_0-9]*\.mem' | sort -u | wc -l)
ndsp=$(grep -c 'DSP48E1 #' $N || true)
echo "netlist: $nread of 12 weight files read during synthesis, $ndsp DSP48E1 instances"
[ "$nread" -eq 12 ] && [ "$ndsp" -eq 170 ] && pass=$((pass+1)) || { echo "FAIL: expected 12 weight files and 170 DSP48E1"; fail=$((fail+1)); }
W=$B/xsim_pipe; rm -rf $W; mkdir -p $W
( cd $W && xvlog -sv -i ../../../.. -d POSTSYNTH ../sr_pipe_small/postsynth.v ../../../verification/tb/tb_sr_pipe_top.v "$XILINX_VIVADO/data/verilog/src/glbl.v" > xvlog.log 2>&1 \
  && xelab -L unisims_ver -generic_top MAXW=32 tb_sr_pipe_top glbl -s sim > xelab.log 2>&1 ) || { echo "FAIL: xvlog/xelab (see $W)"; exit 1; }
runx() {  # runx <label> <plusargs...>
    out="$(xsim sim -R --xsimdir $W/xsim.dir "${@:2}" -log $W/xsim_$1.log 2>&1 | grep -E '^(PASS|FAIL)' )"
    echo "[netlist $1] $out"
    if echo "$out" | grep -q '^PASS' && ! echo "$out" | grep -q '^FAIL'; then pass=$((pass+1)); else fail=$((fail+1)); fi
}
F="-testplusarg F0=p13x7 -testplusarg F1=p1x1 -testplusarg F2=p2x3 -testplusarg F3=p5x4 -testplusarg F4=pramp -testplusarg F5=psat"
runx frames $F
runx stalls $F -testplusarg STALL=1
runx errors -testplusarg F0=p5x4 -testplusarg ERR=1
rm -f clockInfo.txt xsim.jou xsim_*.backup.jou webtalk*.jou webtalk*.log   # xsim writes these into the working directory (the project root)
echo "== post-synthesis summary: $pass passed, $fail failed"
[ "$fail" -eq 0 ]
