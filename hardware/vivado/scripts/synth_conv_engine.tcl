# Out-of-context synthesis of ONE conv_engine instance (M4 exit check: DSP/BRAM/LUT numbers, timing at 100 MHz).
#   vivado -mode batch -source hardware/vivado/scripts/synth_conv_engine.tcl -tclargs <layer 1..4> [clk_ns=10.0] [small|impl]
#   with `impl`: after synthesis also run opt_design/place_design/route_design and report the routed timing/utilization.
#   with `small`: use the 12x12-tile geometry (core 6x6) AND write a post-synthesis functional netlist (build/conv_L<n>/postsynth.v)
#   for hardware/verification/run_postsynth.sh (simulates the synthesized hardware itself).
# Run from the project root. Reports go to hardware/vivado/build/ (git-ignored).  Part: xc7z020clg484-1 (ZedBoard).
# The RAMs are NOT part of the engine (they live outside), so this reports engine logic + weight ROM + MAC lanes + requantizer only.
set layer [lindex $argv 0]
set clk_ns [expr {[llength $argv] > 1 ? [lindex $argv 1] : 10.0}]
set mode [expr {[llength $argv] > 2 ? [lindex $argv 2] : ""}]
set small [expr {$mode eq "small"}]
set impl  [expr {$mode eq "impl"}]
set root [pwd]
set out $root/hardware/vivado/build/conv_L$layer[expr {$small ? "_small" : ""}][expr {$impl ? "_impl" : ""}]
file mkdir $out

# geometry of the four layers for a 64x64 core tile (70x70 input)
switch $layer {
    1 {set cin 3;  set cout 16; set k 3; set dw 0; set iw 70}
    2 {set cin 16; set cout 16; set k 3; set dw 1; set iw 68}
    3 {set cin 16; set cout 16; set k 1; set dw 0; set iw 66}
    4 {set cin 16; set cout 12; set k 3; set dw 0; set iw 66}
    default {error "layer must be 1..4"}
}
if {$small} {   ;# small12 tile: core 6x6 -> input widths 12 / 10 / 8 / 8
    set iw [lindex {0 12 10 8 8} $layer]
}
# SHIFT of each layer from the exported header
set fh [open $root/hardware/rtl/weights/network_params.vh]; set hdr [read $fh]; close $fh
regexp "L${layer}_SHIFT = (\\d+);" $hdr -> shift

read_verilog [glob $root/hardware/rtl/common/*.v]
read_verilog $root/hardware/rtl/conv_engine/conv_engine.v
set wd $root/hardware/rtl/weights
set gen [list C_IN=$cin C_OUT=$cout K=$k DEPTHWISE=$dw IN_W=$iw IN_H=$iw SHIFT=$shift \
    "W_FILE=\"$wd/wrom_L$layer.mem\"" "B_FILE=\"$wd/bias_L$layer.mem\"" "M_FILE=\"$wd/mult_L$layer.mem\""]
synth_design -top conv_engine -part xc7z020clg484-1 -mode out_of_context -generic [lindex $gen 0] -generic [lindex $gen 1] -generic [lindex $gen 2] -generic [lindex $gen 3] -generic [lindex $gen 4] -generic [lindex $gen 5] -generic [lindex $gen 6] -generic [lindex $gen 7] -generic [lindex $gen 8] -generic [lindex $gen 9] -flatten_hierarchy rebuilt
create_clock -name clk -period $clk_ns [get_ports clk]
write_checkpoint -force $out/post_synth.dcp   ;# open later in the GUI:  vivado <this file>
report_utilization    -file $out/utilization.txt
report_timing_summary -file $out/timing.txt -max_paths 5
report_utilization
report_timing_summary -max_paths 1
if {$small} {
    write_verilog -force -mode funcsim $out/postsynth.v
}
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
