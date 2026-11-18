// Anchor FIFO (docs/ARCHITECTURE_PIPELINE.md): the interior input pixels (x+3, y+3) in raster order, popped by L4 once per output pixel.
// `pop` reads the head; `dout` is valid from the next cycle and stays until the next pop.  `full` is REGISTERED and conservative (high from DEPTH - 4
// entries on: at most one push per cycle, so a push is stopped before the FIFO really fills; no combinational path from the pointers into the producer).
// `err` (sticky): push when really full or pop when empty
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
    output reg         full,
    output reg         err
);
    reg [23:0] mem [0:DEPTH-1];
    reg [AW:0] wp, rp;
    reg  [AW:0] cnt;                         // occupancy (= wp - rp, AW+1 bits).  pipe4: kept as its own register (+push -pop) instead of the subtraction
                                             // wp - rp, which was on the 142.86 MHz critical path (wp -> subtract -> compare -> wp enable, WNS -0.415 ns).
                                             // (2026-10-26 bug: wp - rp evaluated in 32 bits broke after the first pointer wrap; a register cannot.)
    wire really_full = (cnt == DEPTH);
    wire empty       = (cnt == 0);
    always @(posedge clk) begin
        if (push && !really_full) mem[wp[AW-1:0]] <= din;
        if (pop) dout <= mem[rp[AW-1:0]];
        if (rst) begin
            wp <= 0; rp <= 0; cnt <= 0; err <= 1'b0; full <= 1'b0;
        end else begin
            if (push && !really_full) wp <= wp + 1'b1;
            if (pop && !empty) rp <= rp + 1'b1;
            cnt <= cnt + ((push && !really_full) ? 1'b1 : 1'b0) - ((pop && !empty) ? 1'b1 : 1'b0);
            if ((push && really_full) || (pop && empty)) err <= 1'b1;
            full <= (cnt >= DEPTH - 4);
        end
    end
endmodule
