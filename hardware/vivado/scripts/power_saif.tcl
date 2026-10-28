# Power estimate of a ROUTED checkpoint COPY with real switching activity from a SAIF file.  Vivado estimate, not measured.
#   vivado -mode batch -nojournal -nolog -source hardware/vivado/scripts/power_saif.tcl -tclargs <routed_copy.dcp> <file.saif> <strip_path> <out_prefix>
# strip_path: the testbench top, e.g. tb_power (the SAIF paths are tb_power/design_1_i/sr_accel_top_0/inst/...; stripping tb_power gives the paths of the in-system design).
# Writes <out_prefix>_power.txt, <out_prefix>_power_hier.txt, <out_prefix>_read_saif.log.  The checkpoint is not modified (no write_checkpoint).
lassign $argv dcp saif strip prefix
if {$dcp eq "" || $saif eq "" || $strip eq "" || $prefix eq ""} { puts "usage: ... -tclargs <routed_copy.dcp> <file.saif> <strip_path> <out_prefix>"; exit 2 }
file mkdir [file dirname $prefix]
open_checkpoint $dcp
puts "READ_SAIF $saif strip=$strip"
read_saif -strip_path $strip -verbose $saif
# how much of the CORE instance got activity from the SAIF: source code of every top-level net of design_1_i/sr_accel_top_0 as reported by report_switching_activity
# ((S) = from the SAIF; other letters = propagated / default / user)
set core_nets [get_nets -hier -top_net_of_hierarchical_group -filter {NAME =~ design_1_i/sr_accel_top_0/*}]
set txt [report_switching_activity -return_string -toggle_rate $core_nets]
array set cnt {}
set ntot 0
foreach line [split $txt "\n"] {
    if {[regexp {toggle rate = [0-9.eE+-]+ \((.)\)} $line -> code]} { incr ntot; if {![info exists cnt($code)]} { set cnt($code) 0 }; incr cnt($code) }
}
set fh [open ${prefix}_core_match.txt w]
puts $fh "core_nets_total [llength $core_nets]"
puts $fh "core_nets_reported $ntot"
foreach c [lsort [array names cnt]] { puts $fh "source_($c) $cnt($c)" }
close $fh
puts "CORE_MATCH total=[llength $core_nets] reported=$ntot [array get cnt]"
report_power -file ${prefix}_power.txt
report_power -hierarchical_depth 6 -file ${prefix}_power_hier.txt
close_design
exit 0
