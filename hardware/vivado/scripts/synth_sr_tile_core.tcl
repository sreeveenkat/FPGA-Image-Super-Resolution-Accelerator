# Out-of-context synthesis of the WHOLE tile core sr_tile_core (M5): 4 conv engines + 5 split RAMs + loader + pixel shuffle.
#   vivado -mode batch -source hardware/vivado/scripts/synth_sr_tile_core.tcl -tclargs [clk_ns=10.0] [mode]
#   mode: (none) synthesis only | impl: also opt/place/route and routed reports | small: HC=6 geometry + post-synthesis functional netlist
#         (build/sr_tile_core_small/postsynth.v, used by hardware/verification/run_postsynth.sh)
# Run from the project root.  Reports go to hardware/vivado/build/ (git-ignored).  Part: xc7z020clg484-1 (ZedBoard).
set clk_ns [expr {[llength $argv] > 0 ? [lindex $argv 0] : 10.0}]
set mode   [expr {[llength $argv] > 1 ? [lindex $argv 1] : ""}]
set small  [expr {$mode eq "small"}]
set impl   [expr {$mode eq "impl"}]
set root [pwd]
set hc [expr {$small ? 6 : 64}]
set out $root/hardware/vivado/build/sr_tile_core[expr {$small ? "_small" : ""}][expr {$impl ? "_impl" : ""}]
file mkdir $out

# SHIFT of each layer from the exported header
set fh [open $root/hardware/rtl/weights/network_params.vh]; set hdr [read $fh]; close $fh
foreach n {1 2 3 4} { regexp "L${n}_SHIFT = (\\d+);" $hdr -> shift$n }

read_verilog [glob $root/hardware/rtl/common/*.v]
read_verilog $root/hardware/rtl/conv_engine/conv_engine.v
read_verilog $root/hardware/rtl/sr_core/sr_tile_core.v
synth_design -top sr_tile_core -part xc7z020clg484-1 -mode out_of_context -flatten_hierarchy rebuilt \
    -generic HC=$hc -generic SHIFT1=$shift1 -generic SHIFT2=$shift2 -generic SHIFT3=$shift3 -generic SHIFT4=$shift4 \
    -generic "WDIR=\"$root/hardware/rtl/weights/\""
create_clock -name clk -period $clk_ns [get_ports clk]
write_checkpoint -force $out/post_synth.dcp   ;# open later in the GUI:  vivado <this file>
report_utilization    -file $out/utilization.txt
report_timing_summary -file $out/timing.txt -max_paths 5
report_utilization
report_timing_summary -max_paths 1
if {$small} { write_verilog -force -mode funcsim $out/postsynth.v }
if {$impl} {
    opt_design
    place_design
    route_design
    write_checkpoint -force $out/routed.dcp       ;# open later in the GUI:  vivado <this file>
    report_utilization    -file $out/utilization_routed.txt
    report_timing_summary -file $out/timing_routed.txt -max_paths 5
    report_route_status   -file $out/route_status.txt
    report_timing_summary -max_paths 1
}
