# xsdb: reset the whole Zynq PS from the debugger.  Use it when the debug port is stuck ("AHB AP transaction error", ARM targets missing under APU / only "DAP" listed).
#   xsdb software/board/dap_reset.tcl
connect
puts "before: [targets]"
if {[catch {targets -set -nocase -filter {name =~ "APU*"}; rst -system} e]} {
    puts "APU system reset failed ($e), trying SRST through the DAP target"
    targets -set -nocase -filter {name =~ "DAP*"}
    rst -srst
}
after 4000
puts "after: [targets]"
disconnect
exit 0
