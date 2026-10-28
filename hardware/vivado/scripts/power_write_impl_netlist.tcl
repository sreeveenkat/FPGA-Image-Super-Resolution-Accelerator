# Writes the post-IMPLEMENTATION functional netlist of the core cell design_1_i/sr_accel_top_0 from a ROUTED checkpoint COPY (read-only): vivado -mode batch -source ... -tclargs <routed_copy.dcp> <out.v>
lassign $argv dcp out
open_checkpoint $dcp
set c [get_cells design_1_i/sr_accel_top_0]
puts "CELL $c ref=[get_property REF_NAME $c] nleaf=[llength [get_cells -hier -filter {IS_PRIMITIVE}]]"
puts "CORE_LEAF_CELLS [llength [get_cells -hier -filter {IS_PRIMITIVE && NAME =~ design_1_i/sr_accel_top_0/*}]]"
puts "CORE_NETS [llength [get_nets -hier -filter {NAME =~ design_1_i/sr_accel_top_0/*}]]"
write_verilog -force -mode funcsim -cell $c $out
close_design
exit 0
