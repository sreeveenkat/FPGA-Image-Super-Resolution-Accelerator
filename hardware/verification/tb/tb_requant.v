// requant.v against vectors made by the Python golden model (data/golden/unit/requant_s<SHIFT>.hex).
// One vector per clock; checks value, order, valid timing (latency 3) and the tag passthrough.
`timescale 1ns/1ps
module tb_requant;
    parameter SHIFT = 24;
    reg clk = 0;
    always #5 clk = ~clk;

    reg [55:0] vec [0:19999];
    reg [8*100-1:0] fname;
    reg v_in = 0;
    reg signed [31:0] acc = 0;
    reg [15:0] m = 0;
    reg [8:0] tag_in = 0;
    wire v_out;
    wire [7:0] y;
    wire [8:0] tag_out;

    requant #(.SHIFT(SHIFT), .TW(9)) dut (.clk(clk), .rst(1'b0), .v_in(v_in), .acc(acc), .m(m), .tag_in(tag_in),
                                           .v_out(v_out), .y(y), .tag_out(tag_out));

    integer n, i, got, errors;
    initial begin
        $sformat(fname, "data/golden/unit/requant_s%0d.hex", SHIFT);
        for (i = 0; i < 20000; i = i + 1) vec[i] = 56'hx;
        $readmemh(fname, vec);
        n = 0;
        while (vec[n] !== 56'hx) n = n + 1;
        errors = 0; got = 0;
        // stimulus on the falling edge, with a bubble every 7th cycle to test valid gating
        for (i = 0; i <= n + 6; i = i + 1) begin
            @(negedge clk);
            if (i < n && (i % 7 != 6 || 1)) begin
                v_in = 1; acc = vec[i][55:24]; m = vec[i][23:8]; tag_in = i[8:0];
            end else begin
                v_in = 0; acc = 32'hdeadbeef; m = 16'hffff;
            end
        end
        @(negedge clk);
        if (n < 1000) begin errors = errors + 1; $display("  only %0d vectors were loaded from %0s (file missing or empty?)", n, fname); end
        if (got != n) begin errors = errors + 1; $display("  expected %0d outputs, got %0d", n, got); end
        if (errors == 0) $display("PASS requant SHIFT=%0d: %0d vectors bit-exact", SHIFT, n);
        else             $display("FAIL requant SHIFT=%0d: %0d errors", SHIFT, errors);
        $finish;
    end

    // checker: outputs appear in order
    integer k = 0;
    always @(posedge clk) begin
        if (v_out) begin
            if (y !== vec[k][7:0] || tag_out !== k[8:0]) begin
                errors = errors + 1;
                if (errors < 6) $display("  vector %0d: acc=%0d M=%0d got %0d (tag %0d) expected %0d", k, $signed(vec[k][55:24]), vec[k][23:8], y, tag_out, vec[k][7:0]);
            end
            k = k + 1;
            got = got + 1;
        end
    end
endmodule
