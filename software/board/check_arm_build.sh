#!/usr/bin/env bash
# Compile + link the board program (all SR_TEST variants: 0-3, 5 recovery test, 6-9 stale-state programs) with the Vitis ARM compiler against the BSP of a Vitis platform, WITHOUT a board.
#   software/board/check_arm_build.sh [platform_export_dir] [lscript.ld]
# Default platform: the M0 platform zed_platform of this machine.  Prints the program size and the highest address used (must stay below SR_IN_ADDR 0x10000000).
# Needs software/board/sr_app/golden_tile.h (python software/host_tools/golden_tile_h.py).  Objects go to a temp dir.  Exit code 0 = everything built.
set -eu
cd "$(dirname "$0")/../.."
P="${1:-$HOME/Desktop/venkat/vitis_workspace/zed_platform/export/zed_platform/sw/standalone_ps7_cortexa9_0}"
LS="${2:-$HOME/Desktop/venkat/vitis_workspace/dma_app/src/lscript.ld}"
BIN="$HOME/Desktop/vivado_install/Vitis/2024.1/gnu/aarch32/lin/gcc-arm-none-eabi/bin"
[ -d "$P/include" ] && [ -f "$LS" ] && [ -x "$BIN/arm-none-eabi-gcc" ] || { echo "SKIP: Vitis ARM toolchain / platform not found"; exit 0; }
[ -f software/board/sr_app/golden_tile.h ] || { echo "FAIL: golden_tile.h missing (run software/host_tools/golden_tile_h.py)"; exit 1; }
T="$(mktemp -d)"; trap 'rm -rf "$T"' EXIT
CF="-O2 -DSDT -mcpu=cortex-a9 -mfpu=vfpv3 -mfloat-abi=hard -g -Wall -Wextra -Werror=implicit-function-declaration -fno-tree-loop-distribute-patterns -specs=$P/Xilinx.spec -I$P/include -Isoftware/board -Isoftware/board/sr_app"
bad=0
for f in sr_tiling sr_driver; do
    "$BIN/arm-none-eabi-gcc" $CF -c software/board/sr_app/$f.c -o "$T/$f.o" 2> "$T/$f.log" || { cat "$T/$f.log"; bad=1; }
done
for t in 0 1 2 3 5 6 7 8 9 10; do
    "$BIN/arm-none-eabi-gcc" $CF -DSR_TEST=$t -c software/board/sr_app/main.c -o "$T/main$t.o" 2> "$T/m$t.log" || { grep -v redefined "$T/m$t.log"; bad=1; continue; }
    w=$(grep 'warning:' "$T"/*.log | grep -vc 'redefined\|previous definition' || true)
    "$BIN/arm-none-eabi-gcc" -mcpu=cortex-a9 -mfpu=vfpv3 -mfloat-abi=hard -specs="$P/Xilinx.spec" -Wl,-T -Wl,"$LS" -L"$P/lib" "$T/main$t.o" "$T/sr_driver.o" "$T/sr_tiling.o" \
        -Wl,--start-group,-lxilstandalone,-lxiltimer,-lxil,-lgcc,-lc,--end-group -o "$T/app$t.elf" 2> "$T/l$t.log" || { grep -v redefined "$T/l$t.log"; bad=1; continue; }
    top=$("$BIN/arm-none-eabi-nm" "$T/app$t.elf" | awk '$3=="_stack"{print $1}')
    echo "SR_TEST=$t: built and linked, warnings from our code: $w, program image ends at 0x$top (limit 0x10000000)"
    [ $((16#$top)) -lt $((16#10000000)) ] || { echo "FAIL: program overlaps the data buffers"; bad=1; }
done
[ $bad -eq 0 ] && echo "PASS check_arm_build" || { echo "FAIL check_arm_build"; exit 1; }
