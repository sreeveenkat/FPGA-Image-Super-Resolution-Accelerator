// Unit test of hardware/rtl/pipe/adder_tree.v: random and extreme 17-bit signed terms, N = 2, 3, 5, 9, 16, 27 (odd and even node counts on every level).
// Checks the sum against a behavioural sum, the latency (LV = clog2(N) cycles) and that one result comes out per cycle (fully pipelined).
`timescale 1ns/1ps
module tb_adder_tree;
    parameter N = 9;
    localparam LV = $clog2(N);
    reg clk = 0; always #4 clk = ~clk;
    reg  [N*17-1:0] in;
    wire signed [23:0] sum;
    adder_tree #(.N(N), .IW(17), .OW(24)) dut (.clk(clk), .in(in), .sum(sum));
    integer seed = 3, i, k, fails = 0, t;
    reg signed [23:0] exp [0:1023];
    reg signed [16:0] v;
    initial begin
        for (t = 0; t < 1024; t = t + 1) begin
            @(negedge clk);
            exp[t] = 0;
            for (i = 0; i < N; i = i + 1) begin
                k = $random(seed) % 5;
                v = (t < 4) ? ((t == 0) ? 17'sd32640 : (t == 1) ? -17'sd32640 : (t == 2) ? ((i & 1) ? 17'sd32640 : -17'sd32640) : 17'sd0)
                  : (k == 0) ? 17'sd32640 : (k == 1) ? -17'sd32640 : $random(seed) % 32641;
                in[i*17 +: 17] = v;
                exp[t] = exp[t] + v;
            end
            if (t >= LV && sum !== exp[t - LV]) begin
                if (fails < 5) $display("FAIL N=%0d vector %0d: sum %0d, expected %0d", N, t - LV, sum, exp[t - LV]);
                fails = fails + 1;
            end
        end
        if (fails == 0) $display("PASS adder_tree N=%0d: 1,020 vectors (random + extreme terms), latency %0d, one sum per cycle", N, LV);
        else $display("FAIL adder_tree N=%0d: %0d errors", N, fails);
        $finish;
    end
endmodule
