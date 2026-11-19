# xsim Tcl (added 2026-11-19 for pipe3/pipe4): post-implementation netlist, SAIF in consecutive windows after a warm-up.  Vivado estimate, not measured.
# Set before sourcing:  period (ns), prefix (SAIF file prefix), warm (cycles), win (cycles per window), nwin.  Each window is closed (usable) on its own.
run [expr {$warm * $period}] ns
for {set k 1} {$k <= $nwin} {incr k} {
    open_saif ${prefix}_w$k.saif
    log_saif [get_objects -r /tb_power/design_1_i/*]
    run [expr {$win * $period}] ns
    close_saif
    puts "SAIF_WINDOW_DONE $k at [current_time]"
}
quit
