# usage: vivado -mode batch -source reports150.tcl -tclargs <routed.dcp> <out_dir>
set dcp [lindex $argv 0]
set rdir [lindex $argv 1]
open_checkpoint $dcp
report_timing_summary -max_paths 10 -file $rdir/timing_summary.txt
report_timing -delay_type max -max_paths 10 -nworst 1 -sort_by slack -path_type full -file $rdir/worst10_setup_paths.txt
report_utilization -file $rdir/utilization.txt
report_clocks -file $rdir/clocks.txt
puts "WNS [get_property SLACK [get_timing_paths -delay_type max]]  WHS [get_property SLACK [get_timing_paths -delay_type min]]"
puts "REPORTS_DONE"
