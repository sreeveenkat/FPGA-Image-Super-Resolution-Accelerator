#!/usr/bin/env bash
# Distillation rung (2026-11-10) on top of R3 (plain SRNet + anchor = the network in the `pipe` / `pipe2` hardware). Run from the project root:
#   software/ai/training/run_kd.sh [alpha=1.0]
# 1. teacher (models/teacher.py, ~304k params, not deployable), 200k steps, seed 0, selected on val42
# 2. per seed s in 0 1, both starting from the R3 FP32 checkpoint plainA_s<s>.pt, 100k steps, lr 5e-4, the SAME 11-px-halo crops:
#      kdA_s<s>   loss = L1(HR) + alpha * L1(teacher)        ctlA_s<s>   loss = L1(HR) only (control: is any gain just "more training"?)
# 3. QAT exactly as the ladder (40k steps, lr 3e-4, per-layer weight scales = the RTL scheme), then eval_candidate (INT8 = integer model).
# Every choice (checkpoint, QAT step) uses the 42 clean validation images only; Set5/Set14/BSD100 are only evaluated (eval_candidate).
set -eu
ALPHA=${1:-1.0}
PY=.venv/bin/python
Q=software/ai/checkpoints/q
mkdir -p $Q results/logs
T=$Q/teacher_s0.pt
[ -f $T ] || $PY software/ai/training/train_teacher.py --steps 200000 --seed 0 --out $T > results/logs/kd_teacher_s0.log 2>&1
for s in 0 1; do
  for kind in kdA ctlA; do
    n=${kind}_s$s
    if [ ! -f $Q/$n.pt ]; then
      if [ $kind = kdA ]; then extra="--kd $T --kd-alpha $ALPHA"; else extra=""; fi
      $PY software/ai/training/train_rep.py --model plain --anchor --init $Q/plainA_s$s.pt $extra --kd-window --steps 100000 --lr 5e-4 \
          --val-every 5000 --seed $s --out $Q/$n.pt > results/logs/kd_$n.log 2>&1
    fi
    [ -f results/quality/q_$n.json ] || $PY software/ai/evaluation/eval_candidate.py --name $n --ckpt $Q/$n.pt --no-bicubic >> results/logs/kd_$n.log 2>&1
    qn=${kind}_qat_s$s
    [ -f $Q/$qn.pt ] || $PY software/ai/quantization/qat.py --ckpt $Q/$n.pt --steps 40000 --lr 3e-4 --val-every 5000 --seed $s --out $Q/$qn.pt > results/logs/kd_$qn.log 2>&1
    [ -f results/quality/q_$qn.json ] || $PY software/ai/evaluation/eval_candidate.py --name $qn --ckpt $Q/$qn.pt --no-fp32 --no-bicubic >> results/logs/kd_$qn.log 2>&1
    echo "$n done"
  done
done
echo "KD rung done"
