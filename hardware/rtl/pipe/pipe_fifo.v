// FIFO between two pipeline stages, with reservations (docs/ARCHITECTURE_PIPELINE.md).
// The producer stage reserves a place when it STARTS a pixel (`reserve`) and pushes the result some cycles later (`push`, never refused);
// `ok` = a further reservation fits.  The count of reservations = entries + results still being computed, so the FIFO can never overflow.
// Read side: first-word-fall-through valid/ready.  DEPTH must be a power of two.
module pipe_fifo #(
    parameter W     = 128,
    parameter DEPTH = 8,
    parameter AW    = $clog2(DEPTH)
) (
    input  wire         clk,
    input  wire         rst,
    input  wire         reserve,
    output wire         ok,
    input  wire         push,
    input  wire [W-1:0] din,
    output wire         out_valid,
    output wire [W-1:0] dout,
    input  wire         out_ready,
    output reg          err          // sticky: push without a reservation or overflow (simulation check, also visible in hardware)
);
    reg [W-1:0]  mem [0:DEPTH-1];
    reg [AW:0]   wp, rp, res;
    wire         pop = out_valid && out_ready;
    assign out_valid = (wp != rp);
    assign dout      = mem[rp[AW-1:0]];
    assign ok        = (res < DEPTH);

    always @(posedge clk) begin
        if (push) mem[wp[AW-1:0]] <= din;
        if (rst) begin
            wp <= 0; rp <= 0; res <= 0; err <= 1'b0;
        end else begin
            if (push) wp <= wp + 1'b1;
            if (pop)  rp <= rp + 1'b1;
            res <= res + (reserve ? 1'b1 : 1'b0) - (pop ? 1'b1 : 1'b0);
            if (push && (wp - rp == DEPTH)) err <= 1'b1;
            if (reserve && !ok) err <= 1'b1;
        end
    end
endmodule
