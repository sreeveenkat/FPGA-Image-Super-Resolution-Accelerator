#!/usr/bin/env bash
# Fresh-load soak (needs the board): N complete program loads with run_board.tcl DEFAULT settings (PL isolation on, PL reprogrammed, ELF loaded twice),
# each one running T1 (golden tile + 20 repeats).  EVERY failure is counted and reported with the full register/debug dump (stat24..29, stat32..38);
# nothing is retried.  A stuck debug port is cleared with dap_reset.tcl (and counted as a failure).
#   software/board/fresh_load_soak.sh [N=100] [log=data/board/fresh_load_soak.log]
# Uses software/board/build/sr_app_t1.elf (build_elf.sh 1).  Exit 0 only if all N runs passed and VERSION was the expected one every time.
cd "$(dirname "$0")/../.."
source ~/Desktop/vivado_install/Vitis/2024.1/settings64.sh >/dev/null 2>&1
N="${1:-100}"; LOG="${2:-data/board/fresh_load_soak.log}"; D=data/board; B=software/board/build
EXPV="${SR_EXPECT_VERSION:-0x53524201}"
unset SR_SYSRST SR_NO_ISOLATE SR_NOFPGA SR_DOW2
ok=0; bad=0
echo "fresh_load_soak start $(date -Is) N=$N expected VERSION $EXPV" | tee -a "$LOG"
for i in $(seq 1 "$N"); do
    rm -f $D/fls_stats.txt
    m=$(timeout 300 xsdb software/board/run_board.tcl $B/sr_app_t1.elf - - $D/fls_stats.txt 2>&1 | grep -E "^marker|rror" | head -2 | tr '\n' ' ' | cut -c1-160)
    st() { grep -E "^$1=" $D/fls_stats.txt 2>/dev/null | cut -d= -f2; }
    r=0
    [ "$(st result)" = 0 ] || r=1
    [ "$(st stat6)" = 20 ] || r=1
    [ "$(st version)" = "$EXPV" ] || r=1
    if [ $r -eq 0 ]; then
        ok=$((ok+1)); echo "$i OK   cycles $(st stat0)-$(st stat1) version $(st version)" >> "$LOG"
    else
        bad=$((bad+1))
        echo "$i FAIL $m | $(grep -E '^(result|version|stat[0-6]|stat2[0-9]|stat3[2-8])=' $D/fls_stats.txt 2>/dev/null | paste -sd' ')" | tee -a "$LOG"
        grep -q "AHB AP\|no targets\|Cannot reset\|no ready marker" <<<"$m" && timeout 60 xsdb software/board/dap_reset.tcl >/dev/null 2>&1
    fi
    [ $((i % 10)) -eq 0 ] && echo "  progress $i/$N: $ok ok, $bad failed" | tee -a "$LOG"
done
echo "fresh_load_soak: $ok ok, $bad failed of $N ($(date -Is))" | tee -a "$LOG"
[ $bad -eq 0 ]
