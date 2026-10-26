// Anchor FIFO (docs/ARCHITECTURE_PIPELINE.md): the interior input pixels (x+3, y+3) in raster order, popped by L4 once per output pixel.
// `pop` reads the head; `dout` is valid from the next cycle and stays until the next pop.  `err` (sticky): push when full or pop when empty
// (the design guarantees neither for W <= MAXW - 6; the simulation and the ERROR_CODE register report it if it ever happens).
module anchor_fifo #(
    parameter DEPTH = 4096,
    parameter AW    = $clog2(DEPTH)
) (
    input  wire        clk,
    input  wire        rst,
    input  wire        push,
    input  wire [23:0] din,
    input  wire        pop,
    output reg  [23:0] dout,
    output wire        full,
    output reg         err
);
    reg [23:0] mem [0:DEPTH-1];
    reg [AW:0] wp, rp;
    assign full = (wp - rp) == DEPTH;
    wire empty  = (wp == rp);
    always @(posedge clk) begin
        if (push && !full) mem[wp[AW-1:0]] <= din;
        if (pop) dout <= mem[rp[AW-1:0]];
        if (rst) begin
            wp <= 0; rp <= 0; err <= 1'b0;
        end else begin
            if (push && !full) wp <= wp + 1'b1;
            if (pop && !empty) rp <= rp + 1'b1;
            if ((push && full) || (pop && empty)) err <= 1'b1;
        end
    end
endmodule
