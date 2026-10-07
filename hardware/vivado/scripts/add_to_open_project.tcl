# Adds ALL RTL + ALL testbenches to the Vivado project that is ALREADY OPEN (any name, any place).
#   In the Vivado Tcl Console:   source /home/sreevenkat/Desktop/venkat/sem_project_all/hardware/vivado/scripts/add_to_open_project.tcl
#   then:                        source /home/sreevenkat/Desktop/venkat/sem_project_all/hardware/vivado/scripts/sim_helpers.tcl
#                                run_tb core
# Needs data/golden to exist (export_rtl.py + gen_unit_vectors.py).  Uses COPIES, no symlinks (safe).
set root /home/sreevenkat/Desktop/venkat/sem_project_all
if {![file exists $root/hardware/rtl/sr_core/sr_tile_core.v]} { error "wrong root: $root" }

# design sources
add_files -fileset sources_1 [glob $root/hardware/rtl/common/*.v]
add_files -fileset sources_1 $root/hardware/rtl/conv_engine/conv_engine.v
add_files -fileset sources_1 $root/hardware/rtl/sr_core/sr_tile_core.v
add_files -fileset sources_1 -norecurse [glob $root/hardware/rtl/weights/*.mem]
add_files -fileset sources_1 -norecurse $root/hardware/rtl/weights/network_params.vh
set_property file_type {Verilog Header} [get_files network_params.vh]
set_property include_dirs $root [get_filesets sources_1]
set_property top sr_tile_core [get_filesets sources_1]

# testbenches
add_files -fileset sim_1 [glob $root/hardware/verification/tb/*.v]
set_property include_dirs $root [get_filesets sim_1]
set_property top tb_sr_tile [get_filesets sim_1]
set_property -name {xsim.elaborate.xelab.more_options} -value {-timescale 1ns/1ps} -objects [get_filesets sim_1]
set_property -name {xsim.simulate.runtime} -value {-all} -objects [get_filesets sim_1]

# The testbenches open "data/golden/..." and "hardware/rtl/weights/..." relative to xsim's working folder
# (<project>/<name>.sim/sim_1/behav/xsim).  Copy those files there.
set pdir  [get_property DIRECTORY [current_project]]
set pname [get_property NAME [current_project]]
set simdir $pdir/$pname.sim/sim_1/behav/xsim
file mkdir $simdir/hardware/rtl/weights $simdir/data
file copy -force {*}[glob $root/hardware/rtl/weights/*] $simdir/hardware/rtl/weights/
file copy -force $root/data/golden $simdir/data/

update_compile_order -fileset sources_1
update_compile_order -fileset sim_1
puts "Added RTL + testbenches to project $pname.  Sim folder: $simdir"
