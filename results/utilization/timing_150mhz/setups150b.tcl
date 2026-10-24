set dcp [lindex $argv 0]
open_checkpoint $dcp
set rdir [lindex $argv 1]
report_timing -delay_type max -from [get_pins -hier -filter {NAME =~ *e4/rq_i_reg[3]/C}] -to [get_pins -hier -filter {NAME =~ *e4/*/A[*] && REF_PIN_NAME =~ A*}] -path_type full -nworst 1 -max_paths 1 -file $rdir/path_rq_to_dsp.txt
report_timing -delay_type max -to [get_pins -hier -filter {NAME =~ *wrap/ow_reg[8]/D}] -path_type full -max_paths 1 -file $rdir/path_to_fdre.txt
puts "SETUPS_DONE"
