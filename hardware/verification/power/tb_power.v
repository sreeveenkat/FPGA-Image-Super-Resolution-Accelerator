// Stimulus for the SAIF power simulation of the SYNTHESIZED accelerator (post-synthesis functional netlist of the Vivado IP design_1_sr_accel_top_0_0).
// Vivado estimate, not measured.  Created 2026-10-28.  One frame (pipeline, PIPE=1) or one 64x64 tile (R0, PIPE=0), the DMA sink always ready, the source
// always valid (no stalls), checked beat by beat against the integer model's output.  Instance names reproduce the system design's hierarchy:
// tb_power/design_1_i/sr_accel_top_0/inst/...  so that  read_saif -strip_path tb_power  matches the routed in-system checkpoint.
// Run from the work directory:  xelab -L unisims_ver -debug typical tb_power glbl -generic_top PIPE=1 -generic_top CLK_NS=8.0 ...
`timescale 1ns/1ps
module tb_power;
    // design / clock are compile-time macros (xvlog -d PIPE_MODE=1 -d CLKNS=8.0): generics given to xelab would be appended to the scope name and break the SAIF paths
    localparam integer PIPE = `PIPE_MODE;   // 1: pipeline (FRAME_W / FRAME_H registers), 0: R0 tile core
    localparam real    CLK_NS = `CLKNS;     // 8.0 = 125 MHz (pipeline), 10.0 = 100 MHz (R0)
    localparam integer MAXCYC = 4000000;
    // vector folder (in32.hex, out32.hex, meta.txt): plusarg +VEC=<dir> (a string generic would put its value into the scope name and break the SAIF paths)

    reg aclk = 0, aresetn = 0;
    always #(CLK_NS / 2.0) aclk = ~aclk;
    reg  [5:0]  awaddr = 0, araddr = 0;  reg awvalid = 0, wvalid = 0, arvalid = 0, bready = 1, rready = 1;
    reg  [31:0] wdata = 0;  reg [3:0] wstrb = 4'hF;
    wire awready, wready, bvalid, arready, rvalid;  wire [1:0] bresp, rresp;  wire [31:0] rdata;
    reg  [31:0] s_tdata = 0; reg s_tvalid = 0, s_tlast = 0;  wire s_tready;
    wire [31:0] m_tdata; wire [3:0] m_tkeep; wire m_tvalid, m_tlast;  reg m_tready = 1;

    sim_design_1 design_1_i (
        .aclk(aclk), .aresetn(aresetn),
        .s_axi_awaddr(awaddr), .s_axi_awprot(3'd0), .s_axi_awvalid(awvalid), .s_axi_awready(awready),
        .s_axi_wdata(wdata), .s_axi_wstrb(wstrb), .s_axi_wvalid(wvalid), .s_axi_wready(wready),
        .s_axi_bresp(bresp), .s_axi_bvalid(bvalid), .s_axi_bready(bready),
        .s_axi_araddr(araddr), .s_axi_arprot(3'd0), .s_axi_arvalid(arvalid), .s_axi_arready(arready),
        .s_axi_rdata(rdata), .s_axi_rresp(rresp), .s_axi_rvalid(rvalid), .s_axi_rready(rready),
        .s_axis_tdata(s_tdata), .s_axis_tkeep(4'hF), .s_axis_tvalid(s_tvalid), .s_axis_tready(s_tready), .s_axis_tlast(s_tlast),
        .m_axis_tdata(m_tdata), .m_axis_tkeep(m_tkeep), .m_axis_tvalid(m_tvalid), .m_axis_tready(m_tready), .m_axis_tlast(m_tlast));

    integer fw, fh, nbi, nbo, fd, r;
    reg [8*300-1:0] VEC;
    reg [31:0] in_mem  [0:1999999];
    reg [31:0] out_mem [0:1999999];
    integer ib = 0, ob = 0, errors = 0, cyc = 0, started = 0;
    always @(posedge aclk) cyc <= cyc + 1;

    // input source: valid from the start (the core only takes beats while its load phase is open)
    always @(posedge aclk) if (aresetn) begin
        if (s_tvalid && s_tready) begin
            ib <= ib + 1;
            if (ib + 1 < nbi) s_tdata <= in_mem[ib + 1];          // after the last beat the bus HOLDS its value (like a DMA), never X
            s_tlast  <= (ib + 1 == nbi - 1);
            if (ib + 1 >= nbi) s_tvalid <= 1'b0;
        end
    end
    // output sink
    always @(posedge aclk) if (m_tvalid && m_tready) begin
        if (ob < nbo && m_tdata !== out_mem[ob]) begin if (errors < 5) $display("FAIL output beat %0d: %h vs %h", ob, m_tdata, out_mem[ob]); errors = errors + 1; end
        ob <= ob + 1;
    end

    task axil_write(input [5:0] a, input [31:0] d);
        reg aw_hs, w_hs, aw_done, w_done;
        begin
            @(negedge aclk); awaddr = a; wdata = d; awvalid = 1; wvalid = 1; aw_done = 0; w_done = 0;
            while (!(aw_done && w_done)) begin
                @(posedge aclk);                                   // values sampled in the active region = the values BEFORE this edge
                aw_hs = awvalid && awready; w_hs = wvalid && wready;
                #0.1;
                if (aw_hs) begin awvalid = 0; aw_done = 1; end
                if (w_hs)  begin wvalid = 0;  w_done = 1; end
            end
            repeat (4) @(negedge aclk);
        end
    endtask
    reg [31:0] rd;
    task axil_read(input [5:0] a);
        reg ar_hs, got;
        begin
            @(negedge aclk); araddr = a; arvalid = 1; got = 0;
            @(posedge aclk); ar_hs = arvalid && arready; #0.1; if (ar_hs) arvalid = 0;
            while (!ar_hs) begin @(posedge aclk); ar_hs = arvalid && arready; #0.1; if (ar_hs) arvalid = 0; end
            while (!got) begin @(posedge aclk); if (rvalid && rready) begin rd = rdata; got = 1; end end
            @(negedge aclk);
        end
    endtask

    initial begin
        if (!$value$plusargs("VEC=%s", VEC)) begin $display("FAIL give +VEC=<dir>"); $finish; end
        fd = $fopen({VEC, "/meta.txt"}, "r");
        if (fd == 0) begin $display("FAIL missing %0s/meta.txt", VEC); $finish; end
        r = $fscanf(fd, "%d %d %d %d", fw, fh, nbi, nbo); $fclose(fd);
        $readmemh({VEC, "/in32.hex"},  in_mem, 0, nbi - 1);
        $readmemh({VEC, "/out32.hex"}, out_mem, 0, nbo - 1);
`ifdef NETLIST
        wait (glbl.GSR === 1'b0);                                  // the netlist's flip-flops are held by the global set/reset for the first 100 ns
`endif
        repeat (4) @(negedge aclk); aresetn = 1; repeat (4) @(negedge aclk);
        s_tdata = in_mem[0]; s_tlast = (nbi == 1); s_tvalid = 1;
        if (PIPE) begin axil_write(6'h08, fw); axil_write(6'h18, fh); end
        axil_write(6'h00, 32'd1);                                  // CONTROL.start
        started = 1;
        while (ob < nbo && cyc < MAXCYC) @(posedge aclk);
        repeat (20) @(posedge aclk);
        axil_read(6'h04);
        $display("INFO beats out %0d of %0d, STATUS 0x%08h, sim cycles %0d, errors %0d", ob, nbo, rd, cyc, errors);
        axil_read(6'h0C);
        $display("INFO CYCLES register %0d", rd);
        if (errors == 0 && ob == nbo) $display("PASS tb_power (%0s): %0d output beats bit-exact", PIPE ? "pipeline frame" : "R0 tile", ob);
        else $display("FAIL tb_power: %0d errors, %0d of %0d beats", errors, ob, nbo);
        $stop;
    end
endmodule
