// Simple dual-port RAM with a synchronous read (1-cycle latency), the style Vivado maps to block RAM.
// Read-during-write at the same address returns the OLD data.
module tile_ram #(
    parameter WIDTH = 128,
    parameter DEPTH = 4900,
    parameter AW    = $clog2(DEPTH)
) (
    input  wire             clk,
    input  wire             we,
    input  wire [AW-1:0]    waddr,
    input  wire [WIDTH-1:0] wdata,
    input  wire [AW-1:0]    raddr,
    output reg  [WIDTH-1:0] rdata
);
    reg [WIDTH-1:0] mem [0:DEPTH-1];

    always @(posedge clk) begin
        if (we) mem[waddr] <= wdata;
        rdata <= mem[raddr];
    end
endmodule
