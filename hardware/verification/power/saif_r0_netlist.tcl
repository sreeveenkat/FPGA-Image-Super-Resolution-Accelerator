# xsim Tcl: R0 post-synthesis netlist, one 64x64 tile (about 926,200 cycles at 10 ns), SAIF in 5 consecutive windows of 190,000 cycles; the testbench stops the
# simulation ($stop) after the last output beat, which ends the 5th window early.  Each window is closed (usable) on its own.
set period 10
for {set k 1} {$k <= 5} {set k [expr {$k + 1}]} {
    open_saif r0_netlist_w$k.saif
    log_saif [get_objects -r /tb_power/design_1_i/*]
    run [expr {190000 * $period}] ns
    close_saif
    puts "SAIF_WINDOW_DONE $k at [current_time]"
}
quit
