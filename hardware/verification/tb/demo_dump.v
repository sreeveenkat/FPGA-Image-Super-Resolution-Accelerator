// Waveform dump for the simulation demo (hardware/verification/demo_sim.sh).  Compiled as a SECOND top level next to tb_sr_accel_top
// (iverilog -s tb_sr_accel_top -s demo_dump): the testbench itself is unchanged.  Dumps only the signals shown in demo_sim.gtkw.
`timescale 1ns/1ps
module demo_dump;
    initial begin
        $dumpfile("hardware/verification/build/demo_sim.vcd");
        $dumpvars(1, tb_sr_accel_top.aclk, tb_sr_accel_top.aresetn,
                     tb_sr_accel_top.awvalid, tb_sr_accel_top.awaddr, tb_sr_accel_top.wdata,
                     tb_sr_accel_top.s_tvalid, tb_sr_accel_top.s_tready, tb_sr_accel_top.s_tlast, tb_sr_accel_top.s_tdata,
                     tb_sr_accel_top.m_tvalid, tb_sr_accel_top.m_tready, tb_sr_accel_top.m_tlast, tb_sr_accel_top.m_tdata);
        $dumpvars(1, tb_sr_accel_top.dut.start_r, tb_sr_accel_top.dut.busy_st, tb_sr_accel_top.dut.wrap_done, tb_sr_accel_top.dut.done_s);
        $dumpvars(1, tb_sr_accel_top.dut.wrap.core.state,
                     tb_sr_accel_top.dut.wrap.core.bz1, tb_sr_accel_top.dut.wrap.core.bz2,
                     tb_sr_accel_top.dut.wrap.core.bz3, tb_sr_accel_top.dut.wrap.core.bz4);
    end
endmodule
