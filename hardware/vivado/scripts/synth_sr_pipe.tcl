# Out-of-context synthesis (+ place and route) of the PIPELINE accelerator top (branch `pipe`: sr_accel_top = AXI-Lite registers + sr_pipe_core).
#   vivado -mode batch -source hardware/vivado/scripts/synth_sr_pipe.tcl -tclargs [clk_ns=8.0] [impl|small]
#     impl : synthesis + opt/place/route, reports (utilization, timing, power) and routed.dcp in hardware/vivado/build/sr_pipe_impl/
#     small: synthesis with MAXW = 32 and a post-synthesis functional netlist build/sr_pipe_small/postsynth.v for run_postsynth.sh
# Run from the project root.  WDIR is passed as a generic = THIS checkout's hardware/rtl/weights/ (the RTL default is an absolute path to main,
# which holds other weights).  Part: xc7z020clg484-1 (ZedBoard).  Checks after synthesis: every .mem file read, DSP count.
set clk_ns [expr {[llength $argv] > 0 ? [lindex $argv 0] : 8.0}]
set mode   [expr {[llength $argv] > 1 ? [lindex $argv 1] : "impl"}]
set root [pwd]
set out $root/hardware/vivado/build/sr_pipe_$mode
file mkdir $out
set wdir $root/hardware/rtl/weights/

read_verilog [list $root/hardware/rtl/common/requant.v]
read_verilog [glob $root/hardware/rtl/pipe/*.v]
read_verilog $root/hardware/rtl/top/sr_accel_top.v
set gens [list -generic "WDIR=\"$wdir\""]
if {$mode eq "small"} { lappend gens -generic MAXW=32 }
synth_design -top sr_accel_top -part xc7z020clg484-1 -mode out_of_context -flatten_hierarchy rebuilt {*}$gens
create_clock -name aclk -period $clk_ns [get_ports aclk]
write_checkpoint -force $out/post_synth.dcp
report_utilization    -file $out/utilization.txt
report_utilization -hierarchical -file $out/utilization_hier.txt
report_timing_summary -file $out/timing.txt -max_paths 5
if {$mode eq "small"} {
    write_verilog -force -mode funcsim $out/postsynth.v
} else {
    opt_design
    place_design
    phys_opt_design
    route_design
    write_checkpoint -force $out/routed.dcp
    report_utilization    -file $out/utilization_routed.txt
    report_utilization -hierarchical -file $out/utilization_hier_routed.txt
    report_timing_summary -file $out/timing_routed.txt -max_paths 10
    report_route_status   -file $out/route_status.txt
    report_power          -file $out/power_routed.txt
    report_timing_summary -max_paths 1
}
