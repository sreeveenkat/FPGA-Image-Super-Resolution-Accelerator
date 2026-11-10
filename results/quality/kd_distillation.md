# Knowledge-distillation rung on top of R3q (2026-11-10): no gain

Script `software/ai/training/run_kd.sh 1.0` (teacher `models/teacher.py`, 304,140 parameters, not deployable; `training/train_teacher.py`;
`train_rep.py --kd/--kd-alpha/--kd-window`). Teacher: 200k steps, val42 PSNR-Y 35.823 dB FP32 (`results/logs/kd_teacher_s0.log`).
Students: the deployed R3 network (plain SRNet + anchor, 2,620 parameters), fine-tuned 100k steps from `plainA_s<seed>.pt`, lr 5e-4, the same
11-px-halo crops; kdA: L1(HR) + 1.0 x L1(teacher); ctlA: L1(HR) only (control). Then QAT 40k steps as the ladder. Selection on val42 only.
INT8 (integer model), PSNR-Y dB, from `results/quality/q_<name>.json`:

| | val42 s0 / s1 | Set5 s0 / s1 | Set14 s0 / s1 | BSD100 s0 / s1 | mean val / Set5 / Set14 / BSD100 |
|---|---|---|---|---|---|
| R3q (`plainA_qat`, deployed recipe) | 34.027 / 34.205 | 35.906 / 36.197 | 31.974 / 32.123 | 30.913 / 31.010 | 34.116 / 36.051 / 32.048 / 30.962 |
| control (`ctlA_qat`) | 34.035 / 34.215 | 35.925 / 36.201 | 31.981 / 32.124 | 30.917 / 31.009 | 34.125 / 36.063 / 32.052 / 30.963 |
| distillation (`kdA_qat`) | 34.020 / 34.202 | 35.902 / 36.176 | 31.973 / 32.118 | 30.913 / 31.006 | 34.111 / 36.039 / 32.045 / 30.959 |

Result: distillation minus R3q = -0.005 / -0.012 / -0.003 / -0.003 dB; distillation minus control = -0.014 / -0.024 / -0.007 / -0.004 dB.
All differences are within the seed spread (0.18-0.29 dB between seeds). Distillation does not help this 2,620-parameter network; the extra
training alone gives at most +0.012 dB. Decision: keep the R3q weights; no weight export, no bitstream rebuild. Only alpha = 1.0 was tried.
