# Build the whole M6 system (PS7 + AXI DMA + sr_accel_top + the M0 GPIOs / adder_ip; branch pipe: sr_accel_top = the whole-frame pipeline) from THIS repository into a NEW Vivado project, then
# synthesis, implementation, bitstream, reports and the XSA.  Batch only; ~6 min with 2 jobs on a 16-thread / 15 GB PC.
#   vivado -mode batch -nojournal -log <out_dir>.log -source hardware/vivado/scripts/build_m6_system.tcl -tclargs <out_dir> [jobs=2] [fclk0_mhz=125]
#   (pipe3: fclk0_mhz 142.857 = IO PLL 1000 MHz / 7; Vivado picks the divisors, the report and ps7_init.tcl of the XSA show the real value)
# Inputs (all in the repo): hardware/rtl/** (+ rtl/weights/*.mem), hardware/vivado/bd/design_1_m6.tcl (write_bd_tcl of the board-tested
# design), hardware/vivado/ip_repo/adder_ip_1_0 (M0 IP, kept so the address map and the Vitis BSP stay identical).
# Outputs: <out_dir>/m6_sr.xpr, <out_dir>/m6_sr.runs/impl_1/design_1_wrapper.bit, <out_dir>/design_1_wrapper.xsa, <out_dir>/reports_final/.
# Refuses to run if <out_dir> already exists.  Keep -jobs at 2: 8 parallel IP runs froze this PC once (2026-10-12).
if {[llength $argv] < 1} { error "usage: -tclargs <out_dir> [jobs]" }
set out  [file normalize [lindex $argv 0]]
set jobs [expr {[llength $argv] > 1 ? [lindex $argv 1] : 2}]
set mhz  [expr {[llength $argv] > 2 ? [lindex $argv 2] : 125}]
set root [file normalize [file dirname [info script]]/../../..]
if {[file exists $out]} { error "$out already exists: choose a new folder (this script never overwrites a project)" }
set wdir $root/hardware/rtl/weights/
foreach f {wpipe6_L1.mem wpipe6_L2.mem wpipe6_L3.mem wpipe6_L4.mem bias_L4.mem mult_L4.mem} {   ;# branch pipe4: NS = 6 ROMs
    if {![file exists $wdir$f]} { error "missing $wdir$f (run software/ai/quantization/export_rtl.py and export_pipe.py)" }
}

create_project m6_sr $out -part xc7z020clg484-1
set_property BOARD_PART digilentinc.com:zedboard:part0:1.1 [current_project]
set_property ip_repo_paths [list $root/hardware/vivado/ip_repo] [current_project]
update_ip_catalog
set rtl $root/hardware/rtl
add_files -norecurse [concat [list $rtl/top/sr_accel_top.v $rtl/common/requant.v] [glob $rtl/pipe/*.v]]   ;# branch pipe2: the whole-frame pipeline v2 (NS = 8, incl. pipe_mul_lut.v)
update_compile_order -fileset sources_1

source $root/hardware/vivado/bd/design_1_m6.tcl
# The RTL default of WDIR is an absolute path on the original PC: point it at THIS checkout's weights.
set_property CONFIG.WDIR $wdir [get_bd_cells sr_accel_top_0]
if {$mhz != 125} {
    set_property CONFIG.PCW_FPGA0_PERIPHERAL_FREQMHZ $mhz [get_bd_cells processing_system7_0]
}
puts "FCLK0 requested $mhz MHz, actual [get_property CONFIG.PCW_ACT_FPGA0_PERIPHERAL_FREQMHZ [get_bd_cells processing_system7_0]] MHz"
# pipe3 timing options (env, default off): SR_DMA_MM64=1 = AXI DMA memory-map side 64 bit (no 32->64 upsizers in front of HP0, which failed at 142.86 MHz)
if {[info exists ::env(SR_DMA_MM64)] && $::env(SR_DMA_MM64) == 1} {
    set_property -dict [list CONFIG.c_m_axi_mm2s_data_width {64} CONFIG.c_m_axi_s2mm_data_width {64}] [get_bd_cells axi_dma_0]
    puts "SR_DMA_MM64: AXI DMA MM2S/S2MM memory-map width 64"
}
puts "WDIR = [get_property CONFIG.WDIR [get_bd_cells sr_accel_top_0]]"
validate_bd_design
save_bd_design
set bd [get_files design_1.bd]
add_files -norecurse [make_wrapper -files $bd -top]
set_property top design_1_wrapper [current_fileset]
update_compile_order -fileset sources_1
generate_target all $bd

# SR_IMPL_STRATEGY=<Vivado strategy name> (default: the project default, as for every earlier build)
if {[info exists ::env(SR_IMPL_STRATEGY)] && $::env(SR_IMPL_STRATEGY) ne ""} {
    set_property strategy $::env(SR_IMPL_STRATEGY) [get_runs impl_1]
    puts "impl_1 strategy: $::env(SR_IMPL_STRATEGY)"
}
launch_runs impl_1 -to_step write_bitstream -jobs $jobs
wait_on_run impl_1
set st [get_property STATUS [get_runs impl_1]]
puts "impl_1 status: $st"
if {![string match "*write_bitstream Complete*" $st]} { error "implementation did not finish: $st" }

open_run impl_1
set rdir $out/reports_final
file mkdir $rdir
report_utilization                 -file $rdir/utilization.txt
report_utilization -hierarchical   -file $rdir/utilization_hier.txt
report_timing_summary -max_paths 10 -file $rdir/timing_summary.txt
report_power                       -file $rdir/power.txt
report_drc                         -file $rdir/drc.txt
puts "WNS [get_property SLACK [get_timing_paths -delay_type max]]  WHS [get_property SLACK [get_timing_paths -delay_type min]]"
write_hw_platform -fixed -include_bit -force -file $out/design_1_wrapper.xsa
puts "BUILD_OK bitstream $out/m6_sr.runs/impl_1/design_1_wrapper.bit  XSA $out/design_1_wrapper.xsa"
close_project
