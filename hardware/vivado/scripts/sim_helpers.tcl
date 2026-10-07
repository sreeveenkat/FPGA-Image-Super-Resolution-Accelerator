# Helpers to run each testbench of the "sr_accel" project from the Vivado Tcl console.
#   source hardware/vivado/scripts/sim_helpers.tcl
#   run_tb core                 ;# tile core, tiny size (HC=6), tile small12      -> expect a PASS line
#   run_tb core_stall           ;# same with random stalls and a 2nd tile
#   run_tb core64 real0         ;# tile core at real size (HC=64), tile real0 (slow: minutes)
#   run_tb conv 1 small12       ;# conv engine layer 1 (1..4), HC=6
#   run_tb conv_rand 3          ;# randomized layer 3
#   run_tb requant 8            ;# requantizer test for SHIFT 8 (1,2,3,8,21,23,24)
#   run_tb mac | ram | splitram | rom 2
proc _go {top generics plusargs} {
    catch {close_sim -force}
    set fs [get_filesets sim_1]
    set_property top $top $fs
    set_property generic $generics $fs
    set_property -name {xsim.simulate.xsim.more_options} -value $plusargs -objects $fs
    launch_simulation -simset sim_1 -mode behavioral    ;# runtime -all: the testbench runs to its $finish here
    catch {close_sim -force}
}
proc run_tb {which args} {
    switch $which {
        core       { set t [expr {[llength $args] ? [lindex $args 0] : "small12"}]
                     _go tb_sr_tile {HC=6} "-testplusarg TILE=$t -testplusarg NOEXTRA" }
        core_stall { _go tb_sr_tile {HC=6} "-testplusarg TILE=small12 -testplusarg TILE2=small12b -testplusarg STALL=1" }
        core64     { set t [expr {[llength $args] ? [lindex $args 0] : "real0"}]
                     _go tb_sr_tile {HC=64} "-testplusarg TILE=$t -testplusarg NOEXTRA" }
        conv       { set L [lindex $args 0]; set t [expr {[llength $args] > 1 ? [lindex $args 1] : "small12"}]
                     _go tb_conv_layer "LAYER=$L HC=6" "-testplusarg TILE=$t" }
        conv_rand  { _go tb_conv_layer "LAYER=[lindex $args 0] HC=6 HH=4 RAND=1" "" }
        requant    { _go tb_requant "SHIFT=[lindex $args 0]" "" }
        mac        { _go tb_mac_unit {} "" }
        ram        { _go tb_tile_ram {} "" }
        splitram   { _go tb_tile_ram_split {} "" }
        rom        { _go tb_weight_rom "LAYER=[lindex $args 0]" "" }
        default    { error "unknown testbench $which" }
    }
}
