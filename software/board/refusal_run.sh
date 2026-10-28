#!/usr/bin/env bash
# VERSION-refusal control with proof that nothing was written:  software/board/refusal_run.sh <name> <elf-of-another-design> <bitstream>
# Patterns are written to DDR before the run, read back before and after (xsdb mrd), compared on the PC with cmp; UART captured and searched for DMA / tile messages.
# Created 2026-10-28.  Files go to data/board/<date>/<name>*.
set -u
HERE=$(cd "$(dirname "$0")/../.." && pwd); cd "$HERE" || exit 2
NAME=$1; ELF=$2; BIT=$3; DAY=${DAY:-$(date +%F)}; DIR=data/board/$DAY; PAT=$DIR/refusal_patterns; OUT=$DIR/${NAME}_ddr
command -v xsdb >/dev/null || source ~/Desktop/vivado_install/Vitis/2024.1/settings64.sh >/dev/null 2>&1
mkdir -p "$PAT" "$OUT"
if [ ! -e "$PAT/pat_out.bin" ]; then
  .venv/bin/python - "$PAT" <<'PY'
import sys, numpy as np
d = sys.argv[1]
for name, size, seed in (("pat_out", 7340032, 11), ("pat_pad", 2097152, 12), ("pat_tin", 65536, 13), ("pat_tout", 65536, 14)):
    np.random.default_rng(seed).integers(0, 256, size, dtype=np.uint8).tofile(f"{d}/{name}.bin")
PY
fi
"$HERE/.venv/bin/python" software/board/uart_capture.py --out "$DIR/$NAME.log" --port /dev/ttyACM0 2> "$DIR/${NAME}_capture_err.txt" &
CPID=$!
for _ in $(seq 1 50); do grep -q "^# capture started" "$DIR/$NAME.log" 2>/dev/null && break; sleep 0.1; done
grep -q "^# capture started" "$DIR/$NAME.log" || { echo "UART capture did not start"; kill $CPID 2>/dev/null; exit 3; }
{ echo "name $NAME"; echo "date $(date --iso-8601=seconds)"; echo "elf $ELF $(md5sum < "$ELF" | cut -d' ' -f1)"; echo "bitstream $BIT $(md5sum < "$BIT" | cut -d' ' -f1)"; } > "$DIR/${NAME}_meta.txt"
SR_BIT=$BIT timeout --foreground -k 5 400 xsdb software/board/refusal_test.tcl "$ELF" data/board/div2k_img0193_lr_960x540.raw "$PAT" "$OUT" < /dev/null > "$DIR/${NAME}_xsdb.log" 2>&1
RC=$?; sleep 2; kill $CPID 2>/dev/null; wait $CPID 2>/dev/null
echo "xsdb_exit $RC" >> "$DIR/${NAME}_meta.txt"
echo "== xsdb exit $RC"; grep -E "^(GUARD|DMAMARK|REG|MARKER|READY|PATTERNS|ERROR)" "$DIR/${NAME}_xsdb.log"
echo "== DDR compare (cmp; no output = identical)"
for r in out pad tin tout; do
  cmp "$PAT/pat_$r.bin" "$OUT/pre_$r.bin"  && echo "pre  $r: identical to the pattern ($(stat -c%s "$OUT/pre_$r.bin") bytes)"
  cmp "$PAT/pat_$r.bin" "$OUT/post_$r.bin" && echo "post $r: identical to the pattern ($(stat -c%s "$OUT/post_$r.bin") bytes)"
done
echo "== UART"; grep ' | ' "$DIR/$NAME.log" | cut -d'|' -f2-
echo "== UART lines matching DMA/tile/frame/T1/T2/init ok: $(grep ' | ' "$DIR/$NAME.log" | grep -c -i -E 'init ok|T[0-9]+:|tile|frame|DMA start|CYCLES')"
