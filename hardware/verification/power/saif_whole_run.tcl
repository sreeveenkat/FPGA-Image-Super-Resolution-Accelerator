# xsim Tcl: SAIF over the whole run (R0: one tile from CONTROL.start to the last output beat), file name given by the Tcl variable saif_name (set via -tclbatch wrapper).
open_saif $::saif_name
log_saif [get_objects -r /tb_power/design_1_i/*]
run -all
close_saif
puts "SAIF_DONE [current_time]"
quit
