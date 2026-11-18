// LUT version of pipe_mul (branch pipe2: lanes with index >= NDSP). Same function and latency; only the use_dsp attribute differs.
// One multiplier lane of a pipeline stage (docs/ARCHITECTURE_PIPELINE.md):  prod = a * w,  a: uint8 activation, w: int8 weight.
// Two register stages: input registers (DSP48 A/B registers) and the product register (M register).  Latency 2: inputs at cycle t -> prod from t+2.
// No reset: valid flags travel separately in the stage.
(* use_dsp = "no" *)
module pipe_mul_lut #(
    parameter LAT = 2                      // pipe4: 3 = two cycles for the multiply (8x4 half products, then their sum) for 142.86 MHz
) (
    input  wire               clk,
    input  wire        [7:0]  a,
    input  wire signed [7:0]  w,
    output reg  signed [16:0] prod
);
    reg        [7:0] a_r;
    reg signed [7:0] w_r;
    wire signed [8:0] a_s = {1'b0, a_r};   // unsigned activation as a positive signed number
    generate
        if (LAT == 2) begin : g2
            always @(posedge clk) begin
                a_r  <= a;
                w_r  <= w;
                prod <= a_s * w_r;
            end
        end else begin : g3                // w = 16 * w[7:4] (signed) + w[3:0] (unsigned)
            reg signed [13:0] pp_lo;       // a * w[3:0]: 0..3825
            reg signed [13:0] pp_hi;       // a * w[7:4]: -2040..1785
            always @(posedge clk) begin
                a_r   <= a;
                w_r   <= w;
                pp_lo <= a_s * $signed({1'b0, w_r[3:0]});
                pp_hi <= a_s * $signed(w_r[7:4]);
                prod  <= $signed(pp_lo) + ($signed(pp_hi) <<< 4);
            end
        end
    endgenerate
endmodule
