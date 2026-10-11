#!/usr/bin/env bash
# Repeated normal runs through run_board.tcl (needs the board): T1, T2 128x128, T2 960x540 in turn, N rounds; every run is checked (marker result, byte-exact output,
# program image in DDR intact).  A stuck debug port is reported and cleared with dap_reset.tcl.  Environment variables are passed on (SR_SYSRST, SR_DOW2, ...).
#   software/board/soak_test.sh [rounds=5]
cd "$(dirname "$0")/../.."
source ~/Desktop/vivado_install/Vitis/2024.1/settings64.sh >/dev/null 2>&1
N="${1:-5}"; D=data/board; B=software/board/build; ok=0; bad=0
one() {   # $1 = elf number, $2 = input or -, $3 = expected or -
    rm -f $D/soak_out.raw $D/soak_img.bin $D/soak_stats.txt
    local out=-; [ "$2" != - ] && out=$D/soak_out.raw
    local m; m=$(SR_VERIFY_DUMP=$D/soak_img.bin SR_VERIFY_BYTES=$(python3 software/board/verify_load.py --bytes $B/sr_app_t$1.elf) \
        timeout 300 xsdb software/board/run_board.tcl $B/sr_app_t$1.elf $2 $out $D/soak_stats.txt 2>&1 | grep -E "^marker|rror" | head -1 | cut -c1-100)
    local v; v=$(python3 software/board/verify_load.py $B/sr_app_t$1.elf $D/soak_img.bin 2>/dev/null | tail -1 | cut -c1-40)
    local r=0; grep -q "^result=0" $D/soak_stats.txt 2>/dev/null || r=1
    if [ "$3" != - ]; then .venv/bin/python software/host_tools/compare_raw.py $D/soak_out.raw $3 >/dev/null 2>&1 || r=1; fi
    if [ $r -eq 0 ]; then ok=$((ok+1)); echo "OK   t$1 $(basename $2) | $v"
    else bad=$((bad+1)); echo "FAIL t$1 $(basename $2) | $m | $v | $(grep -E 'stat2[4-9]=' $D/soak_stats.txt 2>/dev/null | paste -sd' ')"
         grep -q "AHB AP\|no targets\|Cannot reset" <<<"$m" && timeout 60 xsdb software/board/dap_reset.tcl >/dev/null 2>&1; fi
}
for i in $(seq 1 "$N"); do
    one 1 - -
    one 2 $D/set14_baboon_lr_128x128.raw $D/set14_baboon_expected_256x256.raw
    one 2 $D/div2k_img0193_lr_960x540.raw $D/div2k_img0193_expected_1920x1080.raw
done
echo "soak_test: $ok ok, $bad failed (SR_SYSRST=${SR_SYSRST:-0} SR_DOW2=${SR_DOW2:-1} SR_NOFPGA=${SR_NOFPGA:-0})"
[ $bad -eq 0 ]
