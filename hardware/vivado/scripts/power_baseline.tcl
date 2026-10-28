# Vectorless power estimate of a ROUTED checkpoint COPY (never the build output).  Vivado estimate, not measured.
#   vivado -mode batch -nojournal -nolog -source hardware/vivado/scripts/power_baseline.tcl -tclargs <routed_copy.dcp> <out_dir> <tag>
# Default settings (no user activity): report_power as Vivado does it after route_design.  Writes <out_dir>/<tag>_power_vectorless.txt (+ a hierarchical one).
lassign $argv dcp out tag
if {$dcp eq "" || $out eq "" || $tag eq ""} { puts "usage: ... -tclargs <routed_copy.dcp> <out_dir> <tag>"; exit 2 }
file mkdir $out
open_checkpoint $dcp
report_power -file $out/${tag}_power_vectorless.txt
report_power -hierarchical_depth 6 -file $out/${tag}_power_vectorless_hier.txt
close_design
exit 0
