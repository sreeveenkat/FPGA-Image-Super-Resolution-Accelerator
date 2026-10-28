# Read-only: die temperature and rail voltages from the XADC (SYSMON) of the xc7z020 through Vivado's hardware manager.
#   source ~/Desktop/vivado_install/Vivado/2024.1/settings64.sh
#   vivado -mode batch -nolog -nojournal -source software/board/xadc_temp.tcl -tclargs "<label>"
# Prints  XADC_TEMP_C <t>  and  XADC_VCCINT <v> VCCAUX <v>.  Writes nothing to the board.  Run it BETWEEN board runs (one owner of the JTAG cable).
# Recreated 2026-10-28 from the commands recorded in results/board/2026-10-27/xadc_temperature.log (the original script was not saved in the repo).
open_hw_manager
connect_hw_server -url localhost:3121
open_hw_target
set d [lindex [get_hw_devices xc7z020*] 0]
current_hw_device $d
refresh_hw_device -update_hw_probes false $d
set s [lindex [get_hw_sysmons] 0]
puts "XADC_TEMP_C [get_property TEMPERATURE $s]"
puts "XADC_VCCINT [get_property VCCINT $s] VCCAUX [get_property VCCAUX $s]"
close_hw_target
disconnect_hw_server
close_hw_manager
exit
