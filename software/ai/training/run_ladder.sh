#!/usr/bin/env bash
# The image-quality ladder, one (rung, seed) pipeline per call.  Run from the project root:
#   software/ai/training/run_ladder.sh <rung> <seed>      rung = plain | rep | plainA | repA   (A = nearest-neighbour anchor)
# train FP32 -> evaluate (FP32 + PTQ INT8) -> QAT (per-layer weight scales, the RTL scheme) -> evaluate (INT8 only).
# All choices (checkpoint, QAT step) are made on the 42 clean validation images; the test sets are only evaluated at the end of each stage.
set -eu
rung=$1; seed=$2
PY=.venv/bin/python
Q=software/ai/checkpoints/q
mkdir -p $Q results/logs
name=${rung}_s${seed}
case $rung in
  plain)  flags="--model plain" ;;
  rep)    flags="--model rep" ;;
  plainA) flags="--model plain --anchor" ;;
  repA)   flags="--model rep --anchor" ;;
esac
if [ ! -f $Q/$name.pt ]; then
  $PY software/ai/training/train_rep.py $flags --steps 300000 --lr 2e-3 --val-every 10000 --seed $seed --out $Q/$name.pt > results/logs/ladder_$name.log 2>&1
fi
[ -f results/quality/q_$name.json ] || $PY software/ai/evaluation/eval_candidate.py --name $name --ckpt $Q/$name.pt --no-bicubic >> results/logs/ladder_$name.log 2>&1
qn=${rung}_qat_s${seed}
if [ ! -f $Q/$qn.pt ]; then
  case $rung in rep|repA) src="--rep-ckpt $Q/${name}_rep.pt" ;; *) src="--ckpt $Q/$name.pt" ;; esac
  $PY software/ai/quantization/qat.py $src --steps 40000 --lr 3e-4 --val-every 5000 --seed $seed --out $Q/$qn.pt > results/logs/ladder_$qn.log 2>&1
fi
[ -f results/quality/q_$qn.json ] || $PY software/ai/evaluation/eval_candidate.py --name $qn --ckpt $Q/$qn.pt --no-fp32 --no-bicubic >> results/logs/ladder_$qn.log 2>&1
echo "$name pipeline done"
