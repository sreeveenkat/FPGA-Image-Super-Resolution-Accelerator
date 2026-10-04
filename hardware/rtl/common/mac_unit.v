// One multiply-accumulate lane of the conv engine (M4).
//   acc <= (first ? bias : acc) + a * w        a: uint8 activation, w: int8 weight, acc: int32
// Two pipeline stages: product register (maps to the DSP48 M-register), then accumulate.
// Latency: inputs at cycle t  ->  `acc` holds the updated value from cycle t+2 on (so after the last step of a pixel,
// the final accumulator is visible 2 cycles after that step's inputs).
// No reset: after an engine reset the accumulator is simply overwritten by the next pixel's `first` step.
(* use_dsp = "yes" *)
module mac_unit (
    input  wire               clk,
    input  wire               v,      // inputs a/w/first are valid this cycle
    input  wire               first,  // first step of an output pixel: start from bias instead of acc
    input  wire signed [31:0] bias,
    input  wire        [7:0]  a,
    input  wire signed [7:0]  w,
    output reg  signed [31:0] acc
);
    reg signed [16:0] prod;
    reg v_d, first_d;
    wire signed [8:0] a_s = {1'b0, a};  // unsigned activation as a positive signed number

    always @(posedge clk) begin
        prod    <= a_s * w;
        v_d     <= v;
        first_d <= first;
        if (v_d) acc <= (first_d ? bias : acc) + prod;
    end
endmodule
