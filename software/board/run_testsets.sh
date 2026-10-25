#!/usr/bin/env bash
# M7 (needs the board): run every test-set image (data/board/testsets/<set>/<stem>_lr.raw, made by software/host_tools/board_testsets.py prep) through T2 on
# the board with run_board.tcl default settings; the output goes to <stem>_board.raw.  Every run is checked byte-exact against <stem>_exp.raw right away;
# a failure is counted and reported, never retried.  Afterwards: board_testsets.py eval.
#   software/board/run_testsets.sh [log=data/board/testsets/run.log]
cd "$(dirname "$0")/../.."
source ~/Desktop/vivado_install/Vitis/2024.1/settings64.sh >/dev/null 2>&1
LOG="${1:-data/board/testsets/run.log}"; B=software/board/build; T=data/board/testsets
EXPV="${SR_EXPECT_VERSION:-0x53524201}"
unset SR_SYSRST SR_NO_ISOLATE SR_NOFPGA SR_DOW2
ok=0; bad=0; n=0
echo "run_testsets start $(date -Is)" | tee -a "$LOG"
for f in $T/Set5/*_lr.raw $T/Set14/*_lr.raw $T/BSD100/*_lr.raw; do
    n=$((n+1)); s=${f%_lr.raw}
    rm -f ${s}_board.raw $T/stats.txt
    m=$(timeout 300 xsdb software/board/run_board.tcl $B/sr_app_t2.elf $f ${s}_board.raw $T/stats.txt 2>&1 | grep -E "^marker|rror" | head -2 | tr '\n' ' ' | cut -c1-160)
    v=$(grep -E "^version=" $T/stats.txt 2>/dev/null | cut -d= -f2)
    if [ "$v" = "$EXPV" ] && .venv/bin/python software/host_tools/compare_raw.py ${s}_board.raw ${s}_exp.raw >/dev/null 2>&1; then
        ok=$((ok+1)); echo "$n OK   ${s#$T/} $(grep -E '^(tiles|fnv1a32|stat0)=' $T/stats.txt | paste -sd' ')" >> "$LOG"
    else
        bad=$((bad+1)); echo "$n FAIL ${s#$T/} version $v | $m | $(grep -E '^(result|stat2[4-9]|stat3[2-8])=' $T/stats.txt 2>/dev/null | paste -sd' ')" | tee -a "$LOG"
        grep -q "AHB AP\|no targets\|Cannot reset\|no ready marker" <<<"$m" && timeout 60 xsdb software/board/dap_reset.tcl >/dev/null 2>&1
    fi
    [ $((n % 10)) -eq 0 ] && echo "  progress $n: $ok ok, $bad failed" | tee -a "$LOG"
done
echo "run_testsets: $ok byte-exact, $bad failed of $n ($(date -Is))" | tee -a "$LOG"
[ $bad -eq 0 ]
