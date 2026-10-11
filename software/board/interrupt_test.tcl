# xsdb script for the stale-state tests: start a program, let it run for <delay_ms>, STOP the CPU (leaving the PL/DMA wherever it was) and leave it stopped.
#   xsdb software/board/interrupt_test.tcl <elf> <input.raw|-> <delay_ms>
# Same programming sequence as run_board.tcl (env SR_NOFPGA=1 skips the bitstream, SR_SYSRST=1 system reset first).  Run run_board.tcl afterwards WITHOUT SR_SYSRST to see whether a fresh run recovers.
set VITIS_WS /home/sreevenkat/Desktop/venkat/vitis_workspace
set BIT $VITIS_WS/sr_app/_ide/bitstream/design_1_wrapper.bit
set PS7_INIT $VITIS_WS/sr_app/_ide/psinit/ps7_init.tcl
if {$argc != 3} { puts "usage: xsdb interrupt_test.tcl <elf> <input.raw|-> <delay_ms>"; exit 2 }
lassign $argv ELF IN_RAW DELAY
# PS-PL isolation before reprogramming the PL (env SR_NO_ISOLATE=1 skips it, A/B test only): hold the PL in reset (FPGA_RST_CTRL) and switch the PS-PL level
# shifters off (LVL_SHFTR_EN), so that the PL's outputs toggling during configuration cannot reach the PS AXI ports.  ps7_post_config switches them on again
# and releases the PL resets.  (Xilinx's guidance for PL reconfiguration with a running PS; without it the board sometimes got into a state where every
# tile failed until a system reset, see results/speed/m6_board.md.)
proc sr_isolate_pl {} {
    if {[info exists ::env(SR_NO_ISOLATE)] && $::env(SR_NO_ISOLATE) eq "1"} { return }
    targets -set -nocase -filter {name =~ "arm*#0"}
    configparams force-mem-accesses 1
    mwr 0xF8000008 0xDF0D        ;# SLCR unlock
    mwr 0xF8000240 0xF           ;# FPGA_RST_CTRL: FCLK_RESET0..3 asserted
    mwr 0xF8000900 0x0           ;# LVL_SHFTR_EN: PS-PL level shifters off
    configparams force-mem-accesses 0
}
connect
if {[info exists ::env(SR_SYSRST)] && $::env(SR_SYSRST) eq "1"} { targets -set -nocase -filter {name =~ "APU*"}; rst -system; after 1500 }
if {![info exists ::env(SR_NOFPGA)] || $::env(SR_NOFPGA) ne "1"} { sr_isolate_pl; targets -set -nocase -filter {name =~ "xc7z*"}; fpga -file $BIT }
targets -set -nocase -filter {name =~ "arm*#0"}
rst -processor
source $PS7_INIT
ps7_init
ps7_post_config
# The L2 cache controller (PL310) is NOT reset by "rst -processor": it still holds lines, also DIRTY ones, of the previous program.  "dow" writes DDR directly,
# so the new program could read stale L2 lines, or a stale dirty line could be written back over the freshly loaded program or data.  Disable the L2 before
# loading (the BSP boot code invalidates and re-enables it).  env SR_NO_L2_OFF=1 skips this (only for the A/B test of this fix).
if {![info exists ::env(SR_NO_L2_OFF)] || $::env(SR_NO_L2_OFF) ne "1"} {
    configparams force-mem-accesses 1
    mwr 0xF8F02100 0            ;# L2CC control register: bit 0 = enable
    configparams force-mem-accesses 0
}
dow $ELF
if {![info exists ::env(SR_DOW2)] || $::env(SR_DOW2) ne "0"} { dow $ELF }   ;# see run_board.tcl
if {$IN_RAW ne "-"} { dow -data $IN_RAW 0x10000000 }
mwr 0x13000000 0
con
after $DELAY
stop
configparams force-mem-accesses 1
puts "stopped after $DELAY ms: [targets]"
puts "PC: [rrd pc]"
foreach {n r} {DFSR "cp15 c5" DFAR "cp15 c6"} { catch {puts "$n: [rrd $r]"} }
if {[catch {puts [format "MARKER = 0x%08x result %d tiles %d" [mrd -value 0x13000000] [mrd -value 0x13000004] [mrd -value 0x13000010]]} e]} { puts "marker read failed: [string range $e 0 80]" }
# DMA status registers (MM2S_SR 0x40400004, S2MM_SR 0x40400034) and core STATUS (0x40000004), ERROR_CODE (0x40000010), CYCLES (0x4000000c)
foreach {n a} {MM2S_SR 0x40400004 S2MM_SR 0x40400034 STATUS 0x40000004 ERROR_CODE 0x40000010 CYCLES 0x4000000C} { if {[catch {puts [format "%s = 0x%08x" $n [mrd -value $a]]} e]} { puts "$n read failed: [string range $e 0 120]" } }
disconnect
exit 0
