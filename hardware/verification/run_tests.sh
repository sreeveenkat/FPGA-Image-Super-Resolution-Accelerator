#!/usr/bin/env bash
# RTL regression of the whole-frame PIPELINE (branch `pipe`, docs/ARCHITECTURE_PIPELINE.md; Icarus Verilog).  Run from anywhere:
#   hardware/verification/run_tests.sh [quick|full]
#   quick (default): requantizer + adder-tree unit tests; every stage with random weights (distinct M per channel, non-square frames) with stalls and
#                    reset aborts; every stage with the network weights on small frames; the accelerator top (AXI-Lite + AXI-Stream) on 9 frames back to
#                    back incl. every stage's output, with random stalls, error codes 1-4 and soft-reset aborts; board software (register header, host tools,
#                    C tiling + frame padding)                                                                                    (~8 min)
#   full           : everything in quick, the stages on the 64x48 real frame, the top on 64x48 / 37x29 / the golden tile with stalls, the board program
#                    build, and the pipeline mutation test (mutate_pipe.py)                                                       (~45 min)
#   The 960x540 frame is simulated separately in xsim (hardware/verification/run_fullframe.sh, ~10 min; Icarus would take ~90 min).
# Needs: iverilog 12, data/golden/unit/*.hex (gen_unit_vectors.py), data/golden/pipe/* (gen_pipe_vectors.py; made here if missing).
# There are no tiles, so there is no seam test: every top frame is compared with integer_reference.upscale() on the WHOLE frame, borders included.
# Exit code 0 only if every test printed PASS and nothing printed FAIL.
set -u
cd "$(dirname "$0")/../.."
MODE="${1:-quick}"
PY=.venv/bin/python
TMP="$(mktemp -d)"
trap 'rm -rf "$TMP"' EXIT
TB=hardware/verification/tb
PIPE="hardware/rtl/common/requant.v $(ls hardware/rtl/pipe/*.v | tr '\n' ' ')"
pass=0; fail=0

[ -f data/golden/unit/randL4_out.hex ] || $PY software/ai/quantization/gen_unit_vectors.py > /dev/null || exit 1
[ -f data/golden/pipe/gtile_meta.txt ] && [ -f data/golden/pipe/rand/randL4_meta.txt ] || $PY software/ai/quantization/gen_pipe_vectors.py > /dev/null || exit 1

run() {  # run <name> <vvp-args...> ; counts PASS/FAIL lines
    out="$(vvp -n "$TMP/$1.vvp" "${@:2}" 2>&1 | grep -v 'finish called\|Not enough words')"
    echo "$out"
    if echo "$out" | grep -q '^FAIL' || ! echo "$out" | grep -q '^PASS'; then fail=$((fail+1)); else pass=$((pass+1)); fi
}
build() {  # build <name> <iverilog-args...>
    iverilog -g2012 -Wall -I . -o "$TMP/$1.vvp" "${@:2}" 2>"$TMP/$1.err" || { cat "$TMP/$1.err"; fail=$((fail+1)); return 1; }
}
runpy() {  # runpy <cmd...> : one run, PASS when the output has a PASS line and no FAIL line
    out="$("$@" 2>&1)"; echo "$out" | tail -4
    if echo "$out" | grep -q '^FAIL' || ! echo "$out" | grep -q '^PASS'; then fail=$((fail+1)); else pass=$((pass+1)); fi
}

echo "== unit tests: requantizer (also the anchor add mode), adder tree, weight ROM files"
for s in 1 2 3 8 21 22 23 24 25; do build rq$s -P tb_requant.SHIFT=$s hardware/rtl/common/requant.v $TB/tb_requant.v && run rq$s; done
for s in 21 22 25; do build rqa$s -P tb_requant_add.SHIFT=$s hardware/rtl/common/requant.v $TB/tb_requant_add.v && run rqa$s; done
for n in 2 3 5 9 16 27; do build at$n -P tb_adder_tree.N=$n hardware/rtl/pipe/adder_tree.v $TB/tb_adder_tree.v && run at$n; done
build fifos hardware/rtl/pipe/anchor_fifo.v hardware/rtl/pipe/pipe_fifo.v $TB/tb_fifos.v && run fifos       # far past the pointer wrap (the 2026-10-26 deadlock)
out="$($PY software/ai/quantization/export_pipe.py --check)"; echo "$out"
if echo "$out" | grep -q FAIL; then fail=$((fail+1)); echo "FAIL wpipe_L*.mem are not up to date (run export_pipe.py)"; else pass=$((pass+1)); echo "PASS wpipe_L1..4.mem match weights_L1..4.mem"; fi

echo "== pipeline stages, random weights (distinct M per channel, both clamp ends, non-square frames), with stalls, 8 reset aborts, a slow consumer"
for L in 1 2 3 4; do
    build sr$L -P tb_pipe_stage.LAYER=$L -P tb_pipe_stage.REAL=0 $PIPE $TB/tb_pipe_stage.v && { run sr$L; run sr$L +STALL=1 +SWEEP=8; run sr$L +STALL=2; }
done

echo "== pipeline stages, network weights, against each layer's golden output of whole frames"
if [ "$MODE" = full ]; then FR="p13x7 preal2 preal"; else FR="p13x7"; fi
for L in 1 2 3 4; do
    build sn$L -P tb_pipe_stage.LAYER=$L -P tb_pipe_stage.REAL=1 $PIPE $TB/tb_pipe_stage.v || continue
    for f in $FR; do run sn$L +FRAME=$f; done
    run sn$L +FRAME=pramp +STALL=1
done

echo "== accelerator top (sr_accel_top + sr_pipe_core): AXI4-Lite registers + AXI-Stream, driven like the ARM/DMA, whole frames vs integer_reference.upscale"
SMALL="+F0=p13x7 +F1=p1x1 +F2=p2x3 +F3=p5x4 +F4=pramp +F5=psat +F6=preal2 +F7=p2x3"
build top $PIPE hardware/rtl/top/sr_accel_top.v $TB/tb_sr_pipe_top.v && {
    run top $SMALL +LAYERS=1
    run top $SMALL +STALL=1
    run top +F0=p13x7 +ERR=1 +SWEEP=6
    run top +F0=gtile
    run top +F0=pramp +F1=p13x7 +STALL=2                    # slow DMA sink: output banks and FIFOs fill, back-pressure through every stage
    if [ "$MODE" = full ]; then
        run top +F0=preal +F1=gtile +LAYERS=1
        run top +F0=preal +F1=preal2 +STALL=1
        run top +F0=preal2 +SWEEP=12 +STALL=1
    fi
}

echo "== board software (no board): register header vs Verilog, host tools, C tiling code + frame padding"
[ -f data/board/set14_baboon_lr_128x128.raw ] || $PY software/host_tools/make_test_images.py > /dev/null || fail=$((fail+1))
runpy python3 software/board/test_regs.py
runpy $PY software/host_tools/test_host_tools.py
if [ "$MODE" = full ]; then runpy $PY software/board/test_tiling.py; else runpy $PY software/board/test_tiling.py --quick; fi

if [ "$MODE" = full ]; then
    echo "== board program: compile + link with the Vitis ARM toolchain against the M0 platform BSP (skipped when the toolchain is not installed)"
    out="$(software/board/check_arm_build.sh 2>&1)"; echo "$out"
    if echo "$out" | grep -q '^SKIP'; then :; elif echo "$out" | grep -q '^PASS'; then pass=$((pass+1)); else fail=$((fail+1)); fi
    echo "== frames at the counter limits in xsim: 192x192 and 960x24 (> 8,192 anchor pixels: FIFO pointer wrap), 1018x4 (MAX_W: last line-buffer/bank address), 1x4096 (MAX_H)"
    for fr in p192 pw960x24 pmaxw ptall; do
        out="$(hardware/verification/run_fullframe.sh $fr 2>&1)"; echo "$out" | grep -E '^(PASS|FAIL)'
        if echo "$out" | grep -q '^PASS' && ! echo "$out" | grep -q '^FAIL'; then pass=$((pass+1)); else fail=$((fail+1)); fi
    done
    echo "== pipeline mutation test: deliberate RTL defects, each must be caught (mutate_pipe.py exits 0 only then)"
    out="$($PY hardware/verification/mutate_pipe.py 2>&1)"; echo "$out"            # the whole mutant table (runpy would keep only the last lines)
    if echo "$out" | grep -q '^PASS pipeline mutation test'; then pass=$((pass+1)); else fail=$((fail+1)); fi
fi

echo "== summary: $pass test runs passed, $fail failed ($MODE)"
[ "$fail" -eq 0 ]
