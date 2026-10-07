# Creates the Vivado GUI project "sr_accel" with ALL RTL + ALL testbenches.
#   source ~/Desktop/vivado_install/Vivado/2024.1/settings64.sh
#   cd <project root>                      (= sem_project_all)
#   vivado -mode batch -source hardware/vivado/scripts/create_project.tcl     (build only)
#   vivado -source hardware/vivado/scripts/create_project.tcl                 (build + open GUI)
# Then:  source hardware/vivado/scripts/sim_helpers.tcl ; run_tb core        (see that file)
set root [pwd]
if {![file exists $root/hardware/rtl/sr_core/sr_tile_core.v]} { error "run this from the project root (sem_project_all)" }
set proj_dir $root/hardware/vivado/build/sr_accel_proj      ;# git-ignored build folder
set simdir   $proj_dir/sr_accel.sim/sim_1/behav/xsim

# SAFETY: a previous run left symlinks (hardware, data) in the sim folder.  create_project -force FOLLOWS symlinks and would
# delete the REAL folders behind them (this happened once!).  Remove the links themselves first and refuse to go on if one is left.
foreach d {hardware data} {
    if {![catch {file type $simdir/$d} t] && $t eq "link"} { file delete $simdir/$d }
}
foreach d {hardware data} {
    if {[file exists $simdir/$d] || ![catch {file type $simdir/$d}]} { error "$simdir/$d still exists: remove it by hand (rm, no -r)" }
}
create_project -force sr_accel $proj_dir -part xc7z020clg484-1

# ---------------- design sources (everything that becomes FPGA logic) ----------------
add_files -fileset sources_1 [glob $root/hardware/rtl/common/*.v]
add_files -fileset sources_1 $root/hardware/rtl/conv_engine/conv_engine.v
add_files -fileset sources_1 $root/hardware/rtl/sr_core/sr_tile_core.v
add_files -fileset sources_1 -norecurse [glob $root/hardware/rtl/weights/*.mem]
add_files -fileset sources_1 -norecurse $root/hardware/rtl/weights/network_params.vh
set_property file_type {Verilog Header} [get_files network_params.vh]
set_property include_dirs $root [get_filesets sources_1]
set_property top sr_tile_core [get_filesets sources_1]

# ---------------- testbenches (simulation only) ----------------
add_files -fileset sim_1 [glob $root/hardware/verification/tb/*.v]
set_property include_dirs $root [get_filesets sim_1]
set_property top tb_sr_tile [get_filesets sim_1]
set_property -name {xsim.elaborate.xelab.more_options} -value {-timescale 1ns/1ps} -objects [get_filesets sim_1]
set_property -name {xsim.simulate.runtime} -value {-all} -objects [get_filesets sim_1]

# ---------------- relative paths ----------------
# The testbenches/RTL open files like "data/golden/x.hex" and "hardware/rtl/weights/x.mem" RELATIVE to the simulator's working
# folder, which in a Vivado project is <proj>.sim/sim_1/behav/xsim.  Symlinks to the real folders make those paths work.
file mkdir $simdir
foreach d {hardware data} { file link -symbolic $simdir/$d $root/$d }

update_compile_order -fileset sources_1
update_compile_order -fileset sim_1
puts "Project ready: $proj_dir/sr_accel.xpr"
