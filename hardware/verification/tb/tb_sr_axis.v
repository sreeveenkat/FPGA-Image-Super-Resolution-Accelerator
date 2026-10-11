// Self-checking testbench for sr_axis_wrapper (M6 prep).  Run from the project root.  Acts as the AXI DMA:
//   iverilog -g2012 -I . -P tb_sr_axis.HC=6 ... ; vvp ... +TILE=small12 [+STALL=1] [+TILE2=name] [+NOEXTRA]
// Stimulus: the golden input bytes (data/golden/<tile>_in.hex) packed little-endian into 32-bit words, sent BEFORE `start` (DMA armed early),
//   with random gaps in TVALID (never dropping a pending beat) and random TREADY on the output.
// Checks (every run): output words == golden output bytes packed little-endian, exact count, TLAST on the last word only, TKEEP = F,
//   m_axis holds TVALID/TDATA/TLAST until accepted, s_axis_tready/m_axis_tvalid only while busy (nothing accepted before start), exactly one
//   `done` pulse after the last output word, busy low afterwards, error_flags = 0, no X on control outputs.
// Extra (default for HC <= 8, or +REPEAT): same tile again (no reset), a second tile, error injection (early TLAST, missing TLAST, both ->
//   error_flags 001 / 010 / 011, data still exact, flags cleared by the next start), start while busy (flag 100, output unharmed),
//   a sweep of ONE-cycle aborts (alternating aresetn and soft_rst) at many moments with a quiet check, and a fresh tile at the end.
`timescale 1ns/1ps
module tb_sr_axis;
    parameter HC = 6;
    localparam NIN  = (HC + 6) * (HC + 6) * 3;          // input bytes
    localparam NOUT = (2 * HC) * (2 * HC) * 3;          // output bytes
    localparam NWI  = NIN / 4, NWO = NOUT / 4;

    reg aclk = 0, aresetn = 0, soft_rst = 0, start = 0;
    always #5 aclk = ~aclk;
    reg [31:0] s_tdata = 0; reg s_tvalid = 0, s_tlast = 0; wire s_tready;
    wire [31:0] m_tdata; wire m_tvalid, m_tlast; reg m_tready = 0; wire [3:0] m_tkeep;
    wire busy, done; wire [31:0] cycles; wire [2:0] err;

    sr_axis_wrapper #(.HC(HC)) dut (
        .aclk(aclk), .aresetn(aresetn), .soft_rst(soft_rst), .start(start), .busy(busy), .done(done), .cycles(cycles), .error_flags(err),
        .s_axis_tdata(s_tdata), .s_axis_tvalid(s_tvalid), .s_axis_tready(s_tready), .s_axis_tlast(s_tlast),
        .m_axis_tdata(m_tdata), .m_axis_tvalid(m_tvalid), .m_axis_tready(m_tready), .m_axis_tlast(m_tlast), .m_axis_tkeep(m_tkeep));

    reg [7:0]  inmem  [0:NIN-1];
    reg [7:0]  expout [0:NOUT-1];
    reg [31:0] rxw    [0:NWO-1];
    reg [8*200-1:0] f_in, f_out;
    integer errors, stall, wi, rn, ndone, bad, inject, cyc_done, cc = 0, c_start, c_last;
    reg feed_en = 0, acc = 0, watch_quiet = 0;
    reg pv = 0, pr = 0; reg [31:0] pd = 0; reg pl = 0;          // previous m_axis beat, for the hold rule
    integer seed = 4242;
    integer i, j, p, tmo;

    function [31:0] word(input integer k);
        word = {inmem[4*k+3], inmem[4*k+2], inmem[4*k+1], inmem[4*k]};
    endfunction

    // ---- DMA model, driven on the falling edge
    always @(negedge aclk) begin
        if (feed_en && wi < NWI) begin
            if (s_tvalid && !acc) begin
                // beat offered but not accepted at the last rising edge: hold everything (AXI rule)
            end else begin
                s_tdata  <= word(wi);
                s_tlast  <= ((wi == NWI - 1) && !(inject & 2)) || ((wi == 5) && (inject & 1));
                s_tvalid <= (stall && ($random(seed) & 3) == 0) ? 1'b0 : 1'b1;
            end
        end else s_tvalid <= 1'b0;
        m_tready <= (stall && ($random(seed) & 3) == 0) ? 1'b0 : 1'b1;
    end

    // ---- monitors at the rising edge
    always @(posedge aclk) begin
        cc <= cc + 1;
        acc <= s_tvalid && s_tready;
        if (s_tvalid && s_tready && wi == NWI - 1) c_last <= cc;
        if (s_tvalid && s_tready) wi <= wi + 1;
        if (m_tvalid && m_tready) begin
            if (rn < NWO) rxw[rn] <= m_tdata;
            if (m_tlast != (rn == NWO - 1)) bad <= bad + 1;
            rn <= rn + 1;
        end
        if (done) begin ndone <= ndone + 1; if (rn != NWO) bad <= bad + 1; end
        // hold rule: a beat that was valid and not accepted must be presented unchanged
        if (pv && !pr && !(m_tvalid && m_tdata === pd && m_tlast === pl)) bad <= bad + 1;
        pv <= m_tvalid; pr <= m_tready; pd <= m_tdata; pl <= m_tlast;
        if (m_tvalid && m_tkeep !== 4'hF) bad <= bad + 1;
        // nothing may move outside a tile
        if ((s_tready || m_tvalid) && !busy) bad <= bad + 1;
        if (watch_quiet && (busy || s_tready || m_tvalid || done)) bad <= bad + 1000;
        if (aresetn && !soft_rst && ((^{busy, done, s_tready, m_tvalid, m_tlast, cycles, err}) === 1'bx)) bad <= bad + 1;
    end

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

    task pulse_start;
        begin @(negedge aclk); start = 1; c_start = cc; @(negedge aclk); start = 0; end
    endtask

    // one complete tile.  inj: bit0 early TLAST on input word 5, bit1 drop TLAST on the last input word.  exp_err: expected error_flags.
    // dbl: give a second `start` while the tile runs.
    task run_tile(input integer inj, input integer exp_err, input integer dbl);
        begin
            wi = 0; rn = 0; ndone = 0; bad = 0; inject = inj;
            feed_en = 1;                                  // the DMA is armed BEFORE start: data must wait
            repeat (6) @(negedge aclk);
            if (wi != 0) begin errors = errors + 1; $display("  input accepted before start"); end
            pulse_start;
            dbl_run = dbl;
            if (dbl) begin repeat (40) @(negedge aclk); pulse_start; end
            tmo = 0;
            while (ndone == 0 && tmo < 4000000) begin @(posedge aclk); tmo = tmo + 1; end
            cyc_done = cycles;
            feed_en = 0;
            repeat (6) @(negedge aclk);
            if (tmo >= 4000000) begin errors = errors + 1; $display("FAIL: timeout (words in %0d/%0d, out %0d/%0d)", wi, NWI, rn, NWO); end
            check_all(exp_err);
        end
    endtask

    task check_all(input integer exp_err);
        reg [31:0] e;
        begin
            if (wi != NWI) begin errors = errors + 1; $display("  input words accepted %0d, expected %0d", wi, NWI); end
            // full speed on the input side: one byte per cycle into the core (4 cycles per word, no bubble), start-up a few cycles
            if (!stall && !dbl_run && c_last - c_start > NIN + 6) begin errors = errors + 1; $display("  input too slow: %0d cycles for %0d bytes", c_last - c_start, NIN); end
            if (rn != NWO) begin errors = errors + 1; $display("  output words %0d, expected %0d", rn, NWO); end
            if (ndone != 1) begin errors = errors + 1; $display("  done pulses: %0d (expected 1)", ndone); end
            if (bad != 0)   begin errors = errors + 1; $display("  stream protocol violations: %0d (TLAST position / hold rule / activity outside a tile / X)", bad); end
            if (busy)       begin errors = errors + 1; $display("  busy still high after done"); end
            if (err !== exp_err[2:0]) begin errors = errors + 1; $display("  error_flags %b, expected %b", err, exp_err[2:0]); end
            for (p = 0; p < NWO; p = p + 1) begin
                e = {expout[4*p+3], expout[4*p+2], expout[4*p+1], expout[4*p]};
                if (rxw[p] !== e) begin errors = errors + 1; if (errors < 6) $display("  output word %0d: got %08x exp %08x", p, rxw[p], e); end
            end
        end
    endtask

    reg dbl_run = 0;
    integer sweep_n, n_sweep, abort_at, step_len, t_total, mode_extra;
    reg [8*64-1:0] tile, tile2;
    initial begin
        errors = 0; inject = 0;
        if (!$value$plusargs("STALL=%d", stall)) stall = 0;
        if (!$value$plusargs("TILE=%s", tile)) tile = "small12";
        if (!$value$plusargs("TILE2=%s", tile2)) tile2 = "";
        mode_extra = (((HC <= 8) && !$test$plusargs("NOEXTRA")) || $test$plusargs("REPEAT"));
        repeat (4) @(negedge aclk); aresetn = 1; repeat (2) @(negedge aclk);
        load_tile(tile);
        run_tile(0, 0, 0);
        t_total = cyc_done;
        if (errors == 0 && mode_extra) begin
            // 1) same tile again, no reset, other stall pattern
            seed = seed + 777; run_tile(0, 0, 0);
            if (cyc_done != t_total && !stall) begin errors = errors + 1; $display("  cycle count changed: %0d vs %0d", t_total, cyc_done); end
            // 2) another tile (stale data must not leak)
            if (tile2 != "") begin load_tile(tile2); run_tile(0, 0, 0); load_tile(tile); end
            // 3) error injection: flags set, data still exact, then cleared by the next start
            run_tile(1, 3'b001, 0);
            run_tile(2, 3'b010, 0);
            run_tile(3, 3'b011, 0);
            run_tile(0, 3'b000, 0);
            // 4) start while busy: flag 100, output unharmed
            run_tile(0, 3'b100, 1);
            // 5) abort sweep (one-cycle reset, alternating aresetn / soft_rst), wrapper must stay quiet
            if (!$value$plusargs("SWEEP=%d", n_sweep)) n_sweep = (HC <= 8) ? 40 : 12;
            step_len = t_total / n_sweep;
            for (sweep_n = 0; sweep_n < n_sweep; sweep_n = sweep_n + 1) begin
                abort_at = 5 + sweep_n * step_len + (sweep_n * 7) % 13;
                wi = 0; rn = 0; ndone = 0; bad = 0; inject = 0; feed_en = 1;
                pulse_start;
                repeat (abort_at) @(negedge aclk);
                if (sweep_n % 2) soft_rst = 1; else aresetn = 0;
                @(negedge aclk);
                soft_rst = 0; aresetn = 1; feed_en = 0;
                watch_quiet = 1;
                repeat (300) @(negedge aclk);
                watch_quiet = 0;
                if (bad >= 1000) begin errors = errors + 1; $display("  wrapper not quiet after abort at cycle %0d", abort_at); end
            end
            // 6) fresh tile after all the aborts
            run_tile(0, 0, 0);
        end
        if (errors == 0)
            $display("PASS sr_axis_wrapper HC=%0d tile %0s: %0d output words bit-exact, %0d cycles%0s%0s",
                     HC, tile, NWO, t_total, stall ? ", random stalls" : "", mode_extra ? ", re-run + error flags + start-while-busy + abort sweep OK" : "");
        else
            $display("FAIL sr_axis_wrapper HC=%0d tile %0s: %0d errors", HC, tile, errors);
        $finish;
    end
endmodule
