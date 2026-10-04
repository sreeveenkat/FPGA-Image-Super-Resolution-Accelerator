// tile_ram.v: write/read, 1-cycle read latency, read-during-write returns old data.
`timescale 1ns/1ps
module tb_tile_ram;
    reg clk = 0;
    always #5 clk = ~clk;
    reg we = 0;
    reg [5:0] waddr = 0, raddr = 0;
    reg [127:0] wdata = 0;
    wire [127:0] rdata;
    tile_ram #(.WIDTH(128), .DEPTH(50)) dut (.clk(clk), .we(we), .waddr(waddr), .wdata(wdata), .raddr(raddr), .rdata(rdata));
    integer i, errors = 0;
    initial begin
        for (i = 0; i < 50; i = i + 1) begin
            @(negedge clk); we = 1; waddr = i; wdata = {4{32'h01010101 * i[7:0]}} ^ {i[7:0], 120'h123456789abcdef0123456789abcde};
        end
        @(negedge clk); we = 0;
        for (i = 0; i < 50; i = i + 1) begin
            @(negedge clk); raddr = i;
            @(posedge clk); #1;  // data appears one clock after the address was presented
            if (rdata !== ({4{32'h01010101 * i[7:0]}} ^ {i[7:0], 120'h123456789abcdef0123456789abcde})) begin
                errors = errors + 1; $display("  addr %0d: got %h", i, rdata);
            end
        end
        // read-during-write: reading address 3 while overwriting it returns the OLD value
        @(negedge clk); raddr = 6'd3; we = 1; waddr = 6'd3; wdata = 128'hffff;
        @(negedge clk); we = 0;
        if (rdata === 128'hffff) begin errors = errors + 1; $display("  read-during-write returned new data"); end
        raddr = 6'd3;
        @(negedge clk);
        if (rdata !== 128'hffff) begin errors = errors + 1; $display("  overwrite not stored"); end
        if (errors == 0) $display("PASS tile_ram"); else $display("FAIL tile_ram: %0d errors", errors);
        $finish;
    end
endmodule
