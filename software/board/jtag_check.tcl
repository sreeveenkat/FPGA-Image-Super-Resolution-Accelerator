# xsdb: does the ZedBoard answer on JTAG?  Prints the target list and one line "JTAG_OK" or "JTAG_FAIL <reason>".  Touches nothing on the board.
#   xsdb software/board/jtag_check.tcl
if {[catch {connect} e]} { puts "JTAG_FAIL connect: $e"; exit 1 }
set t [targets]
puts $t
if {![string match "*xc7z020*" $t]} { puts "JTAG_FAIL no xc7z020 (PL) on the JTAG chain"; exit 1 }
if {![string match "*Cortex-A9 MPCore #0*" $t]} { puts "JTAG_FAIL ARM core #0 not visible (debug port stuck?)"; exit 1 }
targets -set -nocase -filter {name =~ "xc7z*"}
if {[catch {puts "FPGA_STATE [fpga -state]"}]} { puts "FPGA_STATE unknown" }
puts "JTAG_OK"
disconnect
exit 0
