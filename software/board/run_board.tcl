# xsdb script: run the SR accelerator test program on a ZedBoard connected over JTAG, push an input image, fetch the result and the program's numbers.
#   source ~/Desktop/vivado_install/Vitis/2024.1/settings64.sh
#   xsdb software/board/run_board.tcl <elf> <input.raw|-> <output.raw|-> [stats_file]
#     <elf>     software/board/build/sr_app_t<N>.elf (build_elf.sh <N>);  "-" as input/output = test 1 (no image)
#     stats     optional text file: one line "key=value" per number read back from the marker block in DDR
# STATUS: first used on the board 2026-10-11 (see results/speed/m6_board_runs.md).  The program writes a ready marker plus numbers into DDR (sr_memmap.h), because the
# UART may be held by another terminal.
#
set VITIS_WS   /home/sreevenkat/Desktop/venkat/vitis_workspace
set BIT        $VITIS_WS/sr_app/_ide/bitstream/design_1_wrapper.bit        ;# bitstream of the design with sr_accel_top
set PS7_INIT   $VITIS_WS/sr_app/_ide/psinit/ps7_init.tcl                   ;# NOT adder_ip.tcl / any custom-IP script (trap from M0)
# ---- memory map: must equal software/board/sr_app/sr_memmap.h ------------------------------------------------------------------------------------------
set IN_ADDR    0x10000000
set OUT_ADDR   0x12000000
set MARK_ADDR  0x13000000
set MARK_MAGIC 0x52454459
set TIMEOUT_S  900
set NSTATS     32

if {$argc < 3} { puts "usage: xsdb run_board.tcl <elf> <input.raw|-> <output.raw|-> [stats_file]"; exit 2 }
set ELF     [lindex $argv 0]
set IN_RAW  [lindex $argv 1]
set OUT_RAW [lindex $argv 2]
set STATS_F [expr {$argc > 3 ? [lindex $argv 3] : ""}]
set need [list $BIT $PS7_INIT $ELF]
if {$IN_RAW ne "-"} { lappend need $IN_RAW }
foreach f $need { if {![file exists $f]} { puts "ERROR: missing file $f"; exit 2 } }

connect
puts "targets:"; puts [targets]

# 0. system reset first: a previous run that hung the PS leaves the debug port unusable ("AHB AP transaction error") until the system is reset
targets -set -nocase -filter {name =~ "APU*"}
rst -system
after 1500

# 1. program the FPGA (the PL device is called xc7z020 on the JTAG chain)
targets -set -nocase -filter {name =~ "xc7z*"}
fpga -file $BIT

# 2. initialise the processing system (clocks, DDR, MIO, UART) and load the program
targets -set -nocase -filter {name =~ "arm*#0"}
rst -processor
source $PS7_INIT
ps7_init
ps7_post_config
dow $ELF

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
puts "stats: [join $sl { }]"
if {$STATS_F ne ""} { set fh [open $STATS_F w]; puts $fh [join $sl "\n"]; close $fh }
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
