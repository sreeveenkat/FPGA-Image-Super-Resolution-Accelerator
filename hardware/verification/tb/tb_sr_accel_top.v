// Self-checking testbench for sr_accel_top (M6 prep): behaves like the ARM driver + AXI DMA.  Run from the project root.
//   iverilog -g2012 -I . -P tb_sr_accel_top.HC=6 ... ; vvp ... [+TILE=small12] [+TILE2=small12b] [+STALL=1] [+REPEAT] [+NOEXTRA]
// Driver order (as in the C driver): output side ready, input data offered BEFORE CONTROL.start is written, then poll STATUS until done.
// Always checks : VERSION, TILE_SIZE, reset values, CONTROL reads 0, read-only registers ignore writes, unmapped addresses read 0, wstrb=0 write
//                 does not start; AXI-Lite write with AW/W in any order and random BREADY/RREADY; golden tile bit-exact (every beat, count, TLAST only
//                 on the last beat, TKEEP F, m_axis hold rule, nothing moves outside a tile); nothing accepted before start; busy/done/error in STATUS
//                 (done sticky after the run, cleared by the next start, busy low after); CYCLES == the core's cycle counter; no X on any output.
// With a second tile (+TILE2) : back to back, no reset, exact.
// +OFFSWEEP[=N] : START-vs-first-beat race sweep: the first input beat is offered from N cycles BEFORE to N cycles AFTER the start pulse (default 20),
//                 for every AW/W order of the START write, without gaps and with a gap pattern; every tile must be exact with ERROR_CODE 0 and exact beat counts.
//                 The covered offsets (first offered beat minus start_r pulse, measured) are printed.
// +OFFFEW        : the same at 6 points only (issue delays -6 -2 0 5 10 24, all three AW/W orders, gaps on every second one; the measured offsets are
//                 printed and must include negative and positive values): for HC=64.
// Extra (default for HC <= 8, or +REPEAT): start while busy ignored, early TLAST -> ERROR_CODE 1, missing TLAST -> 2, TKEEP != F -> 3, flags cleared by
//                 the next start, soft reset at many moments (quiet afterwards, STATUS cleared) and a fresh exact tile after each series.
`timescale 1ns/1ps
module tb_sr_accel_top;
    parameter HC = 6;
    localparam NIN  = (HC + 6) * (HC + 6) * 3;
    localparam NOUT = (2 * HC) * (2 * HC) * 3;
    localparam NWI  = NIN / 4, NWO = NOUT / 4;

    // HC rule: 32-bit beats need byte counts that are multiples of 4 (fail at time 0, the RTL has no elaboration-time check)
    initial if (((HC + 6) * (HC + 6) * 3) % 4 != 0 || ((2 * HC) * (2 * HC) * 3) % 4 != 0) begin
        $display("FAIL sr_accel_top: HC=%0d gives byte counts that are not multiples of 4 ((HC+6)^2*3 = %0d, (2HC)^2*3 = %0d)", HC, (HC + 6) * (HC + 6) * 3, (2 * HC) * (2 * HC) * 3);
        $finish;
    end

    reg aclk = 0, aresetn = 0;
    always #5 aclk = ~aclk;

    // AXI-Lite master side
    reg  [5:0]  awaddr = 0;  reg awvalid = 0;  wire awready;
    reg  [31:0] wdata = 0;   reg [3:0] wstrb = 0; reg wvalid = 0; wire wready;
    wire [1:0]  bresp;       wire bvalid;      reg bready = 1;
    reg  [5:0]  araddr = 0;  reg arvalid = 0;  wire arready;
    wire [31:0] rdata;       wire [1:0] rresp; wire rvalid; reg rready = 1;
    // streams
    reg  [31:0] s_tdata = 0; reg [3:0] s_tkeep = 4'hF; reg s_tvalid = 0, s_tlast = 0; wire s_tready;
    wire [31:0] m_tdata; wire [3:0] m_tkeep; wire m_tvalid, m_tlast; reg m_tready = 0;

    sr_accel_top #(.HC(HC), .WDIR("hardware/rtl/weights/")) dut (
        .aclk(aclk), .aresetn(aresetn),
        .s_axi_awaddr(awaddr), .s_axi_awprot(3'b000), .s_axi_awvalid(awvalid), .s_axi_awready(awready),
        .s_axi_wdata(wdata), .s_axi_wstrb(wstrb), .s_axi_wvalid(wvalid), .s_axi_wready(wready),
        .s_axi_bresp(bresp), .s_axi_bvalid(bvalid), .s_axi_bready(bready),
        .s_axi_araddr(araddr), .s_axi_arprot(3'b000), .s_axi_arvalid(arvalid), .s_axi_arready(arready),
        .s_axi_rdata(rdata), .s_axi_rresp(rresp), .s_axi_rvalid(rvalid), .s_axi_rready(rready),
        .s_axis_tdata(s_tdata), .s_axis_tkeep(s_tkeep), .s_axis_tvalid(s_tvalid), .s_axis_tready(s_tready), .s_axis_tlast(s_tlast),
        .m_axis_tdata(m_tdata), .m_axis_tkeep(m_tkeep), .m_axis_tvalid(m_tvalid), .m_axis_tready(m_tready), .m_axis_tlast(m_tlast));

    reg [7:0]  inmem  [0:NIN-1];
    reg [7:0]  expout [0:NOUT-1];
    reg [31:0] rxw    [0:NWO-1];
    reg [8*200-1:0] f_in, f_out;
    integer errors, stall, wi, rn, bad, inject, seed = 2024, seed2 = 99;
    reg feed_en = 0, acc = 0, watch_quiet = 0, check_x = 0;
    reg pv = 0, pr = 0, pl = 0; reg [31:0] pd = 0;           // previous m_axis beat (hold rule)
    reg sp = 0, rp = 0, in_tile = 0;
    reg bpv = 0, bpr = 0, rpv = 0, rpr = 0; reg [31:0] rpd = 0;  // previous B / R beats (hold rule)
    integer i, j, p, tmo;
    integer cyc = 0, gapmode = 0, t_beat = -1, t_start = -1;
    integer n_start_ok = 0, n_start_ign = 0;                      // monitor counts for the DBG_STARTS register     // offset sweep: cycle counter, gap pattern on/off, first offered beat / start pulse

    function [31:0] word(input integer k);
        word = {inmem[4*k+3], inmem[4*k+2], inmem[4*k+1], inmem[4*k]};
    endfunction

    // ---- DMA model + random AXI-Lite handshakes, driven on the falling edge
    // inject: bit0 TLAST on input beat 5 (early), bit1 no TLAST on the last beat, bit2 TKEEP = 0111 on beat 7
    always @(negedge aclk) begin
        if (feed_en && wi < NWI) begin
            if (s_tvalid && !acc) begin
                // beat offered, not accepted at the last rising edge: hold it (AXI rule)
            end else begin
                s_tdata  <= word(wi);
                s_tlast  <= ((wi == NWI - 1) && !(inject & 2)) || ((wi == 5) && (inject & 1));
                s_tkeep  <= ((wi == 7) && (inject & 4)) ? 4'b0111 : 4'hF;
                s_tvalid <= ((stall && ($random(seed) & 3) == 0) || (gapmode && (cyc % 5 == 2 || cyc % 7 == 0))) ? 1'b0 : 1'b1;
            end
        end else s_tvalid <= 1'b0;
        m_tready <= (stall && ($random(seed) & 3) == 0) ? 1'b0 : 1'b1;
        bready   <= (stall && ($random(seed) & 3) == 0) ? 1'b0 : 1'b1;
        rready   <= (stall && ($random(seed) & 3) == 0) ? 1'b0 : 1'b1;
    end

    // ---- monitors at the rising edge
    always @(posedge aclk) begin
        cyc <= cyc + 1;
        if (dut.start_r && !dut.wrap.busy) n_start_ok <= n_start_ok + 1;
        if (dut.start_r && dut.wrap.busy)  n_start_ign <= n_start_ign + 1;
        if (s_tvalid && t_beat < 0) t_beat <= cyc;
        if (dut.start_r && t_start < 0) t_start <= cyc;
        acc <= s_tvalid && s_tready;
        if (s_tvalid && s_tready) wi <= wi + 1;
        if (m_tvalid && m_tready) begin
            if (rn < NWO) rxw[rn] <= m_tdata;
            if (m_tlast != (rn == NWO - 1)) bad <= bad + 1;
            rn <= rn + 1;
        end
        if (pv && !pr && !(m_tvalid && m_tdata === pd && m_tlast === pl)) bad <= bad + 1;     // m_axis hold rule
        pv <= m_tvalid; pr <= m_tready; pd <= m_tdata; pl <= m_tlast;
        if (m_tvalid && m_tkeep !== 4'hF) bad <= bad + 1;
        if ((s_tready || m_tvalid) && !dut.wrap.busy) bad <= bad + 1;                           // nothing moves outside a tile
        if (bpv && !bpr && !bvalid) bad <= bad + 1;                                              // B / R must be held until accepted
        if (rpv && !rpr && !(rvalid && rdata === rpd)) bad <= bad + 1;
        bpv <= bvalid; bpr <= bready; rpv <= rvalid; rpr <= rready; rpd <= rdata;
        if (watch_quiet && (dut.wrap.busy || s_tready || m_tvalid)) bad <= bad + 1000;
        if (check_x && ((^{awready, wready, bresp, bvalid, arready, rdata, rresp, rvalid, s_tready,
                           m_tdata, m_tkeep, m_tvalid, m_tlast}) === 1'bx)) bad <= bad + 1;      // no X on any output once the first reset is over
        // start / soft reset must be ONE-cycle pulses
        sp <= dut.start_r; rp <= dut.srst_r;
        if (sp && dut.start_r) bad <= bad + 1;
        if (rp && dut.srst_r) bad <= bad + 1;
        // from the accepted start until DONE is set, STATUS must never read 'idle' (busy = 0 and done = 0)
        if (dut.srst_r || !aresetn) in_tile <= 1'b0;
        else if (dut.start_r && !dut.wrap.busy) in_tile <= 1'b1;
        else if (dut.done_s) in_tile <= 1'b0;
        if (in_tile && !dut.done_s && !dut.srst_r && !dut.busy_st) bad <= bad + 1;
        if (bvalid && bresp != 0) bad <= bad + 1;
        if (rvalid && rresp != 0) bad <= bad + 1;
    end

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

    task expect_reg(input [5:0] a, input [31:0] exp, input [8*16-1:0] name);
        begin
            axil_read(a);
            if (rd !== exp) begin errors = errors + 1; $display("  register %0s (0x%02x): got %08x expected %08x", name, a, rd, exp); end
        end
    endtask

    task load_tile(input [8*64-1:0] name);
        begin
            $sformat(f_in,  "data/golden/%0s_in.hex",  name);
            $sformat(f_out, "data/golden/%0s_out.hex", name);
            for (i = 0; i < NIN; i = i + 1) inmem[i] = 8'hxx;
            $readmemh(f_in, inmem);
            j = 0; for (i = 0; i < NIN; i = i + 1) if (^inmem[i] === 1'bx) j = j + 1;
            if (j != 0) begin $display("FAIL: %0d undefined bytes in %0s (missing or short?)", j, f_in); $finish; end
            for (i = 0; i < NOUT; i = i + 1) expout[i] = 8'hxx;
            $readmemh(f_out, expout);
            j = 0; for (i = 0; i < NOUT; i = i + 1) if (^expout[i] === 1'bx) j = j + 1;
            if (j != 0) begin $display("FAIL: %0d undefined bytes in %0s", j, f_out); $finish; end
        end
    endtask

    // one tile, driven like the ARM: DMA armed first, then CONTROL.start, then poll STATUS.  exp_code: expected ERROR_CODE (0 = none).
    // dbl: write CONTROL.start two more times while the tile runs (four times mid-load, once mid-compute): must be ignored.
    integer cyc_reg, cyc_core, npoll;
    reg first_poll_ok;
    task run_tile(input integer inj, input integer exp_code, input integer dbl);
        reg fin;
        begin
            wi = 0; rn = 0; bad = 0; inject = inj; npoll = 0;
            feed_en = 1;
            repeat (8) @(negedge aclk);
            if (wi != 0) begin errors = errors + 1; $display("  input accepted before CONTROL.start"); end
            axil_write(6'h00, 32'd1, 4'hF, npoll_order(0));
            if (dbl) begin
                // ignored starts: during the load phase at 1/6, 2/6, 3/6, 4/6 of the input beats, then while the layers compute
                for (i = 1; i <= 4; i = i + 1) begin                    // several points: a single one can coincide with a beat being accepted
                    while (wi < (NWI * i) / 6) @(negedge aclk);
                    axil_write(6'h00, 32'd1, 4'hF, i % 3);
                end
                while (wi < NWI) @(negedge aclk);
                repeat (3000) @(negedge aclk);
                axil_write(6'h00, 32'd1, 4'hF, 0);
            end
            tmo = 0; fin = 0;
            while (!fin && tmo < 40000) begin   // ~7M cycles at the average poll gap
                axil_read(6'h04);
                if (npoll == 0 && (rd[1] || !rd[0] || rd[2])) begin errors = errors + 1; $display("  first STATUS after start: %b (expect busy, not done, no error)", rd[2:0]); end
                npoll = npoll + 1;
                if (rd[1]) fin = 1;
                else begin repeat (50 + ($random(seed2) & 255)) @(negedge aclk); tmo = tmo + 1; end
            end
            if (!fin) begin errors = errors + 1; $display("FAIL: timeout (words in %0d/%0d, out %0d/%0d)", wi, NWI, rn, NWO); end
            feed_en = 0;
            repeat (10) @(negedge aclk);
            check_tile(exp_code);
        end
    endtask

    function integer npoll_order(input dummy);   // vary the write channel order from run to run
        begin npoll_order = ($random(seed2) & 3) % 3; end
    endfunction

    task check_tile(input integer exp_code);
        reg [31:0] e;
        begin
            if (wi != NWI) begin errors = errors + 1; $display("  input beats accepted %0d, expected %0d", wi, NWI); end
            if (rn != NWO) begin errors = errors + 1; $display("  output beats %0d, expected %0d", rn, NWO); end
            if (bad != 0)  begin errors = errors + 1; $display("  protocol violations: %0d (TLAST position / hold rules / activity outside a tile / X)", bad); end
            for (p = 0; p < NWO; p = p + 1) begin
                e = {expout[4*p+3], expout[4*p+2], expout[4*p+1], expout[4*p]};
                if (rxw[p] !== e) begin errors = errors + 1; if (errors < 6) $display("  output beat %0d: got %08x exp %08x", p, rxw[p], e); end
            end
            axil_read(6'h04);
            if (rd !== {29'd0, exp_code != 0, 1'b1, 1'b0}) begin errors = errors + 1; $display("  STATUS after run %08x, expected done=1 busy=0 error=%0d", rd, exp_code != 0); end
            repeat (30) @(negedge aclk);
            axil_read(6'h04);                                                      // done must be STICKY
            if (rd !== {29'd0, exp_code != 0, 1'b1, 1'b0}) begin errors = errors + 1; $display("  STATUS 30 cycles later %08x (done not sticky?)", rd); end
            expect_reg(6'h10, exp_code, "ERROR_CODE");
            axil_read(6'h0C); cyc_reg = rd; cyc_core = dut.wrap.cycles;
            if (cyc_reg !== cyc_core || cyc_reg == 0) begin errors = errors + 1; $display("  CYCLES register %0d, core counter %0d", cyc_reg, cyc_core); end
            // debug registers (VERSION 0602): beat counts, first TLAST position, error snapshot, beats outside a tile, start counters
            expect_reg(6'h18, NWI, "DBG_IN_BEATS");
            expect_reg(6'h1C, (exp_code == 1) ? 6 : (exp_code == 2) ? 0 : NWI, "DBG_TLAST_AT");
            expect_reg(6'h24, 0, "DBG_PRE_BEATS");
            expect_reg(6'h2C, (exp_code == 0) ? 0 : (exp_code == 1) ? 6 : (exp_code == 2) ? NWI : 8, "DBG_ERR_BEATS");
            axil_read(6'h30);
            if ((exp_code == 0 && rd !== 0) || (exp_code != 0 && (rd == 0 || rd > cyc_reg))) begin errors = errors + 1; $display("  DBG_ERR_CYCLES %0d (CYCLES %0d, error %0d)", rd, cyc_reg, exp_code); end
            expect_reg(6'h28, {n_start_ign[15:0], n_start_ok[15:0]}, "DBG_STARTS");
        end
    endtask


    // START-vs-first-beat race: d < 0 -> offer the input |d| cycles before issuing the START write; d >= 0 -> issue the write, offer the input d cycles later.
    // The real offset (first offered beat minus the start_r pulse) is measured; the caller sweeps d so that the measured offsets cover the wanted range.
    integer off_min, off_max, off_n, ord_i;
    task run_tile_offset(input integer d, input integer order);
        reg fin;
        begin
            wi = 0; rn = 0; bad = 0; inject = 0; t_beat = -1; t_start = -1;
            if (d < 0) begin
                feed_en = 1; repeat (-d) @(negedge aclk);
                axil_write(6'h00, 32'd1, 4'hF, order);
            end else begin
                fork
                    axil_write(6'h00, 32'd1, 4'hF, order);
                    begin repeat (d) @(negedge aclk); feed_en = 1; end
                join
            end
            tmo = 0; fin = 0;
            while (!fin && tmo < 40000) begin
                axil_read(6'h04);
                if (rd[1]) fin = 1; else begin repeat (20 + ($random(seed2) & 63)) @(negedge aclk); tmo = tmo + 1; end
            end
            if (!fin) begin errors = errors + 1; $display("FAIL: timeout (words in %0d/%0d, out %0d/%0d)", wi, NWI, rn, NWO); end
            feed_en = 0;
            repeat (10) @(negedge aclk);
            if (t_beat - t_start < off_min) off_min = t_beat - t_start;
            if (t_beat - t_start > off_max) off_max = t_beat - t_start;
            off_n = off_n + 1;
            j = errors;
            axil_read(6'h20);
            if (rd[31] !== (t_beat <= t_start) || (t_beat > t_start && rd[30:0] < t_beat - t_start - 1)) begin
                errors = errors + 1; $display("  DBG_START2BEAT %08x for a first beat offered %0d cycles after the start pulse", rd, t_beat - t_start); end
            check_tile(0);
            if (errors != j) $display("  ^ offset sweep: d=%0d order=%0d gap=%0d, first beat offered %0d cycles after the start pulse", d, order, gapmode, t_beat - t_start);
        end
    endtask

    integer sweep_n, n_sweep, abort_at, step_len, t_total, mode_extra;
    reg [8*64-1:0] tile, tile2;
    initial begin
        errors = 0; inject = 0; wi = 0; rn = 0; bad = 0;
        if (!$value$plusargs("STALL=%d", stall)) stall = 0;
        if (!$value$plusargs("TILE=%s", tile)) tile = (HC == 64) ? "real0" : "small12";
        if (!$value$plusargs("TILE2=%s", tile2)) tile2 = "";
        mode_extra = (((HC <= 8) && !$test$plusargs("NOEXTRA")) || $test$plusargs("REPEAT"));
        repeat (4) @(negedge aclk); aresetn = 1; repeat (2) @(negedge aclk);
        check_x = 1;
        // ---- registers
        expect_reg(6'h14, 32'h5352_4301, "VERSION");
        expect_reg(6'h08, HC, "TILE_SIZE");
        expect_reg(6'h04, 32'd0, "STATUS");
        expect_reg(6'h10, 32'd0, "ERROR_CODE");
        expect_reg(6'h00, 32'd0, "CONTROL");
        expect_reg(6'h20, 32'd0, "DBG_START2BEAT (reset)");
        expect_reg(6'h3C, 32'd0, "unmapped 0x3C");
        expect_reg(6'h34, 32'd0, "unmapped 0x34");
        expect_reg(6'h24, 32'd0, "DBG_PRE_BEATS (reset)");
        expect_reg(6'h28, 32'd0, "DBG_STARTS (reset)");
        axil_write(6'h14, 32'hFFFF_FFFF, 4'hF, 0); expect_reg(6'h14, 32'h5352_4301, "VERSION (write)");
        axil_write(6'h08, 32'd3, 4'hF, 1);         expect_reg(6'h08, HC, "TILE_SIZE (write)");
        axil_write(6'h0C, 32'd5, 4'hF, 2);         axil_write(6'h04, 32'hFFFF_FFFF, 4'hF, 0);
        expect_reg(6'h04, 32'd0, "STATUS (write)");
        // a CONTROL write with wstrb = 0 must not start anything (the DMA is armed, nothing may be accepted)
        wi = 0; rn = 0; bad = 0; feed_en = 1; axil_write(6'h00, 32'd1, 4'b1110, 0); repeat (20) @(negedge aclk); feed_en = 0;
        if (wi != 0 || dut.wrap.busy) begin errors = errors + 1; $display("  CONTROL write with wstrb=0 started the core"); end
        axil_write(6'h00, 32'd2, 4'hF, 0); repeat (6) @(negedge aclk);         // a soft reset on an idle core is harmless
        // ---- tiles
        load_tile(tile);
        run_tile(0, 0, 0);
        t_total = cyc_reg;
        $display("INFO HC=%0d tile %0s: CYCLES register = %0d (core counter %0d)%0s", HC, tile, cyc_reg, cyc_core, stall ? ", random stalls" : "");
        if (tile2 != "") begin load_tile(tile2); run_tile(0, 0, 0); end       // back to back, no reset
        if ($test$plusargs("OFFFEW")) begin
            off_min = 1 << 30; off_max = -(1 << 30); off_n = 0;
            gapmode = 0; run_tile_offset(-6, 0);
            gapmode = 1; run_tile_offset(-2, 1);
            gapmode = 0; run_tile_offset(0, 2);
            gapmode = 1; run_tile_offset(5, 0);
            gapmode = 0; run_tile_offset(10, 1);
            gapmode = 1; run_tile_offset(24, 2);
            gapmode = 0;
            $display("INFO offset points: %0d tiles, first input beat offered from %0d to %0d cycles relative to the start pulse", off_n, off_min, off_max);
            if (off_min >= 0 || off_max <= 0) begin errors = errors + 1; $display("FAIL: offset points do not include both signs"); end
        end
        if ($value$plusargs("OFFSWEEP=%d", n_sweep) || $test$plusargs("OFFSWEEP")) begin
            if (!$value$plusargs("OFFSWEEP=%d", n_sweep)) n_sweep = 20;
            off_min = 1 << 30; off_max = -(1 << 30); off_n = 0;
            for (gapmode = 0; gapmode < 2; gapmode = gapmode + 1)
                for (ord_i = 0; ord_i < 3; ord_i = ord_i + 1)
                    for (sweep_n = -n_sweep - 4; sweep_n <= n_sweep + 6; sweep_n = sweep_n + 1) run_tile_offset(sweep_n, ord_i);
            gapmode = 0;
            $display("INFO offset sweep: %0d tiles, first input beat offered from %0d to %0d cycles relative to the start pulse, AW/W orders 0-2, gaps off/on",
                     off_n, off_min, off_max);
            if (off_min > -n_sweep || off_max < n_sweep) begin errors = errors + 1; $display("FAIL: offset sweep did not cover -%0d..+%0d", n_sweep, n_sweep); end
        end
        if (errors == 0 && mode_extra) begin
            load_tile(tile);
            seed2 = seed2 + 5; run_tile(0, 0, 0);                            // same tile again, other write orders
            run_tile(0, 0, 1);                                               // second start while busy: ignored, output unharmed, no error
            run_tile(1, 1, 0);                                               // early TLAST            -> ERROR_CODE 1
            run_tile(2, 2, 0);                                               // last beat without TLAST -> ERROR_CODE 2
            run_tile(4, 3, 0);                                               // TKEEP != F             -> ERROR_CODE 3
            run_tile(5, 1, 0);                                               // early TLAST + bad TKEEP: the FIRST error is kept
            run_tile(0, 0, 0);                                               // next start clears DONE and ERROR
            // soft reset at many moments, then quiet + cleared STATUS, then a fresh exact tile
            if (!$value$plusargs("SWEEP=%d", n_sweep)) n_sweep = (HC <= 8) ? 24 : 6;
            step_len = t_total / n_sweep;
            for (sweep_n = 0; sweep_n < n_sweep; sweep_n = sweep_n + 1) begin
                abort_at = 20 + sweep_n * step_len + (sweep_n * 7) % 13;
                wi = 0; rn = 0; bad = 0; inject = 0; feed_en = 1;
                repeat (3) @(negedge aclk);
                axil_write(6'h00, 32'd1, 4'hF, 0);
                repeat (abort_at) @(negedge aclk);
                axil_write(6'h00, 32'd2, 4'hF, sweep_n % 3);                  // soft reset
                feed_en = 0; watch_quiet = 1;
                repeat (300) @(negedge aclk);
                watch_quiet = 0;
                if (bad >= 1000) begin errors = errors + 1; $display("  not quiet after soft reset at +%0d cycles", abort_at); end
                axil_read(6'h04);
                if (rd[1:0] !== 2'b00) begin errors = errors + 1; $display("  STATUS %08x after soft reset (busy/done must be 0)", rd); end
            end
            run_tile(0, 0, 0);                                               // fresh tile after all the resets
        end
        if (errors == 0)
            $display("PASS sr_accel_top HC=%0d tile %0s: %0d output beats bit-exact via AXI-Lite + AXI-Stream, CYCLES=%0d%0s%0s%0s",
                     HC, tile, NWO, t_total, stall ? ", random stalls" : "", (tile2 != "") ? ", 2nd tile back to back" : "",
                     mode_extra ? ", start-while-busy + error codes + soft-reset sweep OK" : "");
        else
            $display("FAIL sr_accel_top HC=%0d tile %0s: %0d errors", HC, tile, errors);
        $finish;
    end
endmodule
