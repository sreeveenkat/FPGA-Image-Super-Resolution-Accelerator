#!/usr/bin/env bash
# RTL regression for M4 (Icarus Verilog).   Run from anywhere:  hardware/verification/run_tests.sh [quick|full]
#   quick (default): unit tests + all 4 layers on the small12 tile + on one real 70x70 tile (real_corner) + randomized-parameter layers (~30 s)
#   full           : unit tests + all 4 layers on every golden tile + randomized-parameter layers (~4 min)
# Needs: iverilog 12, data/golden/*.hex (software/ai/quantization/export_rtl.py), data/golden/unit/*.hex (gen_unit_vectors.py).
# Exit code 0 only if every test printed PASS and nothing printed FAIL.
set -u
cd "$(dirname "$0")/../.."
MODE="${1:-quick}"
PY=.venv/bin/python
TMP="$(mktemp -d)"
trap 'rm -rf "$TMP"' EXIT
RTL="hardware/rtl/common/mac_unit.v hardware/rtl/common/requant.v hardware/rtl/common/tile_ram.v hardware/rtl/common/weight_rom.v hardware/rtl/conv_engine/conv_engine.v"
TB=hardware/verification/tb
pass=0; fail=0

[ -f data/golden/small12_in.hex ] || $PY software/ai/quantization/export_rtl.py > /dev/null || exit 1
[ -f data/golden/unit/randL4_out.hex ] || $PY software/ai/quantization/gen_unit_vectors.py > /dev/null || exit 1

run() {  # run <name> <vvp-args...> ; counts PASS/FAIL lines
    out="$(vvp "$TMP/$1.vvp" "${@:2}" 2>&1 | grep -v 'finish called\|Not enough words')"
    echo "$out"
    if echo "$out" | grep -q '^FAIL' || ! echo "$out" | grep -q '^PASS'; then fail=$((fail+1)); else pass=$((pass+1)); fi
}
build() {  # build <name> <iverilog-args...>
    iverilog -g2012 -Wall -I . -o "$TMP/$1.vvp" "${@:2}" 2>"$TMP/$1.err" || { cat "$TMP/$1.err"; fail=$((fail+1)); return 1; }
}

echo "== unit tests"
for s in 1 2 3 8 21 23 24; do build rq$s -P tb_requant.SHIFT=$s hardware/rtl/common/requant.v $TB/tb_requant.v && run rq$s; done
build mac hardware/rtl/common/mac_unit.v $TB/tb_mac_unit.v && run mac
build ram hardware/rtl/common/tile_ram.v $TB/tb_tile_ram.v && run ram
for L in 1 2 3 4; do build wr$L -P tb_weight_rom.LAYER=$L hardware/rtl/common/weight_rom.v $TB/tb_weight_rom.v && run wr$L; done

echo "== conv engine, layer by layer against the golden hex dumps"
if [ "$MODE" = full ]; then
    TILES64="$(ls data/golden/*_in.hex | xargs -n1 basename | sed 's/_in.hex//' | grep -v '^small12$')"
else
    TILES64="real_corner"
fi
for L in 1 2 3 4; do
    build c6_$L -P tb_conv_layer.LAYER=$L -P tb_conv_layer.HC=6 $RTL $TB/tb_conv_layer.v && run c6_$L +TILE=small12
    build c64_$L -P tb_conv_layer.LAYER=$L -P tb_conv_layer.HC=64 $RTL $TB/tb_conv_layer.v || continue
    for t in $TILES64; do run c64_$L +TILE=$t; done
done

echo "== conv engine, randomized parameters (distinct M per channel, extreme values, NON-square 12x10 style tiles)"
for L in 1 2 3 4; do
    build r$L -P tb_conv_layer.LAYER=$L -P tb_conv_layer.HC=6 -P tb_conv_layer.HH=4 -P tb_conv_layer.RAND=1 $RTL $TB/tb_conv_layer.v && run r$L
done

echo "== summary: $pass test runs passed, $fail failed ($MODE)"
[ "$fail" -eq 0 ]
