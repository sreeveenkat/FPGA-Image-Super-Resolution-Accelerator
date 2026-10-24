#!/usr/bin/env bash
# One board run with everything saved:  software/board/board_run.sh <name> <elf> <input.raw|-> <output.raw|-> [stats_file]
#   e.g.  software/board/board_run.sh t3_r0 software/board/build/sr_app_t3_20f.elf data/board/div2k_img0193_lr_960x540.raw data/board/$(date +%F)/t3_r0.raw
# Starts the UART capture first (software/board/uart_capture.py), then runs `xsdb software/board/run_board.tcl <elf> ...` with stdin closed, in the foreground
# process group and under a hard timeout (the demo.sh hang, docs/paper/rehearsal_2026-10-13_notes.md section 4), then stops the capture by PID.
# Saved under data/board/<date>/ :  <name>.log (UART, one timestamped line per line the ARM printed, incl. every 'frame N: total ... us' line of T3/T7),
#   <name>_xsdb.log (xsdb console), <name>_meta.txt (command, git revision, bitstream + ELF md5, VERSION family of the tree), <name>_stats.txt unless a stats file is given.
# Env: SR_TREE (root of the checkout to test; default = the checkout of this script) | SR_BIT (bitstream, as for run_board.tcl) | UART_PORT (default /dev/ttyACM0) | XSDB_TIMEOUT seconds (default 1000; run_board.tcl itself waits up to 900) |
#      SR_NO_UART=1 (run without capture; then the per-frame times are NOT saved) | DAY (default today, YYYY-MM-DD)
# UNTESTED ON THE BOARD.  Tested on the PC with a pseudo-terminal and a fake xsdb: software/board/test_uart_capture.py.
HERE=$(cd "$(dirname "$0")/../.." && pwd)    # checkout that holds this script (and uart_capture.py)
cd "${SR_TREE:-$HERE}" || exit 2              # SR_TREE=<root of another checkout, e.g. a sandbox>: run that tree's ELF/run_board.tcl, save under ITS data/board/<date>/
if [ $# -lt 4 ]; then echo "usage: software/board/board_run.sh <name> <elf> <input.raw|-> <output.raw|-> [stats_file]"; exit 2; fi
NAME=$1; ELF=$2; IN=$3; OUTRAW=$4
DAY=${DAY:-$(date +%F)}; DIR=data/board/$DAY; mkdir -p "$DIR"
STATS=${5:-$DIR/${NAME}_stats.txt}
PORT=${UART_PORT:-/dev/ttyACM0}; TMO=${XSDB_TIMEOUT:-1000}
UART_LOG=$DIR/$NAME.log; XLOG=$DIR/${NAME}_xsdb.log; META=$DIR/${NAME}_meta.txt
command -v xsdb >/dev/null || source ~/Desktop/vivado_install/Vitis/2024.1/settings64.sh >/dev/null 2>&1
command -v xsdb >/dev/null || { echo "board_run: xsdb not found"; exit 2; }
[ -e "$ELF" ] || { echo "board_run: missing ELF $ELF"; exit 2; }

{
    echo "name $NAME"; echo "date $(date --iso-8601=seconds)"; echo "cwd $(pwd)"
    echo "git $(git rev-parse --short HEAD 2>/dev/null) $(git rev-parse --abbrev-ref HEAD 2>/dev/null)"
    echo "elf $ELF $(md5sum < "$ELF" | cut -d' ' -f1)"
    BITF=${SR_BIT:-$(grep -oE '"/[^"]*design_1_wrapper[^"]*\.bit"' software/board/run_board.tcl | head -1 | tr -d '"')}   # the tree's own default, as run_board.tcl uses it
    echo "bitstream $BITF $(md5sum < "$BITF" 2>/dev/null | cut -d' ' -f1)"
    echo "command xsdb software/board/run_board.tcl $ELF $IN $OUTRAW $STATS"
} > "$META"

CPID=
if [ "${SR_NO_UART:-0}" = 1 ]; then
    echo "board_run: SR_NO_UART=1 -> NO UART CAPTURE, per-frame times will not be saved"
else
    "$HERE/.venv/bin/python" "$HERE/software/board/uart_capture.py" --out "$UART_LOG" --port "$PORT" 2> "$DIR/${NAME}_capture_err.txt" &
    CPID=$!
    for _ in $(seq 1 50); do grep -q "^# capture started" "$UART_LOG" 2>/dev/null && break; kill -0 $CPID 2>/dev/null || break; sleep 0.1; done
    if ! grep -q "^# capture started" "$UART_LOG" 2>/dev/null; then
        echo "board_run: UART capture did not start: $(cat "$DIR/${NAME}_capture_err.txt" 2>/dev/null)"
        echo "  close picocom / check the cable in J14 and 'ls $PORT', or set SR_NO_UART=1 to run without the per-frame log"
        exit 3
    fi
fi

date +%T; echo "board_run: $NAME started, xsdb log $XLOG"
timeout --foreground -k 5 "$TMO" xsdb software/board/run_board.tcl "$ELF" "$IN" "$OUTRAW" "$STATS" < /dev/null > "$XLOG" 2>&1
RC=$?
if [ -n "$CPID" ]; then sleep 2; kill "$CPID" 2>/dev/null; wait "$CPID" 2>/dev/null; fi   # by PID, after the last UART bytes arrived
echo "xsdb_exit $RC" >> "$META"
case $RC in 124|137) echo "board_run: FAIL xsdb did not exit within $TMO s (hard timeout); see $XLOG"; exit 1 ;; esac
grep -E "^marker|^stats|ERROR|rror" "$XLOG" | cut -c1-200 | head -5
[ -n "$CPID" ] && echo "UART: $(grep -c ' | ' "$UART_LOG") lines in $UART_LOG ($(grep -c 'frame [0-9]*: total' "$UART_LOG") per-frame lines)"
echo "board_run: $NAME exit $RC; files: $UART_LOG $XLOG $META $STATS"
exit $RC
