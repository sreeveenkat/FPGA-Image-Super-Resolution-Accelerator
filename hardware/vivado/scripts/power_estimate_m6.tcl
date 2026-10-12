# M7 power ESTIMATE (vectorless, not a measurement) of the routed in-system design.  Opens the routed checkpoint read-only and runs
# report_power at three default toggle rates (low / Vivado default / high) to give a range, with a deeper hierarchy for the accelerator.
#   vivado -mode batch -nojournal -nolog -source hardware/vivado/scripts/power_estimate_m6.tcl -tclargs <routed.dcp> <out_dir>
# The checkpoint is not modified (no write_checkpoint).  Output: <out_dir>/power_toggle{6,12,25}.txt
lassign $argv dcp out
if {$dcp eq "" || $out eq ""} { puts "usage: ... -tclargs <routed.dcp> <out_dir>"; exit 2 }
file mkdir $out
open_checkpoint $dcp
foreach tr {6.25 12.5 25} tag {6 12 25} {
    # toggle rate in %, static probability 0.5 (Vivado default), applied to all nets without user activity
    set_switching_activity -default_toggle_rate $tr -default_static_probability 0.5
    report_power -hierarchical_depth 6 -file $out/power_toggle$tag.txt
    puts "POWER toggle=$tr% total=[get_property TOTAL_POWER [lindex [get_designs] 0]]"
}
close_design
exit 0
