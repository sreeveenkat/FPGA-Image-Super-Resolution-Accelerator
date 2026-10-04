// Self-checking testbench for sr_tile_core (M5).  Run from the project root.
//   iverilog -g2012 -I . -P tb_sr_tile.HC=6 ... ; vvp ... +TILE=small12 [+STALL=1] [+TILE2=other] [+REPEAT] [+DUMP=file] [+IN=f +OUT=f +MID=prefix]
// Inputs : +TILE=<name> -> data/golden/<name>_in.hex (tile with halo, bytes [y][x][c]), expected stream data/golden/<name>_out.hex and the
//          intermediate buffers data/golden/<name>_L1..L4.hex.  Or explicit +IN=<hex> [+OUT=<hex>] [+MID=<prefix>] (no files = no check).
// Checks : every layer buffer inside the core (ram1..ram4) bit-exact, the output byte stream bit-exact AND complete (count, out_last),
//          no output before the data is ready, in_ready only in the load phase, and with +REPEAT (always for HC <= 8):
//          * a second tile (+TILE2, different data) right after the first, no reset, must also be exact,
//          * a sweep of ONE-cycle-reset aborts at many different moments (load, each layer, output); afterwards the core must stay quiet,
//          * a final fresh tile must be exact.
// +STALL=1 inserts random gaps on both streams (valid and ready).  +DUMP=<file> writes the received bytes as hex (seam test).
`timescale 1ns/1ps
module tb_sr_tile;
    parameter HC = 6;
    localparam IW1 = HC + 6, IW2 = HC + 4, IW3 = HC + 2, IW4 = HC + 2;
    localparam NIN = IW1 * IW1 * 3;                  // input bytes
    localparam NOUT = (2 * HC) * (2 * HC) * 3;       // output bytes
    `include "hardware/rtl/weights/network_params.vh"

    reg clk = 0, rst = 1, start = 0;
    always #5 clk = ~clk;
    reg in_valid = 0; reg [7:0] in_data = 0; reg out_ready = 0;
    wire busy, done, in_ready, out_valid, out_last; wire [7:0] out_data; wire [31:0] cycles;

`ifdef POSTSYNTH
    sr_tile_core dut (    // post-synthesis netlist: parameters are baked in, internals are not reachable (only the stream interface is checked)
`else
    sr_tile_core #(.HC(HC), .SHIFT1(L1_SHIFT), .SHIFT2(L2_SHIFT), .SHIFT3(L3_SHIFT), .SHIFT4(L4_SHIFT)) dut (
`endif
        .clk(clk), .rst(rst), .start(start), .busy(busy), .done(done),
        .in_valid(in_valid), .in_data(in_data), .in_ready(in_ready),
        .out_valid(out_valid), .out_data(out_data), .out_ready(out_ready), .out_last(out_last), .cycles(cycles));

    // The core's DEFAULT SHIFT parameters must equal the exported ones (a wrapper that instantiates the core without overrides relies on them).
    // This idle second instance exists only to read its parameters.
`ifndef POSTSYNTH
    sr_tile_core #(.HC(HC)) dflt_check (.clk(clk), .rst(1'b1), .start(1'b0), .in_valid(1'b0), .in_data(8'd0), .out_ready(1'b0),
                                        .busy(), .done(), .in_ready(), .out_valid(), .out_data(), .out_last(), .cycles());
    initial begin
        #1;
        if (dflt_check.SHIFT1 !== L1_SHIFT || dflt_check.SHIFT2 !== L2_SHIFT || dflt_check.SHIFT3 !== L3_SHIFT || dflt_check.SHIFT4 !== L4_SHIFT) begin
            $display("FAIL sr_tile_core: default SHIFT parameters (%0d %0d %0d %0d) differ from network_params.vh (%0d %0d %0d %0d)",
                     dflt_check.SHIFT1, dflt_check.SHIFT2, dflt_check.SHIFT3, dflt_check.SHIFT4, L1_SHIFT, L2_SHIFT, L3_SHIFT, L4_SHIFT);
            $finish;
        end
    end
`endif

    // ---- data
    reg [7:0] inmem  [0:NIN-1];
    reg [7:0] expout [0:NOUT-1];
    reg [7:0] rx     [0:NOUT-1];
    reg [7:0] m1 [0:(IW2*IW2*16)-1];
    reg [7:0] m2 [0:(IW3*IW3*16)-1];
    reg [7:0] m3 [0:(IW4*IW4*16)-1];
    reg [7:0] m4 [0:(HC*HC*12)-1];
    reg [8*200-1:0] f_in, f_out, f_mid, f_dump, f_name, f_tmp;
    reg have_out, have_mid;
    integer errors, stall, fi, rxn, last_seen, bad_ready, bad_out, cyc_at_done;
    reg feed_en = 0, watch_quiet = 0;
    integer seed = 12345;
    integer i, j, p, c;

    // ---- stimulus (driven on the falling edge: no race with the DUT)
    always @(negedge clk) begin
        if (feed_en && fi < NIN) begin
            in_data <= inmem[fi];
            in_valid <= (stall && ($random(seed) & 3) == 0) ? 1'b0 : 1'b1;
        end else in_valid <= 1'b0;
        out_ready <= (stall && ($random(seed) & 3) == 0) ? 1'b0 : 1'b1;
    end
    // ---- monitors (sample at the rising edge, before the DUT updates)
    always @(posedge clk) begin
        if (in_valid && in_ready) fi <= fi + 1;
`ifndef POSTSYNTH
        if (in_ready && !(dut.state == 3'd1)) bad_ready <= bad_ready + 1;
`endif
        if (out_valid && out_ready) begin
            if (rxn < NOUT) rx[rxn] <= out_data;
            if (out_last != (rxn == NOUT - 1)) bad_out <= bad_out + 1;
            rxn <= rxn + 1;
        end
`ifndef POSTSYNTH
        if (out_valid && !(dut.state == 3'd6)) bad_out <= bad_out + 1;
`endif
        if (watch_quiet && (busy || in_ready || out_valid || done)) bad_out <= bad_out + 1000;
        // control/status outputs must never be X (or out_last high without out_valid) once the first reset is over
        if (!rst && ((^{busy, done, in_ready, out_valid, out_last, cycles}) === 1'bx || (out_last && !out_valid))) bad_out <= bad_out + 1;
    end

    task load_tile(input [8*64-1:0] name);
        begin
            if (name != "") begin
                $sformat(f_in,  "data/golden/%0s_in.hex",  name);
                $sformat(f_out, "data/golden/%0s_out.hex", name);
                $sformat(f_mid, "data/golden/%0s", name);
                have_out = 1; have_mid = 1;
            end
            for (i = 0; i < NIN; i = i + 1) inmem[i] = 8'hxx;
            $readmemh(f_in, inmem);
            j = 0; for (i = 0; i < NIN; i = i + 1) if (^inmem[i] === 1'bx) j = j + 1;
            if (j != 0) begin $display("FAIL: %0d undefined bytes in %0s (missing or short?)", j, f_in); $finish; end
            if (have_out) begin
                for (i = 0; i < NOUT; i = i + 1) expout[i] = 8'hxx;
                $readmemh(f_out, expout);
                j = 0; for (i = 0; i < NOUT; i = i + 1) if (^expout[i] === 1'bx) j = j + 1;
                if (j != 0) begin $display("FAIL: %0d undefined bytes in %0s", j, f_out); $finish; end
            end
            if (have_mid) begin
                $sformat(f_tmp, "%0s_L1.hex", f_mid); $readmemh(f_tmp, m1);
                $sformat(f_tmp, "%0s_L2.hex", f_mid); $readmemh(f_tmp, m2);
                $sformat(f_tmp, "%0s_L3.hex", f_mid); $readmemh(f_tmp, m3);
                $sformat(f_tmp, "%0s_L4.hex", f_mid); $readmemh(f_tmp, m4);
            end
        end
    endtask

    task pulse_start;
        begin @(negedge clk); start = 1; @(negedge clk); start = 0; end
    endtask

    // run one complete tile; sets errors
    integer tmo;
    task run_tile(input integer check);
        begin
            fi = 0; rxn = 0; bad_ready = 0; bad_out = 0;
            poison;
            feed_en = 1;
            pulse_start;
            tmo = 0;
            while (!done && tmo < 4000000) begin @(posedge clk); tmo = tmo + 1; end
            cyc_at_done = cycles;
            feed_en = 0;
            repeat (4) @(negedge clk);
            if (!done && tmo >= 4000000) begin $display("FAIL: timeout"); errors = errors + 1; end
            if (check) check_all;
        end
    endtask

    task check_all;
        reg [127:0] w; reg [95:0] w4;
        begin
            if (rxn != NOUT) begin errors = errors + 1; $display("  output byte count %0d, expected %0d", rxn, NOUT); end
            if (bad_ready != 0) begin errors = errors + 1; $display("  in_ready high outside the load phase (%0d cycles)", bad_ready); end
            if (bad_out != 0)   begin errors = errors + 1; $display("  output protocol violations: %0d (out_last position / output before ready)", bad_out); end
            if (busy) begin errors = errors + 1; $display("  busy still high after done"); end
`ifndef POSTSYNTH
            if (have_mid) begin
                for (p = 0; p < IW2*IW2; p = p + 1) begin w = dut.ram1.peek(p); for (c = 0; c < 16; c = c + 1) if (w[8*c +: 8] !== m1[p*16+c]) begin errors = errors + 1; if (errors < 6) $display("  L1 buffer pixel %0d ch %0d: got %0d exp %0d", p, c, w[8*c +: 8], m1[p*16+c]); end end
                for (p = 0; p < IW3*IW3; p = p + 1) begin w = dut.ram2.peek(p); for (c = 0; c < 16; c = c + 1) if (w[8*c +: 8] !== m2[p*16+c]) begin errors = errors + 1; if (errors < 6) $display("  L2 buffer pixel %0d ch %0d: got %0d exp %0d", p, c, w[8*c +: 8], m2[p*16+c]); end end
                for (p = 0; p < IW4*IW4; p = p + 1) begin w = dut.ram3.peek(p); for (c = 0; c < 16; c = c + 1) if (w[8*c +: 8] !== m3[p*16+c]) begin errors = errors + 1; if (errors < 6) $display("  L3 buffer pixel %0d ch %0d: got %0d exp %0d", p, c, w[8*c +: 8], m3[p*16+c]); end end
                for (p = 0; p < HC*HC; p = p + 1) begin w4 = dut.ram4.peek(p); for (c = 0; c < 12; c = c + 1) if (w4[8*c +: 8] !== m4[p*12+c]) begin errors = errors + 1; if (errors < 6) $display("  L4 buffer pixel %0d ch %0d: got %0d exp %0d", p, c, w4[8*c +: 8], m4[p*12+c]); end end
            end
`endif
            if (have_out)
                for (p = 0; p < NOUT; p = p + 1)
                    if (rx[p] !== expout[p]) begin errors = errors + 1; if (errors < 6) $display("  output byte %0d (pixel %0d): got %0d exp %0d", p, p/3, rx[p], expout[p]); end
            if (f_dump != 0) begin
                // write the received bytes (one hex byte per line) for the seam test
                p = $fopen(f_dump, "w");
                for (c = 0; c < NOUT; c = c + 1) $fdisplay(p, "%02x", rx[c]);
                $fclose(p);
            end
        end
    endtask

    // poison the four layer buffers (ram1..ram4) with 0xA5 so that a missing write cannot hide behind old, correct data
    task poison;
        integer q;
        begin
`ifndef POSTSYNTH
            for (q = 0; q < dut.ram1.SPLIT; q = q + 1) dut.ram1.mem_lo[q] = {16{8'hA5}};
            for (q = 0; q < dut.ram1.HI_N;  q = q + 1) dut.ram1.mem_hi[q] = {16{8'hA5}};
            for (q = 0; q < dut.ram2.SPLIT; q = q + 1) dut.ram2.mem_lo[q] = {16{8'hA5}};
            for (q = 0; q < dut.ram2.HI_N;  q = q + 1) dut.ram2.mem_hi[q] = {16{8'hA5}};
            for (q = 0; q < dut.ram3.SPLIT; q = q + 1) dut.ram3.mem_lo[q] = {16{8'hA5}};
            for (q = 0; q < dut.ram3.HI_N;  q = q + 1) dut.ram3.mem_hi[q] = {16{8'hA5}};
            for (q = 0; q < dut.ram4.SPLIT; q = q + 1) dut.ram4.mem_lo[q] = {12{8'hA5}};
            for (q = 0; q < dut.ram4.HI_N;  q = q + 1) dut.ram4.mem_hi[q] = {12{8'hA5}};
`endif
        end
    endtask

    integer mode_extra, sweep_n, n_sweep, abort_at, step_len, t_total;
    reg [8*64-1:0] tile, tile2;
    initial begin
        errors = 0; f_dump = 0; have_out = 0; have_mid = 0;
        if (!$value$plusargs("STALL=%d", stall)) stall = 0;
        if ($value$plusargs("DUMP=%s", f_dump)) ;
        if ($value$plusargs("IN=%s", f_in)) begin
            tile = "";
            if ($value$plusargs("OUT=%s", f_out)) have_out = 1;
            if ($value$plusargs("MID=%s", f_mid)) have_mid = 1;
        end else begin
            if (!$value$plusargs("TILE=%s", tile)) tile = "small12";
        end
        if (!$value$plusargs("TILE2=%s", tile2)) tile2 = "";
        mode_extra = (((HC <= 8) && !$test$plusargs("NOEXTRA")) || $test$plusargs("REPEAT"));   // +NOEXTRA: single run only (seam test)
        // the shifts used here must be the exported ones
`ifdef POSTSYNTH
        wait (glbl.GSR === 1'b0);     // Xilinx global set/reset holds every flip-flop for the first 100 ns of a netlist simulation
`endif
        repeat (4) @(negedge clk); rst = 0; repeat (2) @(negedge clk);
        load_tile(tile);
        run_tile(1);
        t_total = cyc_at_done;
        if (errors == 0 && mode_extra) begin
            // 1) second run of the same tile right after the first (no reset), other stall pattern
            seed = seed + 777; run_tile(1);
            if (cyc_at_done != t_total && !stall) begin errors = errors + 1; $display("  cycle count changed between runs: %0d vs %0d", t_total, cyc_at_done); end
            // 2) a different tile after it (stale data in the buffers must not leak)
            if (tile2 != "") begin load_tile(tile2); run_tile(1); load_tile(tile); end
            // 3) abort sweep: one-cycle reset at many moments over the whole run, core must stay quiet afterwards
            if (!$value$plusargs("SWEEP=%d", n_sweep)) n_sweep = (HC <= 8) ? 60 : 24;
            step_len = t_total / n_sweep;
            for (sweep_n = 0; sweep_n < n_sweep; sweep_n = sweep_n + 1) begin
                abort_at = 5 + sweep_n * step_len + (sweep_n * 7) % 13;
                fi = 0; rxn = 0; bad_ready = 0; bad_out = 0; feed_en = 1;
                pulse_start;
                repeat (abort_at) @(negedge clk);
                rst = 1; @(negedge clk); rst = 0; feed_en = 0;
                watch_quiet = 1;
                repeat (300) @(negedge clk);
                watch_quiet = 0;
                if (bad_out >= 1000) begin errors = errors + 1; $display("  core not quiet after abort at cycle %0d", abort_at); end
            end
            // 4) fresh tile after all the aborts
            run_tile(1);
        end
        if (errors == 0)
`ifdef POSTSYNTH
            $display("PASS sr_tile_core HC=%0d tile %0s: %0d output bytes bit-exact (netlist: internal buffers not visible, not checked), %0d cycles%0s%0s",
`else
            $display("PASS sr_tile_core HC=%0d tile %0s: %0d output bytes bit-exact, layer buffers exact, %0d cycles%0s%0s",
`endif
                     HC, tile, NOUT, t_total, stall ? ", random stalls" : "", mode_extra ? ", re-run + 2nd tile + abort sweep OK" : "");
        else
            $display("FAIL sr_tile_core HC=%0d tile %0s: %0d errors", HC, tile, errors);
        $finish;
    end
endmodule
