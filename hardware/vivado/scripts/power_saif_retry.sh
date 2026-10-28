#!/usr/bin/env bash
# usage: power_saif_retry.sh <dcp> <saif> <prefix> ; per-attempt timeout 300 s (Vivado sometimes hangs at "Preparing netlist"), up to 4 attempts
cd /home/sreevenkat/Desktop/venkat/sem_project_all
source ~/Desktop/vivado_install/Vivado/2024.1/settings64.sh >/dev/null 2>&1
R=results/power_estimate/raw
for a in 1 2 3 4; do
  timeout -k 5 300 vivado -mode batch -nojournal -nolog -source hardware/vivado/scripts/power_saif.tcl -tclargs $1 $2 tb_power $R/$3 > $R/${3}_vivado.log 2>&1 < /dev/null
  [ -s $R/${3}_power.txt ] && grep -q "Total On-Chip" $R/${3}_power.txt && [ $R/${3}_power.txt -nt $2 ] && { echo "ok $3 attempt $a $(date +%T)"; exit 0; }
  echo "retry $3 (attempt $a failed/timed out) $(date +%T)"
done
echo "GAVE UP $3"; exit 1
