// Self-checking testbench of the whole-frame pipeline accelerator (sr_accel_top of branch `pipe` = AXI-Lite registers + sr_pipe_core), with an ARM model
// (AXI-Lite master) and a DMA model (MM2S source, S2MM sink).  Vectors: data/golden/pipe/<frame>_* (gen_pipe_vectors.py).
//   +F0=<frame> .. +F7=<frame>  frames run back to back (different sizes; the DMA is armed BEFORE start every time)
//   +STALL=1    random gaps on s_axis and random back-pressure on m_axis; +STALL=2 the same with a SLOW m_axis sink (output banks and FIFOs fill up)
//   +LAYERS=1   also compare every stage's output stream (internal monitors) with <frame>_L1..L4
//   +ERR=1      error codes 1-4 (early TLAST, missing TLAST, TKEEP, frame size), each followed by a soft reset and a clean frame
//   +SWEEP=<n>  n soft-reset aborts at spread points of frame F0, each followed by a quiet check and a clean frame
// Checks: every output beat bit-exact, beat count, TLAST only on the last beat, AXI hold rule on m_axis, no input accepted before start or after the
// last beat, STATUS/CYCLES/ERROR_CODE/DBG registers, VERSION/MAX_W/FRAME_W/FRAME_H, internal FIFO error flags never set (ERROR_CODE 5).
`timescale 1ns/1ps
module tb_sr_pipe_top;
    parameter MAXW = 1024;
    `include "hardware/rtl/weights/network_params.vh"
    localparam MAXB = 1600000;

    reg aclk = 0, aresetn = 0;
    always #4 aclk = ~aclk;                    // 125 MHz
    reg  [5:0]  awaddr, araddr;
    reg  [31:0] wdata;
    reg  [3:0]  wstrb;
    reg         awvalid = 0, wvalid = 0, bready = 1, arvalid = 0, rready = 1;
    wire        awready, wready, bvalid, arready, rvalid;
    wire [1:0]  bresp, rresp;
    wire [31:0] rdata;
    reg  [31:0] s_tdata;
    reg  [3:0]  s_tkeep;
    reg         s_tvalid = 0, s_tlast = 0;
    wire        s_tready;
    wire [31:0] m_tdata;
    wire [3:0]  m_tkeep;
    wire        m_tvalid, m_tlast;
    reg         m_tready = 0;

`ifdef POSTSYNTH
    sr_accel_top dut (                         // synthesized netlist (synth_sr_pipe.tcl small: MAXW = 32): no parameters, no internal names
`else
    sr_accel_top #(.MAXW(MAXW), .WDIR("hardware/rtl/weights/")) dut (
`endif
        .aclk(aclk), .aresetn(aresetn),
        .s_axi_awaddr(awaddr), .s_axi_awprot(3'd0), .s_axi_awvalid(awvalid), .s_axi_awready(awready),
        .s_axi_wdata(wdata), .s_axi_wstrb(wstrb), .s_axi_wvalid(wvalid), .s_axi_wready(wready),
        .s_axi_bresp(bresp), .s_axi_bvalid(bvalid), .s_axi_bready(bready),
        .s_axi_araddr(araddr), .s_axi_arprot(3'd0), .s_axi_arvalid(arvalid), .s_axi_arready(arready),
        .s_axi_rdata(rdata), .s_axi_rresp(rresp), .s_axi_rvalid(rvalid), .s_axi_rready(rready),
        .s_axis_tdata(s_tdata), .s_axis_tkeep(s_tkeep), .s_axis_tvalid(s_tvalid), .s_axis_tready(s_tready), .s_axis_tlast(s_tlast),
        .m_axis_tdata(m_tdata), .m_axis_tkeep(m_tkeep), .m_axis_tvalid(m_tvalid), .m_axis_tready(m_tready), .m_axis_tlast(m_tlast));

    integer errors = 0, seed = 11, seed2 = 5, stall = 0, layers = 0, errt = 0, sweep = 0;
    reg     srst_seen = 0;                     // high from a soft-reset write until the next frame starts (the hold rule does not apply across it)

    // ---- AXI-Lite master tasks.  order: 0 AW and W together, 1 AW first (W a few cycles later), 2 W first
    task axil_write(input [5:0] a, input [31:0] d, input [3:0] s, input integer order);
        reg aw_done, w_done, b_done; integer cnt, d2;
        begin
            d2 = 1 + ($random(seed2) & 7);
            @(negedge aclk);
            awaddr = a; wdata = d; wstrb = s;
            awvalid = (order != 2); wvalid = (order != 1);
            aw_done = 0; w_done = 0; b_done = 0; cnt = 0;
            while (!(aw_done && w_done && b_done)) begin
                @(posedge aclk);
                if (awvalid && awready) aw_done = 1;
                if (wvalid && wready) w_done = 1;
                if (bvalid && bready) b_done = 1;
                @(negedge aclk);
                if (aw_done) awvalid = 0;
                if (w_done) wvalid = 0;
                cnt = cnt + 1;
                if (order == 1 && cnt == d2) wvalid = 1;
                if (order == 2 && cnt == d2) awvalid = 1;
                if (cnt > 2000) begin $display("FAIL: AXI-Lite write timeout"); errors = errors + 1; b_done = 1; aw_done = 1; w_done = 1; awvalid = 0; wvalid = 0; end
            end
        end
    endtask
    reg [31:0] rd;
    task axil_read(input [5:0] a);
        reg ar_done, r_done; integer cnt;
        begin
            @(negedge aclk);
            araddr = a; arvalid = 1; ar_done = 0; r_done = 0; cnt = 0;
            while (!r_done) begin
                @(posedge aclk);
                if (arvalid && arready) ar_done = 1;
                if (rvalid && rready) begin r_done = 1; rd = rdata; end
                @(negedge aclk);
                if (ar_done) arvalid = 0;
                cnt = cnt + 1;
                if (cnt > 2000) begin $display("FAIL: AXI-Lite read timeout"); errors = errors + 1; r_done = 1; arvalid = 0; end
            end
        end
    endtask
    task expect_reg(input [5:0] a, input [31:0] exp, input string name);
        begin
            axil_read(a);
            if (rd !== exp) begin $display("FAIL register %s (0x%02h): read 0x%08h, expected 0x%08h", name, a, rd, exp); errors = errors + 1; end
        end
    endtask

    // ---- vectors
    reg [31:0] in_mem [0:MAXB-1];
    reg [31:0] out_mem [0:MAXB-1];
    integer fw, fh, nbi, nbo;
    string  fname;
    task load_frame(input string name);
        integer fd, r, i;
        begin
            fname = name;
            fd = $fopen({"data/golden/pipe/", name, "_meta.txt"}, "r");
            if (fd == 0) begin $display("FAIL missing data/golden/pipe/%s_meta.txt (run gen_pipe_vectors.py)", name); $finish; end
            r = $fscanf(fd, "%d %d %d %d", fw, fh, nbi, nbo); $fclose(fd);
            for (i = 0; i < nbo; i = i + 1) out_mem[i] = 32'hxxxx_xxxx;
            in_mem[nbi - 1] = 32'hxxxx_xxxx;
            $readmemh({"data/golden/pipe/", name, "_in.hex"}, in_mem, 0, nbi - 1);
            $readmemh({"data/golden/pipe/", name, "_out.hex"}, out_mem, 0, nbo - 1);
            if (^in_mem[nbi - 1] === 1'bx || ^out_mem[nbo - 1] === 1'bx) begin $display("FAIL vector files of %s missing or short", name); $finish; end
            if (layers) load_layers(name);
        end
    endtask

    // ---- DMA model
    integer ib, ob, inj;                        // next input beat, output beats received, injected error kind (0 none, 1 early TLAST, 2 no TLAST, 3 TKEEP)
    reg     dma_on = 0, rx_on = 0;
    reg [31:0] hold_d; reg hold_l, hold_v;
    integer s_pre = 0;                          // input beats accepted while the ARM model says no frame is running
    reg     frame_live = 0;
    always @(posedge aclk) begin
        if (s_tvalid && s_tready) begin
            ib <= ib + 1;
            if (!frame_live) s_pre = s_pre + 1;
        end
        if (rx_on && m_tvalid && m_tready) begin
            if (ob >= nbo) begin $display("FAIL extra output beat %0d", ob); errors = errors + 1; end
            else if (m_tdata !== out_mem[ob]) begin
                if (errors < 10) $display("FAIL %s output beat %0d: got %08h expected %08h", fname, ob, m_tdata, out_mem[ob]);
                errors = errors + 1;
            end
            if (m_tlast !== (ob == nbo - 1)) begin $display("FAIL %s TLAST %b on beat %0d of %0d", fname, m_tlast, ob, nbo); errors = errors + 1; end
            if (m_tkeep !== 4'hF) begin $display("FAIL TKEEP %h", m_tkeep); errors = errors + 1; end
            ob = ob + 1;
        end
        if (!rx_on && m_tvalid) begin $display("FAIL m_axis_tvalid while no frame is expected"); errors = errors + 1; rx_on = 1; end
        // AXI hold rule: a beat that was not taken must stay unchanged
        if (hold_v && aresetn && !srst_seen && (!m_tvalid || m_tdata !== hold_d || m_tlast !== hold_l)) begin
            $display("FAIL m_axis changed a beat before it was accepted"); errors = errors + 1;
        end
        hold_v = m_tvalid && !m_tready && !srst_seen; hold_d = m_tdata; hold_l = m_tlast;
    end
    reg s_tready_q;
    always @(posedge aclk) s_tready_q <= s_tready;
    always @(negedge aclk) begin
        if (dma_on && ib < nbi) begin
            if (!(s_tvalid && !s_tready_q))                                  // AXI: a valid beat stays until it is taken
                s_tvalid <= !stall || ($random(seed) % 3) != 0;
            s_tdata <= in_mem[ib]; s_tkeep <= (inj == 3 && ib == nbi / 2) ? 4'h7 : 4'hF;
            s_tlast <= (inj == 1) ? (ib == nbi / 2 || ib == nbi - 1) : (inj == 2) ? 1'b0 : (ib == nbi - 1);
        end else s_tvalid <= 1'b0;
        m_tready <= rx_on && ((stall == 2) ? ($random(seed) % 10 == 0) : (!stall || ($random(seed) % 3) != 0));   // STALL=2: slow DMA sink (buffers fill up)
    end

    // ---- independent cycle count: from the accepted start (1) while the core is busy, until done (the CYCLES register must equal it)
    integer tcyc = 0;
`ifndef POSTSYNTH
    always @(posedge aclk) begin
        if (dut.start_ok) tcyc <= 1;
        else if (dut.core.busy && !dut.core.done) tcyc <= tcyc + 1;
    end
`endif

    // ---- internal stage monitors (+LAYERS=1)
    reg [127:0] l1m [0:MAXB-1];
    reg [127:0] l2m [0:MAXB-1];
    reg [127:0] l3m [0:MAXB-1];
    reg [95:0]  l4m [0:MAXB-1];
    integer n1, n2, n3, n4, k1, k2, k3, k4;
    task load_layers(input string name);
        begin
            n1 = (fw + 4) * (fh + 4); n2 = (fw + 2) * (fh + 2); n3 = n2; n4 = fw * fh;
            $readmemh({"data/golden/pipe/", name, "_L1.hex"}, l1m, 0, n1 - 1);
            $readmemh({"data/golden/pipe/", name, "_L2.hex"}, l2m, 0, n2 - 1);
            $readmemh({"data/golden/pipe/", name, "_L3.hex"}, l3m, 0, n3 - 1);
            $readmemh({"data/golden/pipe/", name, "_L4.hex"}, l4m, 0, n4 - 1);
        end
    endtask
`ifndef POSTSYNTH
    always @(posedge aclk) if (layers && rx_on) begin
        if (dut.core.s1_ov) begin if (dut.core.s1_od !== l1m[k1]) begin if (errors < 10) $display("FAIL L1 pixel %0d: %h vs %h", k1, dut.core.s1_od, l1m[k1]); errors = errors + 1; end k1 = k1 + 1; end
        if (dut.core.s2_ov) begin if (dut.core.s2_od !== l2m[k2]) begin if (errors < 10) $display("FAIL L2 pixel %0d: %h vs %h", k2, dut.core.s2_od, l2m[k2]); errors = errors + 1; end k2 = k2 + 1; end
        if (dut.core.s3_ov) begin if (dut.core.s3_od !== l3m[k3]) begin if (errors < 10) $display("FAIL L3 pixel %0d: %h vs %h", k3, dut.core.s3_od, l3m[k3]); errors = errors + 1; end k3 = k3 + 1; end
        if (dut.core.s4_ov) begin if (dut.core.s4_od !== l4m[k4]) begin if (errors < 10) $display("FAIL L4 pixel %0d: %h vs %h", k4, dut.core.s4_od, l4m[k4]); errors = errors + 1; end k4 = k4 + 1; end
    end
`endif

    // ---- one frame: arm the DMA, set the size, start, wait for DONE
    integer cyc_reg, t;
    task run_frame(input integer inj_kind, input integer exp_code, input integer abort_at);
        begin
            ib = 0; ob = 0; inj = inj_kind; k1 = 0; k2 = 0; k3 = 0; k4 = 0;
            srst_seen = 0;
            dma_on = 1; rx_on = 1;
            repeat (5 + ($random(seed2) & 15)) @(negedge aclk);            // the DMA is armed before start: nothing may be accepted yet
            if (ib != 0) begin $display("FAIL input accepted before start"); errors = errors + 1; end
            axil_write(6'h08, fw, 4'hF, $random(seed2) & 1);
            axil_write(6'h18, fh, 4'hF, 2);
            frame_live = 1;
            axil_write(6'h00, 32'd1, 4'h1, $random(seed2) & 1);
            t = 0;
            while (ob < nbo && t < 40 * nbi + 20 * nbo + 20000 && !(abort_at > 0 && t >= abort_at)) begin @(negedge aclk); t = t + 1; end
            if (abort_at > 0 && t >= abort_at) begin
                srst_seen = 1;
                axil_write(6'h00, 32'd2, 4'h1, 0);                          // soft reset
                frame_live = 0; dma_on = 0; rx_on = 0;
                repeat (300) begin @(negedge aclk); if (m_tvalid || s_tready) begin $display("FAIL stream activity after the soft reset"); errors = errors + 1; end end
                expect_reg(6'h04, 32'd0, "STATUS after soft reset");
            end else begin
                if (ob != nbo) begin $display("FAIL %s: %0d of %0d output beats (timeout)", fname, ob, nbo); errors = errors + 1; end
                axil_read(6'h04);
                while (rd[0]) axil_read(6'h04);
                frame_live = 0;
                if (rd[1] !== 1'b1) begin $display("FAIL STATUS.done not set (0x%h)", rd); errors = errors + 1; end
                if (rd[2] !== (exp_code != 0)) begin $display("FAIL STATUS.error %b, expected %0d", rd[2], exp_code != 0); errors = errors + 1; end
                expect_reg(6'h10, exp_code, "ERROR_CODE");
                if (inj_kind == 0) begin
                    expect_reg(6'h20, nbi, "DBG_IN_BEATS");
                    expect_reg(6'h24, nbo, "DBG_OUT_BEATS");
                    if (ib != nbi) begin $display("FAIL %0d input beats taken, expected %0d", ib, nbi); errors = errors + 1; end
                    if (layers && (k1 != n1 || k2 != n2 || k3 != n3 || k4 != n4)) begin $display("FAIL stage output counts %0d %0d %0d %0d", k1, k2, k3, k4); errors = errors + 1; end
                end
                axil_read(6'h0C); cyc_reg = rd;
`ifndef POSTSYNTH
                if (cyc_reg != tcyc) begin $display("FAIL CYCLES register %0d, independent count %0d", cyc_reg, tcyc); errors = errors + 1; end
`endif
                // throughput: without stalls a frame takes 16 cycles per layer-1 output pixel plus at most 12 per padded row plus 200 (fill, I/O, control)
                if (!stall && inj_kind == 0 && cyc_reg > 16 * (fw + 4) * (fh + 4) + 12 * (fw + 6) + 200) begin
                    $display("FAIL %s: CYCLES %0d above the throughput bound %0d", fname, cyc_reg, 16 * (fw + 4) * (fh + 4) + 12 * (fw + 6) + 200); errors = errors + 1;
                end
                repeat (40) @(negedge aclk);
                dma_on = 0; rx_on = 0;
            end
        end
    endtask

    integer nf, i2, fails_before, pa;
    string fnm, lst, ext;
    reg [31:0] cyc0;
    initial begin
        if (!$value$plusargs("STALL=%d", stall)) stall = 0;
        if (!$value$plusargs("LAYERS=%d", layers)) layers = 0;
        if (!$value$plusargs("ERR=%d", errt)) errt = 0;
        if (!$value$plusargs("SWEEP=%d", sweep)) sweep = 0;
`ifdef POSTSYNTH
        if (layers) begin $display("FAIL +LAYERS needs the RTL (the netlist has no internal names)"); $finish; end
        wait (glbl.GSR == 1'b0);                                   // the netlist's flip-flops are held by the global set/reset for the first 100 ns
`else
        if (dut.core.SHIFT1 != L1_SHIFT || dut.core.SHIFT2 != L2_SHIFT || dut.core.SHIFT3 != L3_SHIFT || dut.core.SHIFT4 != L4_SHIFT || dut.core.ANCHOR != NET_ANCHOR) begin
            $display("FAIL default SHIFT/ANCHOR parameters of sr_pipe_core differ from network_params.vh"); $finish;
        end
`endif
        repeat (4) @(negedge aclk); aresetn = 1; repeat (2) @(negedge aclk);
        // quiet after reset
        repeat (50) begin @(negedge aclk); if (s_tready || m_tvalid) begin $display("FAIL stream activity after reset"); errors = errors + 1; end end
        expect_reg(6'h14, 32'h5352_5301, "VERSION");
        expect_reg(6'h1C, MAXW - 6, "MAX_W");
        expect_reg(6'h04, 32'd0, "STATUS");
        expect_reg(6'h10, 32'd0, "ERROR_CODE");
        expect_reg(6'h08, 32'd0, "FRAME_W (reset)");
        expect_reg(6'h30, 32'd0, "unmapped 0x30");
        axil_write(6'h14, 32'hFFFF_FFFF, 4'hF, 0); expect_reg(6'h14, 32'h5352_5301, "VERSION (write)");
        axil_write(6'h08, 32'h1234_0567, 4'h1, 1); expect_reg(6'h08, 32'h0000_0067, "FRAME_W (wstrb 0001)");
        axil_write(6'h18, 32'hABCD_0102, 4'h3, 2); expect_reg(6'h18, 32'h0000_0102, "FRAME_H");
        axil_write(6'h00, 32'd1, 4'h0, 0); repeat (5) @(negedge aclk); expect_reg(6'h04, 32'd0, "STATUS (start with wstrb 0)");
        nf = 0; lst = "";
        for (i2 = 0; i2 < 8; i2 = i2 + 1) begin
            if ($value$plusargs($sformatf("F%0d=%%s", i2), fnm)) begin
                load_frame(fnm);
                run_frame(0, 0, 0);
                if (i2 == 0) cyc0 = cyc_reg;
                lst = $sformatf("%s %s(%0dx%0d, CYCLES %0d)", lst, fnm, fw, fh, cyc_reg);
                nf = nf + 1;
            end
        end
        if (nf == 0) begin $display("FAIL no frames given (+F0=<name>)"); $finish; end
        if (errt) begin
            pa = $value$plusargs("F0=%s", fnm); load_frame(fnm);
            run_frame(1, 1, 0); axil_write(6'h00, 32'd2, 4'h1, 0);
            run_frame(2, 2, 0); axil_write(6'h00, 32'd2, 4'h1, 0);
            run_frame(3, 3, 0); axil_write(6'h00, 32'd2, 4'h1, 0);
            run_frame(0, 0, 0);
            // frame size out of range: start refused, ERROR_CODE 4, nothing accepted
            // (a refused start changes neither DONE nor anything else: STATUS = done + error after a finished frame)
            axil_write(6'h08, 32'd0, 4'hF, 0); axil_write(6'h00, 32'd1, 4'h1, 0); repeat (20) @(negedge aclk);
            expect_reg(6'h04, 32'd6, "STATUS (W = 0)"); expect_reg(6'h10, 32'd4, "ERROR_CODE (W = 0)");
            axil_write(6'h00, 32'd2, 4'h1, 0);
            axil_write(6'h08, MAXW - 5, 4'hF, 0); axil_write(6'h00, 32'd1, 4'h1, 0); repeat (20) @(negedge aclk);
            expect_reg(6'h04, 32'd4, "STATUS (W = MAX_W + 1)"); expect_reg(6'h10, 32'd4, "ERROR_CODE (W = MAX_W + 1)");
            axil_write(6'h00, 32'd2, 4'h1, 0);
            axil_write(6'h08, 32'd5, 4'hF, 0); axil_write(6'h18, 32'd0, 4'hF, 0); axil_write(6'h00, 32'd1, 4'h1, 0);
            repeat (20) @(negedge aclk); expect_reg(6'h10, 32'd4, "ERROR_CODE (H = 0)");
            if (s_tready) begin $display("FAIL s_axis_tready after a refused start"); errors = errors + 1; end
            axil_write(6'h00, 32'd2, 4'h1, 0);
            run_frame(0, 0, 0);
        end
        for (i2 = 0; i2 < sweep; i2 = i2 + 1) begin
            pa = $value$plusargs("F0=%s", fnm); load_frame(fnm);
            run_frame(0, 0, 1 + (i2 * 2731 + 97) % (cyc0 + 50));
            run_frame(0, 0, 0);
        end
        if (s_pre != 0) begin $display("FAIL %0d input beats accepted outside a frame", s_pre); errors = errors + 1; end
        ext = "";
        if (stall == 1) ext = {ext, ", random stalls"};
        if (stall == 2) ext = {ext, ", slow output sink"};
        if (layers) ext = {ext, ", every stage output exact"};
        if (errt)   ext = {ext, ", error codes 1-4 + recovery"};
        if (sweep)  ext = $sformatf("%s, %0d soft-reset aborts + quiet checks", ext, sweep);
        if (errors == 0) $display("PASS sr_pipe_top%s: %0d frame(s) bit-exact via AXI-Lite + AXI-Stream%s", lst, nf, ext);
        else $display("FAIL sr_pipe_top: %0d errors", errors);
        $finish;
    end
endmodule
