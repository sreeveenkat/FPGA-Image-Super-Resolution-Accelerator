#!/usr/bin/env bash
# The real-size frame: 960 x 540 (DIV2K img0193, the board's T2/T3 input) through the whole pipeline accelerator in xsim (RTL), every output beat and every
# stage's output compared with the integer model (tb_sr_pipe_top.v +LAYERS=1), CYCLES printed.  Icarus would need ~90 min for the ~8.4 M cycles.
# Needs Vivado 2024.1 and data/board/div2k_img0193_lr_960x540.raw (software/host_tools/make_test_images.py).
#   hardware/verification/run_fullframe.sh [frame=pfull] [extra plusargs, e.g. -testplusarg STALL=1]
set -u
cd "$(dirname "$0")/../.."
source "$HOME/Desktop/vivado_install/Vivado/2024.1/settings64.sh" > /dev/null 2>&1
FR="${1:-pfull}"; shift || true
[ -f data/golden/pipe/pfull_meta.txt ] || .venv/bin/python software/ai/quantization/gen_pipe_vectors.py --full > /dev/null || exit 1
W=hardware/vivado/build/xsim_frame_$FR; rm -rf $W; mkdir -p $W          # one folder per frame: parallel runs must not delete each other's build
( cd $W && xvlog -sv -i ../../../.. ../../../rtl/common/requant.v ../../../rtl/pipe/*.v ../../../rtl/top/sr_accel_top.v ../../../verification/tb/tb_sr_pipe_top.v \
      > xvlog.log 2>&1 && xelab -O3 -timescale 1ns/1ps tb_sr_pipe_top -s fullframe > xelab.log 2>&1 ) || { echo "FAIL xvlog/xelab (see $W)"; exit 1; }
start=$(date +%s)
out="$(xsim fullframe --xsimdir $W/xsim.dir -R -testplusarg F0=$FR -testplusarg LAYERS=1 "$@" -log $W/xsim.log 2>&1 | grep -E '^(PASS|FAIL)')"
echo "$out"
echo "(xsim wall time $(( $(date +%s) - start )) s)"
rm -f xsim.jou xsim_*.backup.jou webtalk*.jou webtalk*.log xelab.pb xvlog.pb
echo "$out" | grep -q '^PASS' && ! echo "$out" | grep -q '^FAIL'
