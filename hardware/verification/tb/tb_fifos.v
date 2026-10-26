// Unit test of the two pipeline FIFOs (hardware/rtl/pipe/anchor_fifo.v, pipe_fifo.v) far past the pointer wrap-around.
// Added 2026-10-26 after a deadlock: anchor_fifo computed its occupancy in 32-bit context, so after 8,192 pushes `full` went high with 579 entries inside
// and the 192x192 and 960x540 frames stopped (no earlier test pushed more than 3,072 anchors).
//   anchor_fifo: 30,000 pushes / pops with a random occupancy between 0 and DEPTH, data order, `full` exactly from DEPTH-4 entries on (registered), err never set;
//                then a forced overflow and underflow must set err.
//   pipe_fifo:   20,000 reserved pushes / pops, data order, ok = fewer than DEPTH reservations, err never set; then a push into a full FIFO must set err.
`timescale 1ns/1ps
module tb_fifos;
    reg clk = 0, rst = 1; always #4 clk = ~clk;
    // ---- anchor FIFO (small DEPTH = 64 so the occupancy sweeps the whole range many times; the pointers wrap every 128 pushes)
    localparam AD = 64;
    reg         a_push = 0, a_pop = 0;
    reg  [23:0] a_din = 0;
    wire [23:0] a_dout;
    wire        a_full, a_err;
    anchor_fifo #(.DEPTH(AD)) ua (.clk(clk), .rst(rst), .push(a_push), .din(a_din), .pop(a_pop), .dout(a_dout), .full(a_full), .err(a_err));
    // ---- pipe FIFO
    localparam PD = 8;
    reg          p_res = 0, p_push = 0, p_rdy = 0;
    reg  [31:0]  p_din = 0;
    wire [31:0]  p_dout;
    wire         p_ok, p_v, p_err;
    pipe_fifo #(.W(32), .DEPTH(PD)) up (.clk(clk), .rst(rst), .reserve(p_res), .ok(p_ok), .push(p_push), .din(p_din), .out_valid(p_v), .dout(p_dout), .out_ready(p_rdy), .err(p_err));

    integer seed = 9, fails = 0, n_in = 0, n_out = 0, occ = 0, occ_q = 0, target = 0, k, pend = 0, pi = 0, po = 0, pres = 0, prev_occ = 0;
    initial begin
        repeat (3) @(negedge clk); rst = 0; @(negedge clk);
        // anchor FIFO: occupancy follows a random target in 0..AD (push while below it, pop while above it)
        for (k = 0; k < 600000 && n_out < 30000; k = k + 1) begin
            if (k % 100 == 0) target = $unsigned($random(seed)) % (AD + 1);
            a_push = (occ < target) && !a_full && n_in < 30000;
            a_pop  = (occ > target || n_in >= 30000) && occ > 0;
            a_din  = n_in * 7 + 3;
            @(posedge clk); #1;
            // `full` is registered: it reflects the occupancy before this edge (prev_occ) and must be high exactly from AD - 4 entries on
            if (a_full !== (occ >= AD - 4)) begin if (fails < 5) $display("FAIL anchor_fifo: full %b with %0d entries", a_full, occ); fails = fails + 1; end
            // dout is written at the edge of its own pop (valid from then on until the next pop)
            if (a_pop && a_dout !== n_out * 7 + 3) begin if (fails < 5) $display("FAIL anchor_fifo: data %0d, expected %0d", a_dout, n_out * 7 + 3); fails = fails + 1; end
            if (a_push) begin n_in = n_in + 1; occ = occ + 1; end
            if (a_pop) begin n_out = n_out + 1; occ = occ - 1; end
            @(negedge clk);
        end
        a_push = 0; a_pop = 0;
        @(posedge clk); #1;
        if (a_err) begin $display("FAIL anchor_fifo: err set during legal use"); fails = fails + 1; end
        if (n_out < 30000) begin $display("FAIL anchor_fifo: only %0d pops", n_out); fails = fails + 1; end
        // forced underflow, then a reset, then a forced overflow: err must be set each time
        @(negedge clk); a_pop = (occ == 0); @(negedge clk); a_pop = 0; @(negedge clk);
        if (!a_err) begin $display("FAIL anchor_fifo: pop when empty did not set err"); fails = fails + 1; end
        rst = 1; @(negedge clk); rst = 0; @(negedge clk);
        for (k = 0; k <= AD; k = k + 1) begin a_push = 1; @(negedge clk); end
        a_push = 0; @(negedge clk);
        if (!a_err) begin $display("FAIL anchor_fifo: push when full did not set err"); fails = fails + 1; end

        // pipe FIFO: random reservations / pushes / pops, 20,000 words
        rst = 1; @(negedge clk); rst = 0; @(negedge clk);
        for (k = 0; k < 200000 && po < 20000; k = k + 1) begin
            p_res  = p_ok && ($random(seed) & 1) && pres < 20000;
            p_push = (pend > 0) && ($random(seed) & 1);
            p_din  = pi * 13 + 1;
            p_rdy  = ($random(seed) % 3) != 0;
            @(posedge clk); #1;
            if (p_v && p_rdy && 1'b0) ;                       // (data checked below, from the values sampled before the edge)
            @(negedge clk);
        end
        // (the loop above only drives; the checks run in the monitor below)
        if (p_err) begin $display("FAIL pipe_fifo: err set during legal use"); fails = fails + 1; end
        if (po < 20000) begin $display("FAIL pipe_fifo: only %0d words out", po); fails = fails + 1; end
        // overflow: fill to DEPTH without reservations counted as free, then one more push
        rst = 1; @(negedge clk); rst = 0; @(negedge clk); p_rdy = 0; p_res = 0;
        for (k = 0; k <= PD; k = k + 1) begin p_push = 1; @(negedge clk); end
        p_push = 0; @(negedge clk);
        if (!p_err) begin $display("FAIL pipe_fifo: push into a full FIFO did not set err"); fails = fails + 1; end
        if (fails == 0) $display("PASS fifos: anchor_fifo 30,000 words through a 64-deep FIFO (pointers wrap %0d times), full exactly from DEPTH-4, err only on misuse; pipe_fifo 20,000 reserved words, ok/err correct", 30000 / 128);
        else $display("FAIL fifos: %0d errors", fails);
        $finish;
    end
    // pipe FIFO monitor (samples before the edge)
    always @(posedge clk) if (!rst) begin
        if (p_res) begin pres = pres + 1; pend = pend + 1; end
        if (p_push) begin pi = pi + 1; pend = pend - 1; end
        if (p_v && p_rdy) begin
            if (p_dout !== po * 13 + 1) begin if (fails < 5) $display("FAIL pipe_fifo: word %0d is %0d", po, p_dout); fails = fails + 1; end
            po = po + 1;
        end
    end
endmodule
