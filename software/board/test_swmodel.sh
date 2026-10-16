#!/usr/bin/env bash
# PC check of the ARM-only baseline (sr_app/sr_swmodel.c, board test T7): run it on the 960x540 board test image and on the 128x128 Set14 crop and require
# a byte-exact match with the integer model's expected outputs (data/board/*_expected_*.raw; made here with make_test_images.py / expected_output.py if missing).
# Built twice: with ASan + UBSan (correctness) and with -O2 (PC time).  Exit 0 = all byte-exact.
set -eu
cd "$(dirname "$0")/../.."
P=.venv/bin/python
B=software/board/build/pc; mkdir -p "$B"
$P software/host_tools/weights_h.py > /dev/null
SRC="software/board/pc_test/swmodel_tool.c software/board/sr_app/sr_swmodel.c software/board/sr_app/sr_tiling.c"
INC="-Isoftware/board -Isoftware/board/sr_app"
gcc -std=c11 -O1 -g -Wall -Wextra -Werror -fsanitize=address,undefined -fno-sanitize-recover=all $INC $SRC -o $B/swmodel_san
gcc -std=c11 -O2 -Wall -Wextra -Werror $INC $SRC -o $B/swmodel_o2
fail=0
for pair in "div2k_img0193_lr_960x540 div2k_img0193_expected_1920x1080" "set14_baboon_lr_128x128 set14_baboon_expected_256x256"; do
    set -- $pair
    in=data/board/$1.raw; exp=data/board/$2.raw
    [ -f "$in" ] || $P software/host_tools/make_test_images.py > /dev/null
    [ -f "$exp" ] || $P software/host_tools/expected_output.py "$in" "data/board/$2" > /dev/null
    [ -f "$in" ] && [ -f "$exp" ] || { echo "FAIL: missing $in or $exp"; fail=1; continue; }
    for exe in swmodel_san swmodel_o2; do
        out=$B/$1_$exe.raw
        $B/$exe "$in" "$out" | sed "s/^/  [$exe] /"
        if cmp -s "$out" "$exp"; then echo "PASS $exe $1: byte-exact vs $2"; else echo "FAIL $exe $1: differs from $2"; fail=1; fi
    done
done
exit $fail
