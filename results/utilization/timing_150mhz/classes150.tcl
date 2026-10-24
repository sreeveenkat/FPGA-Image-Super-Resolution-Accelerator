# Classify the failing setup paths (one worst path per endpoint) by start cell type / destination cell type / hierarchy.
set dcp [lindex $argv 0]
set out [lindex $argv 1]
open_checkpoint $dcp
set paths [get_timing_paths -delay_type max -max_paths 1000 -nworst 1 -unique_pins -slack_lesser_than 0.0]
set fh [open $out w]
puts $fh "# failing setup endpoints (slack < 0), one worst path each: [llength $paths]"
puts $fh "# slack_ns | start_pin | end_pin | start_cell_type | end_cell_type | logic_levels | datapath_ns"
foreach p $paths {
    set sp [get_property STARTPOINT_PIN $p]
    set ep [get_property ENDPOINT_PIN $p]
    set st [get_property REF_NAME [get_cells -of_objects $sp]]
    set et [get_property REF_NAME [get_cells -of_objects $ep]]
    puts $fh "[get_property SLACK $p] | $sp | $ep | $st | $et | [get_property LOGIC_LEVELS $p] | [get_property DATAPATH_DELAY $p]"
}
close $fh
puts "CLASSES_DONE [llength $paths]"
