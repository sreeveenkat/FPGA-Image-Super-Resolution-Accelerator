// TWO multiplier lanes in ONE DSP48E1 (branch pipe2p, docs/ARCHITECTURE_PIPELINE_V2P.md): both products share the activation `a`.
//   A = (w2 << 17) + w1  (25-bit signed),  B = a (uint8 as a 9-bit positive signed number),  P = A * B  (|P| < 2^33, P[33:0] kept)
//   lo     = signed P[16:0]               = a * w1                                     (exact)
//   hi_raw = signed P[33:17], b = P[16]   : a * w2 = hi_raw + b   (b = the borrow of a negative low field; the adder tree adds the b's of a tree once)
// Exhaustively checked for all a in 0..255 and w1, w2 in -127..127 (16,646,400 cases).  This works because the DSP only multiplies: the products are
// summed OUTSIDE the DSP (adder trees), so the low field never overflows into the high one.
// Latency 2 like pipe_mul: input registers (A/B registers) then the product register (M or P register).  No reset (valid flags travel separately).
(* use_dsp = "yes" *)
module pipe_mul2 (
    input  wire               clk,
    input  wire        [7:0]  a,
    input  wire signed [7:0]  w1,
    input  wire signed [7:0]  w2,
    output wire signed [16:0] lo,
    output wire signed [16:0] hi_raw,
    output wire               b
);
    reg        [7:0]  a_r;
    reg signed [24:0] A_r;
    reg signed [33:0] p;
    wire signed [8:0]  a_s = {1'b0, a_r};
    wire signed [24:0] A_n = $signed({w2, 17'd0}) + $signed({{17{w1[7]}}, w1});   // the weights come from a ROM: this add folds into the ROM logic
    always @(posedge clk) begin
        a_r <= a;
        A_r <= A_n;
        p   <= A_r * a_s;
    end
    assign lo     = p[16:0];
    assign hi_raw = p[33:17];
    assign b      = p[16];
endmodule
