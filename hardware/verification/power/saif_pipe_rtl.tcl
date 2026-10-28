# xsim Tcl: pipeline RTL, SAIF over a 400,000-cycle window (8 ns) after 100,000 warm-up cycles.
set period 8
run [expr {100000 * $period}] ns
open_saif pipe_rtl.saif
log_saif [get_objects -r /tb_power/design_1_i/*]
run [expr {400000 * $period}] ns
close_saif
puts "SAIF_DONE [current_time]"
quit
