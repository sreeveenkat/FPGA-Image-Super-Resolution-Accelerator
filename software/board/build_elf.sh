#!/usr/bin/env bash
# Build the board program for one SR_TEST variant into software/board/build/sr_app_t<N>.elf (git-ignored), against the m6_platform BSP.  Does not touch any Vitis project.
#   software/board/build_elf.sh <N> [extra gcc flags, e.g. -DSR_T3_FRAMES=3]
set -eu
cd "$(dirname "$0")/../.."
N="${1:?usage: build_elf.sh <SR_TEST 0..3> [extra flags]}"; shift || true
P="$HOME/Desktop/venkat/vitis_workspace/m6_platform/export/m6_platform/sw/standalone_ps7_cortexa9_0"
LS="$HOME/Desktop/venkat/vitis_workspace/sr_app/src/lscript.ld"
BIN="$HOME/Desktop/vivado_install/Vitis/2024.1/gnu/aarch32/lin/gcc-arm-none-eabi/bin"
mkdir -p software/board/build
CF="-O2 -DSDT -mcpu=cortex-a9 -mfpu=vfpv3 -mfloat-abi=hard -g -Wall -Wextra -Werror=implicit-function-declaration -fno-tree-loop-distribute-patterns -specs=$P/Xilinx.spec -I$P/include -Isoftware/board -Isoftware/board/sr_app -DSR_TEST=$N $*"
"$BIN/arm-none-eabi-gcc" $CF -mcpu=cortex-a9 -mfpu=vfpv3 -mfloat-abi=hard -specs="$P/Xilinx.spec" -Wl,-T -Wl,"$LS" -L"$P/lib" \
    software/board/sr_app/main.c software/board/sr_app/sr_driver.c software/board/sr_app/sr_tiling.c \
    -Wl,--start-group,-lxilstandalone,-lxiltimer,-lxil,-lgcc,-lc,--end-group -o software/board/build/sr_app_t$N.elf 2> software/board/build/link_t$N.log || { grep -E "error|undefined" software/board/build/link_t$N.log; exit 1; }
ls -l software/board/build/sr_app_t$N.elf
