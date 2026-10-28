# xsdb: VERSION-refusal control.  Loads <bitstream> (env SR_BIT) and an ELF of ANOTHER design, fills output-related DDR regions with known patterns BEFORE the program
# runs (dow -data = memory writes), runs it, and after the refusal reads the same regions back (mrd) plus the DMA / accelerator registers (read only), so that
# the host can show that nothing was written.  Uses only xsdb memory reads/writes, the same as run_board.tcl.  Same load sequence as run_board.tcl (isolation,
# platform ps7_init.tcl = 100 MHz, L2 off, ELF loaded twice).
#   xsdb software/board/refusal_test.tcl <elf> <input.raw> <patdir> <outdir>
# patdir holds pat_out.bin (7 MB at SR_OUT_ADDR), pat_pad.bin (2 MB at SR_PAD_ADDR), pat_tin.bin, pat_tout.bin (64 KB at the tile buffers).
# Writes <outdir>/{pre,post}_{out,pad,tin,tout}.bin and prints REG lines.   Created 2026-10-28.
set VITIS_WS /home/sreevenkat/Desktop/venkat/vitis_workspace
set BIT      $::env(SR_BIT)
set PS7_INIT $VITIS_WS/sr_app/_ide/psinit/ps7_init.tcl
set IN_ADDR 0x10000000; set OUT_ADDR 0x12000000; set MARK_ADDR 0x13000000; set MARK_MAGIC 0x52454459
set PAD_ADDR 0x14000000; set TIN_ADDR 0x16000000; set TOUT_ADDR 0x16100000
if {$argc != 4} { puts "usage: xsdb refusal_test.tcl <elf> <input.raw> <patdir> <outdir>"; exit 2 }
lassign $argv ELF IN_RAW PATDIR OUTDIR
foreach f [list $BIT $PS7_INIT $ELF $IN_RAW $PATDIR/pat_out.bin $PATDIR/pat_pad.bin $PATDIR/pat_tin.bin $PATDIR/pat_tout.bin] {
    if {![file exists $f]} { puts "ERROR: missing file $f"; exit 2 } }
file mkdir $OUTDIR

proc sr_isolate_pl {} {   ;# identical to run_board.tcl
    targets -set -nocase -filter {name =~ "arm*#0"}
    configparams force-mem-accesses 1
    mwr 0xF8000008 0xDF0D
    mwr 0xF8000240 0xF
    mwr 0xF8000900 0x0
    configparams force-mem-accesses 0
}
# read-only snapshot of the registers that would show a started transfer / tile
proc regs {tag} {
    configparams force-mem-accesses 1
    foreach {n a} {DMA_MM2S_DMASR 0x40400004 DMA_MM2S_SA 0x40400018 DMA_MM2S_LENGTH 0x40400028 DMA_S2MM_DMASR 0x40400034 DMA_S2MM_DA 0x40400048 DMA_S2MM_LENGTH 0x40400058
                   SR_STATUS 0x40000004 SR_CYCLES 0x4000000c SR_VERSION 0x40000014} {
        if {[catch {set v [mrd -value $a]}]} { set v FAIL }
        if {$v eq "FAIL"} { puts "REG $tag $n $a FAIL" } else { puts [format "REG %s %s %s 0x%08x" $tag $n $a $v] }
    }
    configparams force-mem-accesses 0
}
proc dump {tag dir} {
    foreach {n a bytes} {out 0x12000000 7340032 pad 0x14000000 2097152 tin 0x16000000 65536 tout 0x16100000 65536} {
        mrd -bin -file $dir/${tag}_$n.bin $a [expr {$bytes / 4}]
    }
}

connect
puts [targets]
sr_isolate_pl
targets -set -nocase -filter {name =~ "xc7z*"}
fpga -file $BIT
targets -set -nocase -filter {name =~ "arm*#0"}
rst -processor
source $PS7_INIT
ps7_init
ps7_post_config
configparams force-mem-accesses 1
mwr 0xF8F02100 0
configparams force-mem-accesses 0
dow $ELF
dow $ELF
dow -data $IN_RAW $IN_ADDR
dow -data $PATDIR/pat_out.bin  $OUT_ADDR
dow -data $PATDIR/pat_pad.bin  $PAD_ADDR
dow -data $PATDIR/pat_tin.bin  $TIN_ADDR
dow -data $PATDIR/pat_tout.bin $TOUT_ADDR
mwr $MARK_ADDR 0
puts "PATTERNS WRITTEN"
dump pre $OUTDIR
regs pre
con
set t0 [clock seconds]; set ready 0
while {[expr {[clock seconds] - $t0}] < 120} {
    after 500
    if {[catch {set m [mrd -value $MARK_ADDR]} err]} { stop; set m [mrd -value $MARK_ADDR]; con }
    if {[expr {$m}] == [expr {$MARK_MAGIC}]} { set ready 1; break }
}
stop
puts "READY $ready after [expr {[clock seconds] - $t0}] s"
set result [mrd -value [expr {$MARK_ADDR + 4}]]
puts [format "MARKER result=%d bytes=%d fnv=0x%08x tiles=%d test=%d" $result [mrd -value [expr {$MARK_ADDR + 8}]] [mrd -value [expr {$MARK_ADDR + 12}]] [mrd -value [expr {$MARK_ADDR + 16}]] [mrd -value [expr {$MARK_ADDR + 20}]]]
regs post
dump post $OUTDIR
disconnect
exit 0
