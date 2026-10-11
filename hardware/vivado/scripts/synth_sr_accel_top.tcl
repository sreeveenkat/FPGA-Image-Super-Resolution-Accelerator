# Out-of-context synthesis + place and route of the accelerator top sr_accel_top (M6): AXI-Lite registers + AXI-Stream wrapper + tile core.
#   vivado -mode batch -source hardware/vivado/scripts/synth_sr_accel_top.tcl -tclargs [clk_ns=10.0] -log <file> -journal <file>
# Run from the project root.  Reports go to hardware/vivado/build/sr_accel_top/ (git-ignored).  Part: xc7z020clg484-1 (ZedBoard).
# HC and WDIR are NOT passed as generics: this deliberately tests the DEFAULTS of sr_accel_top (HC = 64, absolute WDIR),
# which is what the block design will use.  If the .mem files are not found, $readmemh only warns and the weights become 0 -> DSP count collapses.
set clk_ns [expr {[llength $argv] > 0 ? [lindex $argv 0] : 10.0}]
set root [pwd]
set out $root/hardware/vivado/build/sr_accel_top
file mkdir $out

# HC rule (not checked in the RTL, see the header of sr_accel_top.v): the default HC must give byte counts that are multiples of 4
set fh [open $root/hardware/rtl/top/sr_accel_top.v]; set src [read $fh]; close $fh
if {![regexp {parameter HC\s*=\s*(\d+)} $src -> hc]} { error "cannot find the default HC in sr_accel_top.v" }
if {(($hc + 6) * ($hc + 6) * 3) % 4 != 0 || ((2 * $hc) * (2 * $hc) * 3) % 4 != 0} { error "HC=$hc: (HC+6)^2*3 and (2*HC)^2*3 must be multiples of 4" }
puts "HC rule ok for default HC=$hc"

read_verilog [glob $root/hardware/rtl/common/*.v]
read_verilog $root/hardware/rtl/conv_engine/conv_engine.v
read_verilog $root/hardware/rtl/sr_core/sr_tile_core.v
read_verilog $root/hardware/rtl/axi_wrapper/sr_axis_wrapper.v
read_verilog $root/hardware/rtl/top/sr_accel_top.v
synth_design -top sr_accel_top -part xc7z020clg484-1 -mode out_of_context -flatten_hierarchy rebuilt
create_clock -name aclk -period $clk_ns [get_ports aclk]
write_checkpoint -force $out/post_synth.dcp
report_utilization    -file $out/utilization.txt
report_timing_summary -file $out/timing.txt -max_paths 5
opt_design
place_design
route_design
write_checkpoint -force $out/routed.dcp
report_utilization    -file $out/utilization_routed.txt
report_timing_summary -file $out/timing_routed.txt -max_paths 5
report_route_status   -file $out/route_status.txt
report_power          -file $out/power_routed.txt
report_timing_summary -max_paths 1
