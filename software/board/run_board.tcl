# xsdb script: run the SR accelerator test program on a ZedBoard connected over JTAG, push an input image, fetch the result and the program's numbers.
#   source ~/Desktop/vivado_install/Vitis/2024.1/settings64.sh
#   xsdb software/board/run_board.tcl <elf> <input.raw|-> <output.raw|-> [stats_file]
#     <elf>     software/board/build/sr_app_t<N>.elf (build_elf.sh <N>);  "-" as input/output = test 1 (no image)
#     stats     optional text file: one line "key=value" per number read back from the marker block in DDR
# STATUS: first used on the board 2026-10-11 (see results/speed/m6_board_runs.md).  The program writes a ready marker plus numbers into DDR (sr_memmap.h), because the
# UART may be held by another terminal.
#
set VITIS_WS   /home/sreevenkat/Desktop/venkat/vitis_workspace
# bitstream of the design with sr_accel_top.  DEFAULT = VERSION 0x53520602, Vivado project m6_sr_0602 (rebuilt 2026-10-12, full board regression passed,
# results/utilization/m6_system_0602.md).  FALLBACK 0601 (project m6_sr, board-verified 2026-10-11/12), via env SR_BIT:
#   SR_BIT=/home/sreevenkat/Desktop/venkat/vitis/m6_sr/m6_sr.runs/impl_1/design_1_wrapper.bit xsdb software/board/run_board.tcl ...
set BIT        [expr {[info exists ::env(SR_BIT)] ? $::env(SR_BIT) : "/home/sreevenkat/Desktop/venkat/R2q_artifacts/design_1_wrapper_R2q.bit"}]   ;# R2q sandbox: this tree's own bitstream (VERSION 0x53522201); the R0 bitstream is refused by this tree's driver
set PS7_INIT   $VITIS_WS/sr_app/_ide/psinit/ps7_init.tcl                   ;# NOT adder_ip.tcl / any custom-IP script (trap from M0)
# ---- memory map: must equal software/board/sr_app/sr_memmap.h ------------------------------------------------------------------------------------------
set IN_ADDR    0x10000000
set OUT_ADDR   0x12000000
set MARK_ADDR  0x13000000
set MARK_MAGIC 0x52454459
set TIMEOUT_S  900
set NSTATS     40

if {$argc < 3} { puts "usage: xsdb run_board.tcl <elf> <input.raw|-> <output.raw|-> [stats_file]"; exit 2 }
set ELF     [lindex $argv 0]
set IN_RAW  [lindex $argv 1]
set OUT_RAW [lindex $argv 2]
set STATS_F [expr {$argc > 3 ? [lindex $argv 3] : ""}]
set need [list $BIT $PS7_INIT $ELF]
if {$IN_RAW ne "-"} { lappend need $IN_RAW }
foreach f $need { if {![file exists $f]} { puts "ERROR: missing file $f"; exit 2 } }

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
puts "targets:"; puts [targets]

# 0. optional system reset
# Optional (env SR_SYSRST=1): a system reset first.  Not needed normally; use it if the debug port is stuck ("AHB AP transaction error", core in "Vector Catch").
if {[info exists ::env(SR_SYSRST)] && $::env(SR_SYSRST) eq "1"} {
    targets -set -nocase -filter {name =~ "APU*"}
    rst -system
    after 1500
}

# 1. program the FPGA (the PL device is called xc7z020 on the JTAG chain)
# env SR_NOFPGA=1 skips this step (the PL keeps whatever state the previous run left: used to test stale-state recovery)
if {![info exists ::env(SR_NOFPGA)] || $::env(SR_NOFPGA) ne "1"} {
    sr_isolate_pl
    targets -set -nocase -filter {name =~ "xc7z*"}
    fpga -file $BIT
}

# 2. initialise the processing system (clocks, DDR, MIO, UART) and load the program
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
# Without a system reset, dirty data-cache lines of the PREVIOUS program survive "rst -processor" and can be written back over the new program (proven on the
# board: zeros from the old program's .bss inside the new program's MMU table -> data abort).  Loading twice (the first load flushes those lines out, the second
# writes the image again) removed this in every test; SR_VERIFY_DUMP checks the result.  env SR_DOW2=0 = load once (only for the A/B test).
dow $ELF
if {![info exists ::env(SR_DOW2)] || $::env(SR_DOW2) ne "0"} { dow $ELF }

# 3. input image into DDR, marker cleared
if {$IN_RAW ne "-"} { dow -data $IN_RAW $IN_ADDR }
mwr $MARK_ADDR 0

# 4. run and wait for the ready marker (the program writes it as its last action)
con
set t0 [clock seconds]
set ready 0
while {[expr {[clock seconds] - $t0}] < $TIMEOUT_S} {
    after 500
    if {[catch {set m [mrd -value $MARK_ADDR]} err]} {
        # reading while the core runs is not allowed on this setup: stop briefly, read, continue
        stop
        set m [mrd -value $MARK_ADDR]
        con
    }
    if {[expr {$m}] == [expr {$MARK_MAGIC}]} { set ready 1; break }
}
set wall [expr {[clock seconds] - $t0}]
stop
if {!$ready} { puts "ERROR: no ready marker after $TIMEOUT_S s (see the UART: sudo picocom -b 115200 /dev/ttyACM0)"; exit 1 }

# 5. marker block: [1] result (0 = ok), [2] output file bytes, [3] FNV-1a 32 of the output payload, [4] tiles, [5] test number, [8..] stats
set result [mrd -value [expr {$MARK_ADDR + 4}]]
set nbytes [mrd -value [expr {$MARK_ADDR + 8}]]
set fnv    [mrd -value [expr {$MARK_ADDR + 12}]]
set tiles  [mrd -value [expr {$MARK_ADDR + 16}]]
puts [format "marker: result=%d bytes=%d tiles=%d fnv1a32=0x%08x (host wall clock incl. image upload: %d s)" $result $nbytes $tiles $fnv $wall]
set sl [list "result=$result" "bytes=$nbytes" "tiles=$tiles" [format "fnv1a32=0x%08x" $fnv] "wall_s=$wall"]
for {set i 0} {$i < $NSTATS} {incr i} {
    lappend sl "stat$i=[mrd -value [expr {$MARK_ADDR + 32 + 4 * $i}]]"
}
# VERSION register of sr_accel_top (the PL is configured and the PS-PL interface is enabled at this point): shows which bitstream really ran.
# xsdb blocks PL addresses ("not added to the memory map") unless memory accesses are forced; 0 = read failed.
configparams force-mem-accesses 1
if {[catch {set ver [mrd -value 0x40000014]}]} { set ver 0 }
configparams force-mem-accesses 0
lappend sl [format "version=0x%08x" $ver]
puts "stats: [join $sl { }]"
if {$STATS_F ne ""} { set fh [open $STATS_F w]; puts $fh [join $sl "\n"]; close $fh }
# 5b. optional (env SR_VERIFY_DUMP=<file> SR_VERIFY_BYTES=<n>): physical copy of the program image (0x00100000, n bytes) read AFTER the run through the
#     DAP (no CPU cache in the path), checked against the ELF by verify_load.py: shows whether the program in DDR was still intact.
if {[info exists ::env(SR_VERIFY_DUMP)]} {
    targets -set -nocase -filter {name =~ "APU*"}
    mrd -bin -file $::env(SR_VERIFY_DUMP) 0x00100000 [expr {$::env(SR_VERIFY_BYTES) / 4}]
    targets -set -nocase -filter {name =~ "arm*#0"}
}

if {$result != 0} { puts "ERROR: the program reported error code $result (see the UART)"; exit 1 }

# 6. read the output image back (word count = bytes / 4)
if {$OUT_RAW ne "-"} {
    if {$nbytes % 4 != 0 || $nbytes < 16} { puts "ERROR: bad output size $nbytes"; exit 1 }
    mrd -bin -file $OUT_RAW $OUT_ADDR [expr {$nbytes / 4}]
    puts "output written to $OUT_RAW ($nbytes bytes). Compare: .venv/bin/python software/host_tools/compare_raw.py $OUT_RAW <expected.raw>"
    puts "(the FNV-1a printed by compare_raw.py for the board file must equal the marker value above)"
}
disconnect
exit 0
