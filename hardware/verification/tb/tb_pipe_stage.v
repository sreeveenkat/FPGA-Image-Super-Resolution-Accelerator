// Self-checking testbench of ONE pipeline stage (hardware/rtl/pipe/pipe_stage.v) against Python-generated vectors (gen_pipe_vectors.py).
//   LAYER 1..4 selects the shape: 1 conv3x3 3->16 (MODE 0), 2 depthwise3x3 16 (MODE 1), 3 conv1x1 16->16 (MODE 0), 4 conv3x3 16->12 + anchor (MODE 2).
//   REAL = 0: random weights / distinct M per channel (data/golden/pipe/rand/randL<n>_*), REAL = 1: the network weights (hardware/rtl/weights/wpipe_L<n>.mem),
//            input = the previous layer's golden output of frame +FRAME=<name> (L1: the padded input pixels), expected = this layer's golden output.
//   Plusargs: +STALL=1 random input gaps and a random consumer (reservations, 8 places), +SWEEP=<n> n one-cycle-reset aborts, each followed by a quiet check
//             and an exact run, +FRAME=<name> (REAL=1).
// Checks: every output word in order and bit-exact, the number of outputs and px_start pulses, out_valid only with a reservation, nothing after the frame,
//         an immediate re-run, cycles per output pixel (= 16 without stalls; printed).
`timescale 1ns/1ps
module tb_pipe_stage;
    parameter LAYER = 1;
    parameter REAL  = 0;
    `include "hardware/rtl/weights/network_params.vh"
    localparam C_IN   = (LAYER == 1) ? 3 : 16;
    localparam C_OUT  = (LAYER == 4) ? 12 : 16;
    localparam K      = (LAYER == 3) ? 1 : 3;
    localparam MODE   = (LAYER == 2) ? 1 : (LAYER == 4) ? 2 : 0;
    localparam ANCH   = (LAYER == 4) ? (REAL ? NET_ANCHOR : 1) : 0;
    localparam RSHIFT = (LAYER == 1) ? L1_SHIFT : (LAYER == 2) ? L2_SHIFT : (LAYER == 3) ? L3_SHIFT : L4_SHIFT;
    localparam [7:0] LC = "0" + LAYER;
    localparam RD = "data/golden/pipe/rand/randL";
    localparam WF = REAL ? {"hardware/rtl/weights/wpipe_L", LC, ".mem"} : {RD, LC, "_wpipe.mem"};
    localparam BF = REAL ? {"hardware/rtl/weights/bias_L", LC, ".mem"}  : {RD, LC, "_bias.mem"};
    localparam MF = REAL ? {"hardware/rtl/weights/mult_L", LC, ".mem"}  : {RD, LC, "_mult.mem"};
    localparam SH = REAL ? RSHIFT : 20;
    localparam MAXN = 1100000;

    reg clk = 0, rst = 1, start = 0;
    always #4 clk = ~clk;
    reg  [15:0] in_w, in_h;
    reg         in_valid = 0;
    reg  [8*C_IN-1:0] in_data;
    wire        in_ready, px_start, out_valid, anc_pop;
    wire        out_ok;
    wire [8*C_OUT-1:0] out_data;
    reg  [23:0] anc_data;

    pipe_stage #(.C_IN(C_IN), .C_OUT(C_OUT), .K(K), .MODE(MODE), .SHIFT(SH), .ANCHOR(ANCH), .MAXW(1024),
                 .W_FILE(WF), .B_FILE(BF), .M_FILE(MF)) dut (
        .clk(clk), .rst(rst), .start(start), .in_w(in_w), .in_h(in_h), .in_valid(in_valid), .in_data(in_data), .in_ready(in_ready),
        .out_ok(out_ok), .px_start(px_start), .out_valid(out_valid), .out_data(out_data), .anc_pop(anc_pop), .anc_data(anc_data));

    reg [8*C_IN-1:0]  in_mem  [0:MAXN-1];
    reg [8*C_OUT-1:0] exp_mem [0:MAXN-1];
    reg [23:0]        anc_mem [0:MAXN-1];
    integer n_in, n_out, fail = 0, stall = 0, sweep = 0, i, seed = 7, fd, r;
    string frame, fn, pfx, what, extra;

    // consumer model: reservations (px_start) and occupancy; out_ok = fewer than 8 reserved
    integer res = 0, occ = 0, oi = 0, nstart = 0, ai = 0, r2, o2;
    reg     consume, armed = 0;
    assign out_ok = (res < 8);
    // state is updated with non-blocking assignments: out_ok changes after the edge, never during it (no race with the DUT)
    always @(posedge clk) begin
        r2 = res; o2 = occ;
        consume = (o2 > 0) && (!stall || ($random(seed) & 3) != 0);
        if (rst) begin r2 = 0; o2 = 0; end
        else begin
            if (px_start) begin r2 = r2 + 1; nstart = nstart + 1; if (!armed) begin $display("FAIL px_start outside a frame"); fail = fail + 1; end end
            if (out_valid) begin
                if (!armed) begin $display("FAIL out_valid outside a frame"); fail = fail + 1; end
                else if (o2 >= r2) begin $display("FAIL out_valid without a reservation"); fail = fail + 1; end
                else if (oi >= n_out) begin $display("FAIL extra output %0d", oi); fail = fail + 1; end
                else if (out_data !== exp_mem[oi]) begin
                    if (fail < 10) $display("FAIL output %0d (x %0d, y %0d): got %h expected %h", oi, oi % (in_w - K + 1), oi / (in_w - K + 1), out_data, exp_mem[oi]);
                    fail = fail + 1;
                end
                oi = oi + 1; o2 = o2 + 1;
            end
            if (consume) begin o2 = o2 - 1; r2 = r2 - 1; end
        end
        res <= r2; occ <= o2;
    end
    // anchor FIFO model: data from the cycle after a pop
    always @(posedge clk) if (anc_pop) begin anc_data <= anc_mem[ai]; ai <= ai + 1; end

    // input driver
    integer ii = 0;
    always @(negedge clk) begin
        if (in_valid && in_ready_q) ii = ii + 1;
        in_valid <= armed && (ii < n_in) && (!stall || ($random(seed) % 3) != 0);
        in_data  <= in_mem[(ii < n_in) ? ii : 0];
    end
    reg in_ready_q;
    always @(posedge clk) in_ready_q <= in_ready;          // sampled at the rising edge the transfer happens on

    task run_frame(input integer abort_at, output integer cyc);
        integer t;
        begin
            ii = 0; oi = 0; ai = 0; nstart = 0; cyc = 0;
            @(negedge clk) start = 1; armed = 1; @(negedge clk) start = 0;
            t = 0;
            while (oi < n_out && t < 40 * n_in + 4000 && !(abort_at > 0 && t == abort_at)) begin @(negedge clk); t = t + 1; end
            cyc = t;
            if (abort_at > 0 && t == abort_at) begin
                @(negedge clk) rst = 1; @(negedge clk) rst = 0; armed = 0; in_valid = 0;
                // quiet check: no activity without a start
                repeat (200) begin @(negedge clk); if (px_start || out_valid || anc_pop) begin $display("FAIL activity after reset"); fail = fail + 1; end end
            end else begin
                if (oi != n_out) begin $display("FAIL only %0d of %0d outputs (timeout)", oi, n_out); fail = fail + 1; end
                repeat (60) @(negedge clk);
                if (oi != n_out || nstart != n_out) begin $display("FAIL %0d outputs, %0d px_start, expected %0d", oi, nstart, n_out); fail = fail + 1; end
                if (ANCH && ai != n_out) begin $display("FAIL %0d anchor pops, expected %0d", ai, n_out); fail = fail + 1; end
                armed = 0;
            end
        end
    endtask

    integer cyc1, cyc2, dummy, k2;
    initial begin
        if (!$value$plusargs("STALL=%d", stall)) stall = 0;
        if (!$value$plusargs("SWEEP=%d", sweep)) sweep = 0;
        if (REAL) begin
            if (!$value$plusargs("FRAME=%s", frame)) begin $display("FAIL REAL=1 needs +FRAME=<name>"); $finish; end
            pfx = {"data/golden/pipe/", frame};
            fn = {pfx, "_meta.txt"};
            fd = $fopen(fn, "r"); if (fd == 0) begin $display("FAIL missing %0s", fn); $finish; end
            r = $fscanf(fd, "%d %d", in_w, in_h); $fclose(fd);
            // stage input size: L1 = padded frame, L2 = L1 output, L3/L4 = L2 output
            in_w = (LAYER == 1) ? in_w + 6 : (LAYER == 2) ? in_w + 4 : in_w + 2;
            in_h = (LAYER == 1) ? in_h + 6 : (LAYER == 2) ? in_h + 4 : in_h + 2;
        end else begin
            fd = $fopen({RD, LC, "_meta.txt"}, "r"); if (fd == 0) begin $display("FAIL missing rand meta"); $finish; end
            r = $fscanf(fd, "%d %d", in_w, in_h); $fclose(fd);
        end
        n_in  = in_w * in_h;
        n_out = (in_w - K + 1) * (in_h - K + 1);
        for (i = 0; i < n_in; i = i + 1) in_mem[i] = {8*C_IN{1'bx}};
        for (i = 0; i < n_out; i = i + 1) exp_mem[i] = {8*C_OUT{1'bx}};
        if (REAL) begin
            if (LAYER == 1) begin
                // L1 input = the padded frame pixels, rebuilt from the 32-bit input beats
                load_padded({pfx, "_in.hex"});
            end else begin
                fn = $sformatf("%s_L%0d.hex", pfx, LAYER - 1);
                $readmemh(fn, in_mem, 0, n_in - 1);
            end
            fn = $sformatf("%s_L%0d.hex", pfx, LAYER);
            $readmemh(fn, exp_mem, 0, n_out - 1);
            if (ANCH) begin fn = {pfx, "_anc.hex"}; $readmemh(fn, anc_mem, 0, n_out - 1); end
        end else begin
            $readmemh({RD, LC, "_in.hex"}, in_mem, 0, n_in - 1);
            $readmemh({RD, LC, "_out.hex"}, exp_mem, 0, n_out - 1);
            if (ANCH) $readmemh({RD, LC, "_anc.hex"}, anc_mem, 0, n_out - 1);
        end
        if (^in_mem[n_in - 1] === 1'bx || ^exp_mem[n_out - 1] === 1'bx) begin $display("FAIL vector files missing or short"); $finish; end
        if (REAL && SH != RSHIFT) begin $display("FAIL SHIFT mismatch"); $finish; end
        repeat (3) @(negedge clk); rst = 0; repeat (2) @(negedge clk);
        run_frame(0, cyc1);
        run_frame(0, cyc2);                                   // immediate re-run
        for (k2 = 0; k2 < sweep; k2 = k2 + 1) begin
            run_frame(1 + (k2 * 37 + 5) % (16 * n_out), dummy); // abort at a spread of points
            run_frame(0, dummy);
        end
        if (REAL) what = {"frame ", frame}; else what = "random weights";
        extra = "";
        if (stall) extra = ", random stalls";
        if (sweep) extra = $sformatf("%s, %0d reset aborts + quiet checks", extra, sweep);
        if (fail == 0)
            $display("PASS pipe_stage L%0d %s: %0dx%0d -> %0d outputs x %0d ch bit-exact, %0d cycles (%0d.%02d per output)%s, re-run OK",
                     LAYER, what, in_w, in_h, n_out, C_OUT, cyc1, cyc1 / n_out, (cyc1 * 100 / n_out) % 100, extra);
        else $display("FAIL pipe_stage L%0d: %0d errors", LAYER, fail);
        $finish;
    end

    task load_padded(input string f);
        reg [31:0] bw [0:MAXN-1];
        integer nb, j, byte_i;
        reg [7:0] bytes3 [0:2];
        begin
            nb = (3 * n_in + 3) / 4;
            $readmemh(f, bw, 0, nb - 1);
            for (j = 0; j < n_in; j = j + 1) begin
                for (byte_i = 0; byte_i < 3; byte_i = byte_i + 1)
                    bytes3[byte_i] = bw[(3 * j + byte_i) / 4][8 * ((3 * j + byte_i) % 4) +: 8];
                in_mem[j] = {bytes3[2], bytes3[1], bytes3[0]};
            end
        end
    endtask
endmodule
