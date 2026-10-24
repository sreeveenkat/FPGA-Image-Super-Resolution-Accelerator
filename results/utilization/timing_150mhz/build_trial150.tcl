# Build the whole M6 system (PS7 + AXI DMA + sr_accel_top + the M0 GPIOs / adder_ip) from THIS repository into a NEW Vivado project, then
# synthesis, implementation, bitstream, reports and the XSA.  Batch only; ~6 min with 2 jobs on a 16-thread / 15 GB PC.
#   vivado -mode batch -nojournal -log <out_dir>.log -source hardware/vivado/scripts/build_m6_system.tcl -tclargs <out_dir> [jobs=2]
# Inputs (all in the repo): hardware/rtl/** (+ rtl/weights/*.mem), hardware/vivado/bd/design_1_m6.tcl (write_bd_tcl of the board-tested
# design), hardware/vivado/ip_repo/adder_ip_1_0 (M0 IP, kept so the address map and the Vitis BSP stay identical).
# Outputs: <out_dir>/m6_sr.xpr, <out_dir>/m6_sr.runs/impl_1/design_1_wrapper.bit, <out_dir>/design_1_wrapper.xsa, <out_dir>/reports_final/.
# Refuses to run if <out_dir> already exists.  Keep -jobs at 2: 8 parallel IP runs froze this PC once (2026-10-12).
if {[llength $argv] < 1} { error "usage: -tclargs <out_dir> [jobs]" }
set out  [file normalize [lindex $argv 0]]
set jobs [expr {[llength $argv] > 1 ? [lindex $argv 1] : 2}]
set root [file normalize [file dirname [info script]]/../../..]
if {[file exists $out]} { error "$out already exists: choose a new folder (this script never overwrites a project)" }
set wdir $root/hardware/rtl/weights/
foreach f {weights_L1.mem wrom_L4.mem bias_L4.mem mult_L4.mem} {
    if {![file exists $wdir$f]} { error "missing $wdir$f (run software/ai/quantization/export_rtl.py)" }
}

create_project m6_sr $out -part xc7z020clg484-1
set_property BOARD_PART digilentinc.com:zedboard:part0:1.1 [current_project]
set_property ip_repo_paths [list $root/hardware/vivado/ip_repo] [current_project]
update_ip_catalog
set rtl $root/hardware/rtl
add_files -norecurse [list $rtl/top/sr_accel_top.v $rtl/axi_wrapper/sr_axis_wrapper.v $rtl/sr_core/sr_tile_core.v $rtl/conv_engine/conv_engine.v \
    $rtl/common/mac_unit.v $rtl/common/requant.v $rtl/common/tile_ram.v $rtl/common/tile_ram_split.v $rtl/common/weight_rom.v]
update_compile_order -fileset sources_1

source $root/hardware/vivado/bd/design_1_m6.tcl
# The RTL default of WDIR is an absolute path on the original PC: point it at THIS checkout's weights.
set_property CONFIG.WDIR $wdir [get_bd_cells sr_accel_top_0]
# ---- 150 MHz trial: the ONLY non-RTL change.  FCLK0 from the DDR PLL, request 150 MHz (the IP picks the closest reachable value)
set_property -dict [list CONFIG.PCW_FCLK0_PERIPHERAL_CLKSRC {DDR PLL} CONFIG.PCW_FPGA0_PERIPHERAL_FREQMHZ {150}] [get_bd_cells processing_system7_0]
puts "TRIAL requested [get_property CONFIG.PCW_FPGA0_PERIPHERAL_FREQMHZ [get_bd_cells processing_system7_0]] MHz, actual [get_property CONFIG.PCW_ACT_FPGA0_PERIPHERAL_FREQMHZ [get_bd_cells processing_system7_0]] MHz, src [get_property CONFIG.PCW_FCLK0_PERIPHERAL_CLKSRC [get_bd_cells processing_system7_0]]"
puts "WDIR = [get_property CONFIG.WDIR [get_bd_cells sr_accel_top_0]]"
validate_bd_design
save_bd_design
set bd [get_files design_1.bd]
add_files -norecurse [make_wrapper -files $bd -top]
set_property top design_1_wrapper [current_fileset]
update_compile_order -fileset sources_1
generate_target all $bd

launch_runs impl_1 -to_step route_design -jobs $jobs
wait_on_run impl_1
set st [get_property STATUS [get_runs impl_1]]
puts "impl_1 status: $st"
if {![string match "*route_design Complete*" $st]} { error "implementation did not finish: $st" }

open_run impl_1
set rdir /reports_final
file mkdir 
report_utilization                 -file /utilization.txt
report_timing_summary -max_paths 10 -file /timing_summary.txt
report_timing -delay_type max -max_paths 10 -nworst 1 -sort_by slack -path_type full -file /worst10_setup_paths.txt
report_clocks -file /clocks.txt
report_clock_utilization -file /clock_utilization.txt
puts "WNS [get_property SLACK [get_timing_paths -delay_type max]]  WHS [get_property SLACK [get_timing_paths -delay_type min]]"
puts "TRIAL_DONE"
close_project
