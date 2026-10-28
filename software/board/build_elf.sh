#!/usr/bin/env bash
# Build the board program for one SR_TEST variant into software/board/build/sr_app_t<N>.elf (git-ignored), against the m6_platform BSP.  Does not touch any Vitis project.
#   software/board/build_elf.sh <N> [extra gcc flags, e.g. -DSR_T3_FRAMES=3]
# SR_ELF_SUFFIX=_split (with -DSR_TIMING_SPLIT) names the output sr_app_t<N>_split.elf so the production ELF is not overwritten.
# Env overrides (for a fresh checkout / new platform): SR_BSP=<platform>/export/<name>/sw/standalone_ps7_cortexa9_0 (made by create_platform.py),
# SR_LSCRIPT=<linker script> (sr_app/lscript.ld in this repo is a copy of the Vitis sr_app one). Output always goes to software/board/build of THIS checkout.
set -eu
cd "$(dirname "$0")/../.."
N="${1:?usage: build_elf.sh <SR_TEST 0..3, 5, 10, 11> [extra flags]}"; shift || true
P="${SR_BSP:-$HOME/Desktop/venkat/vitis_workspace/m6_platform/export/m6_platform/sw/standalone_ps7_cortexa9_0}"
LS="${SR_LSCRIPT:-$HOME/Desktop/venkat/vitis_workspace/sr_app/src/lscript.ld}"
BIN="$HOME/Desktop/vivado_install/Vitis/2024.1/gnu/aarch32/lin/gcc-arm-none-eabi/bin"
mkdir -p software/board/build
EXTRA=""; [ "$N" = 11 ] && EXTRA="software/board/sr_app/sr_swmodel.c"   # T7 ARM-only baseline (needs sr_weights.h: software/host_tools/weights_h.py)
CF="-O2 -DSDT -mcpu=cortex-a9 -mfpu=vfpv3 -mfloat-abi=hard -g -Wall -Wextra -Werror=implicit-function-declaration -fno-tree-loop-distribute-patterns -specs=$P/Xilinx.spec -I$P/include -Isoftware/board -Isoftware/board/sr_app -DSR_TEST=$N $*"
"$BIN/arm-none-eabi-gcc" $CF -mcpu=cortex-a9 -mfpu=vfpv3 -mfloat-abi=hard -specs="$P/Xilinx.spec" -Wl,-T -Wl,"$LS" -L"$P/lib" \
    software/board/sr_app/main.c software/board/sr_app/sr_driver.c software/board/sr_app/sr_tiling.c $EXTRA \
    -Wl,--start-group,-lxilstandalone,-lxiltimer,-lxil,-lgcc,-lc,--end-group -o software/board/build/sr_app_t$N${SR_ELF_SUFFIX:-}.elf 2> software/board/build/link_t$N${SR_ELF_SUFFIX:-}.log || { grep -E "error|undefined" software/board/build/link_t$N${SR_ELF_SUFFIX:-}.log; exit 1; }
ls -l software/board/build/sr_app_t$N${SR_ELF_SUFFIX:-}.elf
