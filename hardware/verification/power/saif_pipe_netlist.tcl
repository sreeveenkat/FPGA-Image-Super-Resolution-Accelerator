# xsim Tcl: pipeline post-synthesis netlist, SAIF in 4 consecutive windows of 75,000 cycles (8 ns) after 30,000 warm-up cycles.  Each window is closed (and so usable) on its own.
set period 8
run [expr {30000 * $period}] ns
for {set k 1} {$k <= 4} {incr k} {
    open_saif pipe_netlist_w$k.saif
    log_saif [get_objects -r /tb_power/design_1_i/*]
    run [expr {75000 * $period}] ns
    close_saif
    puts "SAIF_WINDOW_DONE $k at [current_time]"
}
quit
