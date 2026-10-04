#!/usr/bin/env bash
# RTL regression for M4 (Icarus Verilog).   Run from anywhere:  hardware/verification/run_tests.sh [quick|full]
#   quick (default): unit tests + conv engine (all 4 layers on small12 and one real 70x70 tile + randomized layers) + the full tile core on the
#                    small tiles (HC=6) + the 20-tile seam test (HC=8)                                                  (~1 min)
#   full           : everything in quick, the conv engine on every golden tile, the full tile core at the real size (HC=64) on every golden
#                    tile with and without stalls, and the real-size seam test (2x2 tiles)                               (~20 min)
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
    TILES64="$(ls data/golden/*_in.hex | xargs -n1 basename | sed 's/_in.hex//' | grep -v '^small12')"
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

echo "== tile_ram_split"
build splitram hardware/rtl/common/tile_ram_split.v $TB/tb_tile_ram_split.v && run splitram

echo "== full tile core (sr_tile_core): stream in -> 4 layers -> pixel shuffle -> stream out"
CORE="hardware/rtl/common/mac_unit.v hardware/rtl/common/requant.v hardware/rtl/common/weight_rom.v hardware/rtl/common/tile_ram_split.v hardware/rtl/conv_engine/conv_engine.v hardware/rtl/sr_core/sr_tile_core.v"
build core6 -P tb_sr_tile.HC=6 $CORE $TB/tb_sr_tile.v && {
    run core6 +TILE=small12 +TILE2=small12b
    run core6 +TILE=small12b +TILE2=small12 +STALL=1
}

seam() {  # seam <hc> <lr_h> <lr_w> : tiled RTL output must equal the whole-image integer model
    local hc=$1 h=$2 w=$3 d=data/golden/seam
    $PY software/ai/quantization/seam_test.py gen --hc $hc --h $h --w $w > /dev/null || { fail=$((fail+1)); return; }
    build seam$hc -P tb_sr_tile.HC=$hc $CORE $TB/tb_sr_tile.v || return
    local bad=0 n=0
    for f in $d/hc${hc}_t*_in.hex; do
        b=$(basename $f _in.hex)
        out="$(vvp "$TMP/seam$hc.vvp" +NOEXTRA +IN=$f +OUT=$d/${b}_out.hex +DUMP=$d/${b}_rtl.hex 2>&1 | grep -v 'finish called\|Not enough words')"
        echo "$out" | grep -q '^PASS' && ! echo "$out" | grep -q '^FAIL' || { echo "$b: $out"; bad=$((bad+1)); }
        n=$((n+1))
    done
    echo "[seam hc=$hc] $n tiles simulated, $bad failed"
    if [ $bad -eq 0 ]; then
        out="$($PY software/ai/quantization/seam_test.py check --hc $hc)"; echo "$out"
        if echo "$out" | grep -q '^PASS'; then pass=$((pass+1)); else fail=$((fail+1)); fi
    else fail=$((fail+1)); fi
}
seam 8 37 29

if [ "$MODE" = full ]; then
    echo "== full tile core at the real size (HC=64)"
    build core64 -P tb_sr_tile.HC=64 $CORE $TB/tb_sr_tile.v && {
        for t in $TILES64; do run core64 +TILE=$t; done
        run core64 +TILE=real0 +STALL=1
        run core64 +TILE=noise +STALL=1
    }
    seam 64 100 90
fi

echo "== summary: $pass test runs passed, $fail failed ($MODE)"
[ "$fail" -eq 0 ]
