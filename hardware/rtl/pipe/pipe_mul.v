// One multiplier lane of a pipeline stage (docs/ARCHITECTURE_PIPELINE.md):  prod = a * w,  a: uint8 activation, w: int8 weight.
// Two register stages: input registers (DSP48 A/B registers) and the product register (M register).  Latency 2: inputs at cycle t -> prod from t+2.
// No reset: valid flags travel separately in the stage.
(* use_dsp = "yes" *)
module pipe_mul #(
    parameter LAT = 2                      // pipe4: 3 = one more output register (the DSP48's P register)
) (
    input  wire               clk,
    input  wire        [7:0]  a,
    input  wire signed [7:0]  w,
    output reg  signed [16:0] prod
);
    reg        [7:0] a_r;
    reg signed [7:0] w_r;
    reg signed [16:0] p1;
    wire signed [8:0] a_s = {1'b0, a_r};   // unsigned activation as a positive signed number
    always @(posedge clk) begin
        a_r  <= a;
        w_r  <= w;
        p1   <= a_s * w_r;
    end
    generate
        if (LAT == 2) begin : g2
            always @* prod = p1;
        end else begin : g3
            always @(posedge clk) prod <= p1;
        end
    endgenerate
endmodule
