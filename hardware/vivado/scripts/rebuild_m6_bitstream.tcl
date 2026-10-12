# Rebuild the bitstream + XSA of the EXISTING Vivado project m6_sr after an RTL change of sr_accel_top (module reference). Batch only.
#   vivado -mode batch -source hardware/vivado/scripts/rebuild_m6_bitstream.tcl -tclargs <path/to/m6_sr.xpr> [jobs]
# Does ONLY: refresh the sr_accel_top module reference, reset + rerun synthesis/implementation/bitstream, write reports, export the XSA
# (<project dir>/design_1_wrapper.xsa, bitstream included).  No other block-design change.  Close the project in the Vivado GUI first.
# Reports go to <project dir>/reports_final/.
if {[llength $argv] < 1} { error "usage: -tclargs <m6_sr.xpr> [jobs]" }
set xpr  [file normalize [lindex $argv 0]]
set jobs [expr {[llength $argv] > 1 ? [lindex $argv 1] : 8}]
set pdir [file dirname $xpr]
open_project $xpr

set ref [get_ips -quiet *sr_accel_top*]
if {[llength $ref] != 1} { error "expected exactly one sr_accel_top module reference, found: $ref" }
puts "refreshing module reference $ref"
open_bd_design [get_files design_1.bd]
update_module_reference $ref
validate_bd_design
save_bd_design
generate_target all [get_files design_1.bd]

foreach r [get_runs -filter {IS_SYNTHESIS}] { reset_run $r }
reset_run impl_1
launch_runs impl_1 -to_step write_bitstream -jobs $jobs
wait_on_run impl_1
set st [get_property STATUS [get_runs impl_1]]
puts "impl_1 status: $st"
if {![string match "*write_bitstream Complete*" $st]} { error "implementation did not finish: $st" }

open_run impl_1
set rdir $pdir/reports_final
file mkdir $rdir
report_utilization                 -file $rdir/utilization.txt
report_utilization -hierarchical   -file $rdir/utilization_hier.txt
report_timing_summary -max_paths 10 -file $rdir/timing_summary.txt
report_power                       -file $rdir/power.txt
report_drc                         -file $rdir/drc.txt
puts "WNS [get_property SLACK [get_timing_paths -delay_type max]]  WHS [get_property SLACK [get_timing_paths -delay_type min]]"
write_hw_platform -fixed -include_bit -force -file $pdir/design_1_wrapper.xsa
puts "XSA written: $pdir/design_1_wrapper.xsa"
close_project
