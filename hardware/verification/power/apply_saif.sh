#!/usr/bin/env bash
# apply_saif.sh <design> <saif> <out_tag>   (2026-11-19; like power_saif_retry.sh but 900 s per attempt for the larger pipe3/pipe4 checkpoints)
cd ~/Desktop/venkat/sem_project_all; source ~/Desktop/vivado_install/Vivado/2024.1/settings64.sh >/dev/null 2>&1
R=results/power_estimate/raw; W=~/Desktop/venkat/power_estimate_work
for a in 1 2 3 4; do
  timeout -k 5 900 vivado -mode batch -nojournal -nolog -source hardware/vivado/scripts/power_saif.tcl -tclargs $W/$1/routed_copy.dcp $2 tb_power $R/$3 > $R/${3}_vivado.log 2>&1 < /dev/null
  [ -s $R/${3}_power.txt ] && grep -q "Total On-Chip" $R/${3}_power.txt && [ $R/${3}_power.txt -nt $2 ] && { echo "ok $3 attempt $a $(date +%T)"; grep -E 'Total On-Chip|Design Nets Matched' $R/${3}_power.txt; cat $R/${3}_core_match.txt; exit 0; }
  echo "retry $3 attempt $a $(date +%T)"
done; echo "GAVE UP $3"; exit 1
