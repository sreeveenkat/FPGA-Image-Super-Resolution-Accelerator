#!/usr/bin/env bash
# Stale-state recovery test (needs the board): interrupt a program in the middle of a DMA transfer, then run a fresh 128x128 T2 and compare byte-exact. NO system reset.
#   software/board/stale_test.sh [nofpga]      "nofpga" = the bitstream is NOT reloaded between the two runs (the PL keeps its stale state)
# Scenarios: T2 on 960x540 with the CPU stopped after <delay> ms (the PL finishes that tile by itself), and the stale-state programs SR_TEST=9 (MM2S blocked, core not started),
# 7 (core stuck mid-LOAD), 6 (core stuck mid-OUTPUT), 8 (tile started, not waited for).  After a failed fresh run the board is reset with dap_reset.tcl so the test can go on.
# Uses software/board/build/sr_app_t{2,8,9}.elf (build_elf.sh) and the files in data/board/.  Exit 0 only if every fresh run was byte-exact.
cd "$(dirname "$0")/../.."
source ~/Desktop/vivado_install/Vitis/2024.1/settings64.sh >/dev/null 2>&1
[ "${1:-}" = nofpga ] && export SR_NOFPGA=1
unset SR_SYSRST
D=data/board; B=software/board/build; ok=0; bad=0
fresh() {   # $1 = label
    rm -f $D/stale_out.raw $D/stale_img.bin
    local m v; m=$(SR_VERIFY_DUMP=$D/stale_img.bin SR_VERIFY_BYTES=$(python3 software/board/verify_load.py --bytes $B/sr_app_t2.elf) \
        timeout 120 xsdb software/board/run_board.tcl $B/sr_app_t2.elf $D/set14_baboon_lr_128x128.raw $D/stale_out.raw $D/stale_stats.txt 2>&1 | grep -E "^marker|rror" | head -2 | tr '\n' ' ')
    v=$(python3 software/board/verify_load.py $B/sr_app_t2.elf $D/stale_img.bin 2>&1 | tail -1)
    if .venv/bin/python software/host_tools/compare_raw.py $D/stale_out.raw $D/set14_baboon_expected_256x256.raw >/dev/null 2>&1; then echo "OK   $1 -> fresh run byte-exact; $v"; ok=$((ok+1)); else echo "FAIL $1 -> fresh run: $m; $v; dump: $(grep -E 'stat2[4-9]=' $D/stale_stats.txt 2>/dev/null | paste -sd' ')"; bad=$((bad+1)); timeout 60 xsdb software/board/dap_reset.tcl >/dev/null 2>&1; fi
}
snap() { grep -E "^(PC|MM2S|S2MM|STATUS|ERROR_CODE|CYCLES)" | sed 's/^PC: pc: /PC=/' | paste -sd' '; }
for d in 300 517 733; do
    echo "  [T2 960x540 stopped at $d ms] $(timeout 120 xsdb software/board/interrupt_test.tcl $B/sr_app_t2.elf $D/div2k_img0193_lr_960x540.raw $d 2>&1 | snap)"
    fresh "T2 stopped at $d ms"
done
for t in 9 7 6 8; do
    echo "  [SR_TEST=$t stale program, state when stopped] $(timeout 120 xsdb software/board/interrupt_test.tcl $B/sr_app_t$t.elf - 300 2>&1 | snap)"
    fresh "SR_TEST=$t program"
done
echo "stale_test: $ok ok, $bad failed (mode: $([ -n "${SR_NOFPGA:-}" ] && echo "bitstream NOT reloaded" || echo "bitstream reloaded"), $([ "${SR_SYSRST:-0}" = 1 ] && echo "system reset before each load" || echo "no system reset"))"
[ $bad -eq 0 ]
