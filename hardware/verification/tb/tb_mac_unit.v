// mac_unit.v: random and extreme sequences against an independent 64-bit behavioural model written in the testbench.
`timescale 1ns/1ps
module tb_mac_unit;
    reg clk = 0;
    always #5 clk = ~clk;
    reg v = 0, first = 0;
    reg signed [31:0] bias = 0;
    reg [7:0] a = 0;
    reg signed [7:0] w = 0;
    wire signed [31:0] acc;
    mac_unit dut (.clk(clk), .v(v), .first(first), .bias(bias), .a(a), .w(w), .acc(acc));

    integer errors = 0, seqs = 0, i, j, len;
    reg signed [63:0] model;
    reg signed [31:0] b;

    task run_sequence(input integer n, input integer mode);  // mode 0 random, 1 all max positive, 2 all max negative, 3 mixed extremes
        begin
            b = (mode == 0) ? $random : (mode == 1) ? 32'sd1000 : (mode == 2) ? -32'sd1000 : 32'sd0;
            model = b;
            for (j = 0; j < n; j = j + 1) begin
                @(negedge clk);
                v = 1; first = (j == 0); bias = b;
                case (mode)
                    0: begin a = $random; w = $random; end
                    1: begin a = 8'd255; w = 8'sd127; end
                    2: begin a = 8'd255; w = -8'sd128; end
                    default: begin a = (j % 2) ? 8'd255 : 8'd0; w = (j % 3 == 0) ? -8'sd128 : 8'sd127; end
                endcase
                if (j != 0 || 1) model = ((j == 0) ? b : model) + $signed({1'b0, a}) * w;
            end
            @(negedge clk); v = 0; a = 8'hA5; w = 8'sd77;  // garbage while invalid: must not change acc
            repeat (4) @(negedge clk);
            seqs = seqs + 1;
            if (acc !== model[31:0] || model !== $signed(acc)) begin
                errors = errors + 1;
                $display("  sequence %0d (mode %0d, %0d steps): acc=%0d expected %0d", seqs, mode, n, acc, model);
            end
        end
    endtask

    initial begin
        repeat (3) @(negedge clk);
        for (i = 0; i < 300; i = i + 1) run_sequence(1 + ($random & 63), 0);   // up to 64 random steps
        run_sequence(144, 1);  // the longest real layer (L4: 144 steps) at the largest positive product
        run_sequence(144, 2);  // and at the most negative product: -144*255*128 = -4.7 M, far from int32 overflow
        run_sequence(144, 3);
        run_sequence(1, 1);
        // back-to-back pixels with no gap: the second 'first' must discard the first pixel's sum
        @(negedge clk); v = 1; first = 1; bias = 32'sd5; a = 8'd10; w = 8'sd3;
        @(negedge clk); first = 0; a = 8'd20; w = -8'sd2;
        @(negedge clk); first = 1; bias = -32'sd7; a = 8'd4; w = 8'sd4;
        @(negedge clk); v = 0;
        repeat (4) @(negedge clk);
        if (acc !== 32'sd9) begin errors = errors + 1; $display("  back-to-back: acc=%0d expected 9", acc); end
        if (errors == 0) $display("PASS mac_unit: %0d sequences + back-to-back bit-exact", seqs);
        else             $display("FAIL mac_unit: %0d errors", errors);
        $finish;
    end
endmodule
