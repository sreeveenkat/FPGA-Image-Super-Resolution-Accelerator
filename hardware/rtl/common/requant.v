// Requantizer (M4): y = clamp((acc * M + 2^(SHIFT-1)) >>> SHIFT, 0, 255)
//   acc: signed 32 bit, M: unsigned 16 bit, product up to 48 bits, arithmetic shift = floor = round half up.
// Three pipeline stages (multiply, add rounding constant, shift+clamp). Latency 3 cycles. A TAG travels with the data
// (the engine uses it for {last, channel index}).
module requant #(
    parameter SHIFT = 24,
    parameter TW    = 9
) (
    input  wire               clk,
    input  wire               rst,    // synchronous reset of the valid pipeline
    input  wire               v_in,
    input  wire signed [31:0] acc,
    input  wire        [15:0] m,
    input  wire [TW-1:0]      tag_in,
    output reg                v_out,
    output reg  [7:0]         y,
    output reg  [TW-1:0]      tag_out
);
    localparam signed [48:0] RND = 49'sd1 <<< (SHIFT - 1);

    wire signed [16:0] m_s = {1'b0, m};
    reg signed [48:0] p1, s2;
    reg v1, v2;
    reg [TW-1:0] t1, t2;
    wire signed [48:0] shifted = s2 >>> SHIFT;

    always @(posedge clk) begin
        // stage 1: multiply
        p1 <= acc * m_s;
        v1 <= v_in && !rst;
        t1 <= tag_in;
        // stage 2: add the rounding constant
        s2 <= p1 + RND;
        v2 <= v1 && !rst;
        t2 <= t1;
        // stage 3: arithmetic shift and clamp to 0..255
        if (shifted < 0)        y <= 8'd0;
        else if (shifted > 255) y <= 8'd255;
        else                    y <= shifted[7:0];
        v_out   <= v2 && !rst;
        tag_out <= t2;
    end
endmodule
