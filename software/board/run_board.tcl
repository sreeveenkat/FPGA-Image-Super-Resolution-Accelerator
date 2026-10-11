# xsdb script: run the SR accelerator test program on a ZedBoard connected over JTAG, push an input image, fetch the result.
#   source ~/Desktop/vivado_install/Vitis/2024.1/settings64.sh
#   xsdb software/board/run_board.tcl <input.raw> <output.raw>
# STATUS: NEVER RUN (no board connection when this was written, and the new bitstream / ELF do not exist yet).  Written from the xsdb command set that
# Vitis itself uses (connect, targets, fpga, ps7_init, dow, mwr, mrd); expect to adjust target filters on the first run.
# The program must be built with -DSR_TEST=2 (full image) or 3 (timing): see software/board/README.md.  It writes a ready marker into DDR (sr_memmap.h).
#
# ---- paths: CHANGE THESE after the block design is built and the Vitis application exists (they come from the Vitis workspace) -------------------------
set VITIS_WS   /home/sreevenkat/Desktop/venkat/vitis_workspace
set BIT        $VITIS_WS/sr_app/_ide/bitstream/design_1_wrapper.bit        ;# bitstream of the NEW design (with sr_accel_top)
set PS7_INIT   $VITIS_WS/sr_app/_ide/psinit/ps7_init.tcl                   ;# NOT adder_ip.tcl / any custom-IP script (trap from M0)
set ELF        $VITIS_WS/sr_app/build/sr_app.elf
# ---- memory map: must equal software/board/sr_app/sr_memmap.h ------------------------------------------------------------------------------------------
set IN_ADDR    0x10000000
set OUT_ADDR   0x12000000
set MARK_ADDR  0x13000000
set MARK_MAGIC 0x52454459
set TIMEOUT_S  600

if {$argc != 2} { puts "usage: xsdb run_board.tcl <input.raw> <output.raw>"; exit 2 }
set IN_RAW  [lindex $argv 0]
set OUT_RAW [lindex $argv 1]
foreach f [list $BIT $PS7_INIT $ELF $IN_RAW] { if {![file exists $f]} { puts "ERROR: missing file $f"; exit 2 } }

connect
puts "targets:"; puts [targets]

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
dow -data $IN_RAW $IN_ADDR
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
stop
if {!$ready} { puts "ERROR: no ready marker after $TIMEOUT_S s (see the UART: sudo picocom -b 115200 /dev/ttyACM0)"; exit 1 }

# 5. marker block: [1] result (0 = ok), [2] output file bytes, [3] FNV-1a 32 of the output payload, [4] tiles, [5] test number
set result [mrd -value [expr {$MARK_ADDR + 4}]]
set nbytes [mrd -value [expr {$MARK_ADDR + 8}]]
set fnv    [mrd -value [expr {$MARK_ADDR + 12}]]
set tiles  [mrd -value [expr {$MARK_ADDR + 16}]]
puts [format "marker: result=%d bytes=%d tiles=%d fnv1a32=0x%08x" $result $nbytes $tiles $fnv]
if {$result != 0} { puts "ERROR: the program reported error code $result (see the UART)"; exit 1 }
if {$nbytes % 4 != 0 || $nbytes < 16} { puts "ERROR: bad output size $nbytes"; exit 1 }

# 6. read the output image back (word count = bytes / 4)
mrd -bin -file $OUT_RAW $OUT_ADDR [expr {$nbytes / 4}]
puts "output written to $OUT_RAW ($nbytes bytes). Compare: .venv/bin/python software/host_tools/compare_raw.py $OUT_RAW <expected.raw>"
puts "(the FNV-1a printed by compare_raw.py for the board file must equal the marker value above)"
disconnect
exit 0
