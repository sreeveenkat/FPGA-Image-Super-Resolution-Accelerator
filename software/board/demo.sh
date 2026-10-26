#!/usr/bin/env bash
# Review demo (needs the ZedBoard on JTAG + power).  One command, from a fresh power-up, ~1-2 minutes:
#   software/board/demo.sh            # default bitstream = 0602 (m6_sr_0602)
#   software/board/demo.sh --0601     # fallback bitstream 0601 (m6_sr)
#   software/board/demo.sh --no-view  # do not open the picture
# Steps: [1] board answers on JTAG  [2] FPGA programmed safely (PL isolation on) + VERSION  [3] golden tile (+20 repeats)
#        [4] full 960x540 -> 1920x1080 frame, byte-exact vs the integer model  [5] PNGs + side-by-side picture opened.
# Screen: one short line per step + big PASS/FAIL.  Everything else goes to data/board/demo/demo_<time>.log.
# Uses run_board.tcl unchanged (the same safe loading that passed the regression of 2026-10-12: isolation, L2 off, ELF loaded twice).
cd "$(dirname "$0")/../.." || exit 2
ROOT=$(pwd)
V=/home/sreevenkat/Desktop/venkat/vitis
BIT_0602=$V/m6_sr_0602/m6_sr.runs/impl_1/design_1_wrapper.bit
BIT_0601=$V/m6_sr/m6_sr.runs/impl_1/design_1_wrapper.bit
BIT=/home/sreevenkat/Desktop/venkat/R3q_125_artifacts/design_1_wrapper_R3q_125.bit; EXPV=0x53524301; VIEW=1   # r3q_125 sandbox: this tree's own bitstream (not built into the repo; see results/utilization/m6_system_R3q_125.md)
for a in "$@"; do
    case "$a" in
        --0601) BIT=$BIT_0601; EXPV=0x53520601 ;;
        --no-view) VIEW=0 ;;
        *) echo "usage: software/board/demo.sh [--0601] [--no-view]"; exit 2 ;;
    esac
done
D=data/board; OUT=$D/demo; B=software/board/build; PY=.venv/bin/python
LR_RAW=$D/div2k_img0193_lr_960x540.raw; EXP_RAW=$D/div2k_img0193_expected_1920x1080.raw
mkdir -p $OUT
STAMP=$(date +%Y%m%d_%H%M%S); LOG=$OUT/demo_$STAMP.log
T0=$(date +%s.%N)

if [ -t 1 ]; then G=$'\e[1;32m'; R=$'\e[1;31m'; Y=$'\e[1;33m'; N=$'\e[0m'; else G=; R=; Y=; N=; fi
el() { printf "%5.1f s" "$(echo "$(date +%s.%N) - $T0" | bc)"; }
say() { echo "$*"; echo "$*" | sed 's/\x1b\[[0-9;]*m//g' >> $LOG; }
banner() {  # banner PASS|FAIL text
    local c=$G; [ "$1" = FAIL ] && c=$R
    say ""; say "${c}############################################################${N}"
    say "${c}###  $1: $2${N}"; say "${c}############################################################${N}"; say ""
}
fail() {  # fail "<what>" "<fix lines...>"
    say "${R}  FAIL${N}  $1"; shift
    for l in "$@"; do say "        ${Y}fix:${N} $l"; done
    banner FAIL "DEMO STOPPED at $(el) - full log: $LOG"; exit 1
}
st() { grep -E "^$2=" "$1" 2>/dev/null | cut -d= -f2; }

say "SR accelerator demo  $(date '+%F %T')   bitstream $EXPV  ($BIT)"
say "full log: $LOG"
source ~/Desktop/vivado_install/Vitis/2024.1/settings64.sh >/dev/null 2>&1
command -v xsdb >/dev/null || fail "xsdb not found" "source ~/Desktop/vivado_install/Vitis/2024.1/settings64.sh"
for f in "$BIT" $B/sr_app_t1.elf $B/sr_app_t2.elf "$LR_RAW" $PY; do
    [ -e "$f" ] || fail "missing file $f" "ELFs: software/board/build_elf.sh 1 ; software/board/build_elf.sh 2" \
                                         "images: $PY software/host_tools/make_test_images.py" "bitstream: see docs/DEMO.md (fallback --0601)"
done
if [ ! -e "$EXP_RAW" ]; then
    say "  (expected output missing: computing it with the integer model, ~5 s)"
    $PY software/host_tools/expected_output.py $LR_RAW ${EXP_RAW%.raw} >> $LOG 2>&1 || fail "expected_output.py failed" "see $LOG"
fi
export SR_BIT=$BIT
unset SR_SYSRST SR_NO_ISOLATE SR_NOFPGA SR_DOW2 SR_VERIFY_DUMP

# ---- [1] JTAG ----------------------------------------------------------------------------------------------------------------------------------
say "[1/5] board on JTAG ..."
echo "== jtag_check" >> $LOG
timeout 60 xsdb software/board/jtag_check.tcl >> $LOG 2>&1
grep -q "^JTAG_OK" $LOG || fail "the board does not answer on JTAG ($(grep -m1 JTAG_FAIL $LOG))" \
    "is the board ON (power LED) and the micro-USB cable in the PROG/JTAG port (J17)?" \
    "pkill hw_server   (a stale JTAG server), then run the demo again" \
    "unplug + replug the PROG USB cable, wait 5 s, run again" \
    "power-cycle the board (SW8 off 10 s, on), run again" \
    "close Vitis/Vivado hardware manager if they hold the cable"
say "${G}  OK${N}    $(grep -m1 FPGA_STATE $LOG | sed 's/FPGA_STATE //')  ($(el))"

# ---- [2]+[3] program FPGA, VERSION, golden tile ------------------------------------------------------------------------------------------------
say "[2/5] programming the FPGA (PL isolation on) ..."
say "[3/5] golden tile 64x64 (+20 repeats) ..."
echo "== T1 run_board.tcl" >> $LOG
S1=$OUT/t1_$STAMP.txt
timeout 300 xsdb software/board/run_board.tcl $B/sr_app_t1.elf - - $S1 >> $LOG 2>&1
VER=$(st $S1 version)
[ -n "$VER" ] || fail "no result from the board (program did not finish)" \
    "xsdb software/board/dap_reset.tcl   (clears a stuck debug port), then run the demo again" \
    "if it fails again: power-cycle the board (SW8 off 10 s, on)"
if [ "$VER" = "$EXPV" ]; then say "${G}  OK${N}    FPGA programmed, VERSION $VER"
else fail "VERSION $VER, expected $EXPV (wrong bitstream?)" "check $BIT"; fi
if [ "$(st $S1 result)" = 0 ] && [ "$(st $S1 stat6)" = 20 ]; then
    say "${G}  PASS${N}  golden tile bit-exact, 20/20 repeats identical; CYCLES $(st $S1 stat2), tile time $(echo "scale=2; $(st $S1 stat5)/1000" | bc) ms  ($(el))"
else
    fail "golden tile: result $(st $S1 result), repeats $(st $S1 stat6)/20" "xsdb software/board/dap_reset.tcl, then run the demo again"
fi

# ---- [4] full frame ----------------------------------------------------------------------------------------------------------------------------
say "[4/5] full frame 960x540 -> 1920x1080 (135 tiles) ..."
echo "== T2 run_board.tcl" >> $LOG
S2=$OUT/t2_$STAMP.txt; O2=$OUT/fpga_1920x1080_$STAMP.raw
timeout 600 xsdb software/board/run_board.tcl $B/sr_app_t2.elf $LR_RAW $O2 $S2 >> $LOG 2>&1
[ "$(st $S2 result)" = 0 ] && [ -s $O2 ] || fail "frame: board result '$(st $S2 result)'" \
    "xsdb software/board/dap_reset.tcl, then run the demo again"
echo "== compare_raw" >> $LOG
$PY software/host_tools/compare_raw.py $O2 $EXP_RAW >> $LOG 2>&1; CMP=$?
FT=$(echo "scale=1; $(st $S2 stat0)/1000" | bc); FPS=$(printf "%.2f" "$(echo "scale=4; 1000000/$(st $S2 stat0)" | bc)")
if [ $CMP -eq 0 ]; then
    say "${G}  PASS${N}  frame BYTE-EXACT vs the integer model (6,220,800 bytes), checksum $(st $S2 fnv1a32), frame time $FT ms (= $FPS fps)  ($(el))"
else
    fail "frame NOT byte-exact vs the integer model (compare_raw exit $CMP, see $LOG)" "run the demo again; if it repeats use --0601"
fi

# ---- [5] pictures ------------------------------------------------------------------------------------------------------------------------------
say "[5/5] pictures ..."
PNG=$OUT/fpga_1920x1080_$STAMP.png; SBS=$OUT/side_by_side_$STAMP.png
{ $PY software/host_tools/raw2png.py $O2 $PNG && \
  $PY software/host_tools/side_by_side.py $LR_RAW $O2 $SBS "ZedBoard FPGA super-resolution x2 - output byte-exact vs the integer model"; } >> $LOG 2>&1 \
  || fail "PNG conversion failed (the board result above is still valid)" "see $LOG"
rm -f $O2   # 6 MB raw; the PNG is lossless
say "${G}  OK${N}    $SBS"
if [ $VIEW = 1 ]; then
    if [ -n "${DISPLAY:-}${WAYLAND_DISPLAY:-}" ]; then
        if command -v eog >/dev/null; then setsid eog "$SBS" >/dev/null 2>&1 < /dev/null &
        else setsid xdg-open "$SBS" >/dev/null 2>&1 < /dev/null & fi
        say "        opened in the image viewer"
    else
        say "        (no display: open $SBS by hand)"
    fi
fi
banner PASS "DEMO COMPLETE in $(el) - golden tile + full frame byte-exact, VERSION $VER"
exit 0
