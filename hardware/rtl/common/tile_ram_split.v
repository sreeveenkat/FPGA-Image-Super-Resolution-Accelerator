// Activation RAM for the tile core (M5): same interface and 1-cycle read latency as tile_ram, but the array is split by address into
//   lo: the largest power-of-two depth <= DEPTH   and   hi: the remainder.
// Why: Vivado rounds the depth of a cascaded block-RAM array up to a power of two, so one 4624 x 128-bit buffer cost 32 RAMB36
// (as if it were 8192 deep) instead of about 20.  With the split the 4096-deep part and the small remainder map separately.
// (Addresses >= DEPTH are never written; reading them returns undefined data.)
module tile_ram_split #(
    parameter WIDTH = 128,
    parameter DEPTH = 4624,
    parameter AW    = $clog2(DEPTH),
    // largest power of two <= DEPTH (computed without a function so it works in every tool)
    parameter SPLIT = (DEPTH >= 8192) ? 8192 : (DEPTH >= 4096) ? 4096 : (DEPTH >= 2048) ? 2048 : (DEPTH >= 1024) ? 1024 :
                      (DEPTH >= 512) ? 512 : (DEPTH >= 256) ? 256 : (DEPTH >= 128) ? 128 : (DEPTH >= 64) ? 64 :
                      (DEPTH >= 32) ? 32 : (DEPTH >= 16) ? 16 : (DEPTH >= 8) ? 8 : (DEPTH >= 4) ? 4 : (DEPTH >= 2) ? 2 : 1,
    parameter HI    = DEPTH - SPLIT
) (
    input  wire             clk,
    input  wire             we,
    input  wire [AW-1:0]    waddr,
    input  wire [WIDTH-1:0] wdata,
    input  wire [AW-1:0]    raddr,
    output wire [WIDTH-1:0] rdata
);
    localparam HI_N = (HI > 0) ? HI : 1;   // never a zero-size array; unused (and optimised away) when HI == 0
    reg [WIDTH-1:0] mem_lo [0:SPLIT-1];
    reg [WIDTH-1:0] mem_hi [0:HI_N-1];
    reg [WIDTH-1:0] q_lo, q_hi;
    reg             sel_hi;
    wire w_hi = (HI > 0) && (waddr >= SPLIT);
    wire r_hi = (HI > 0) && (raddr >= SPLIT);

    always @(posedge clk) begin
        if (we && !w_hi) mem_lo[waddr[$clog2(SPLIT)-1:0]] <= wdata;
        q_lo <= mem_lo[raddr[$clog2(SPLIT)-1:0]];
    end

    generate
        if (HI > 0) begin : hi_part
            always @(posedge clk) begin
                if (we && w_hi) mem_hi[waddr - SPLIT] <= wdata;
                q_hi   <= mem_hi[raddr - SPLIT];
                sel_hi <= r_hi;
            end
            assign rdata = sel_hi ? q_hi : q_lo;
        end else begin : no_hi
            assign rdata = q_lo;
        end
    endgenerate

    // simulation helper for testbenches: read a word by hierarchical reference, e.g.  dut.ram1.peek(addr)
    // synthesis translate_off
    function [WIDTH-1:0] peek(input integer a);
        begin
            if (a < SPLIT) peek = mem_lo[a];
            else           peek = mem_hi[a - SPLIT];
        end
    endfunction
    // synthesis translate_on
endmodule
