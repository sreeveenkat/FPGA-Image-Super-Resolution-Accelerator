#!/usr/bin/env bash
# Simulation demo (no board needed):
#   hardware/verification/demo_sim.sh            # 1) run_tests.sh quick (~3 min)  2) one small tile (HC=6) through sr_accel_top with a waveform  3) GTKWave
#   hardware/verification/demo_sim.sh --wave     # skip the regression, only the waveform tile
# The tile is the normal self-checking testbench tb_sr_accel_top (HC=6, golden tile small12, output compared bit-exact with the integer model);
# tb/demo_dump.v adds the VCD as a second top level.  Waveform: hardware/verification/build/demo_sim.vcd, layout: hardware/verification/demo_sim.gtkw.
set -u
cd "$(dirname "$0")/../.."
if [ -t 1 ]; then G=$'\e[1;32m'; R=$'\e[1;31m'; N=$'\e[0m'; else G=; R=; N=; fi
BUILD=hardware/verification/build; mkdir -p $BUILD
if [ "${1:-}" != "--wave" ]; then
    echo "== [1/2] RTL regression: hardware/verification/run_tests.sh quick (~3 min, full output in $BUILD/run_tests_quick.log)"
    t0=$(date +%s)
    hardware/verification/run_tests.sh quick > $BUILD/run_tests_quick.log 2>&1; rc=$?
    tail -3 $BUILD/run_tests_quick.log
    if [ $rc -eq 0 ]; then echo "${G}PASS${N}  regression ($(( $(date +%s) - t0 )) s)"; else echo "${R}FAIL${N}  regression (exit $rc), see $BUILD/run_tests_quick.log"; exit 1; fi
fi
echo "== [2/2] one tile with waveform (HC=6: 12x12 input incl. halo -> 12x12 output, sr_accel_top driven like the ARM + DMA)"
AXIS="hardware/rtl/common/mac_unit.v hardware/rtl/common/requant.v hardware/rtl/common/weight_rom.v hardware/rtl/common/tile_ram_split.v hardware/rtl/conv_engine/conv_engine.v hardware/rtl/sr_core/sr_tile_core.v hardware/rtl/axi_wrapper/sr_axis_wrapper.v"
iverilog -g2012 -I hardware/verification -o $BUILD/demo_sim.vvp -P tb_sr_accel_top.HC=6 -s tb_sr_accel_top -s demo_dump \
    $AXIS hardware/rtl/top/sr_accel_top.v hardware/verification/tb/tb_sr_accel_top.v hardware/verification/tb/demo_dump.v || { echo "${R}FAIL${N} compile"; exit 1; }
out=$(vvp $BUILD/demo_sim.vvp +TILE=small12 +NOEXTRA 2>&1 | grep -v "finish called\|Not enough words\|VCD info")
echo "$out" | tail -4
if echo "$out" | grep -q PASS && ! echo "$out" | grep -q FAIL; then echo "${G}PASS${N}  tile bit-exact, waveform $BUILD/demo_sim.vcd ($(du -h $BUILD/demo_sim.vcd | cut -f1))"
else echo "${R}FAIL${N}  tile simulation"; exit 1; fi
if command -v gtkwave >/dev/null; then
    setsid gtkwave $BUILD/demo_sim.vcd hardware/verification/demo_sim.gtkw >/dev/null 2>&1 < /dev/null &
    echo "GTKWave opened with the saved layout (hardware/verification/demo_sim.gtkw)"
else
    echo "GTKWave is not installed:  sudo apt install gtkwave   then:  gtkwave $BUILD/demo_sim.vcd hardware/verification/demo_sim.gtkw"
fi
