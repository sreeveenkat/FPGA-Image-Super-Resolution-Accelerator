// tile_ram_split (M5): matches a plain array for several (WIDTH, DEPTH) pairs, incl. depth 4096 (no upper part), a small depth, reads across the split boundary and the peek() helper
module tb_tile_ram_split;
  reg clk = 0; always #5 clk = ~clk;
  reg we = 0; reg [12:0] wa = 0, ra = 0; reg [127:0] wd = 0;
  wire [127:0] rd_a, rd_b, rd_c;
  tile_ram_split #(.WIDTH(128), .DEPTH(4624)) a (.clk(clk), .we(we), .waddr(wa[12:0]), .wdata(wd), .raddr(ra[12:0]), .rdata(rd_a));
  tile_ram_split #(.WIDTH(128), .DEPTH(4096)) b (.clk(clk), .we(we && wa < 4096), .waddr(wa[11:0]), .wdata(wd), .raddr(ra[11:0]), .rdata(rd_b));
  tile_ram_split #(.WIDTH(128), .DEPTH(144))  c (.clk(clk), .we(we && wa < 144),  .waddr(wa[7:0]),  .wdata(wd), .raddr(ra[7:0]),  .rdata(rd_c));
  reg [127:0] ref_mem [0:4623];
  integer i, errs = 0;
  initial begin
    for (i = 0; i < 4624; i = i + 1) begin
      @(negedge clk); we = 1; wa = i; wd = {4{$random}}; ref_mem[i] = wd;
    end
    @(negedge clk); we = 0;
    for (i = 0; i < 4624; i = i + 1) begin
      @(negedge clk); ra = i;
      @(negedge clk);
      if (rd_a !== ref_mem[i]) begin errs = errs + 1; if (errs < 4) $display("a addr %0d mismatch", i); end
      if (i < 4096 && rd_b !== ref_mem[i]) begin errs = errs + 1; if (errs < 4) $display("b addr %0d mismatch", i); end
      if (i < 144  && rd_c !== ref_mem[i]) begin errs = errs + 1; if (errs < 4) $display("c addr %0d mismatch", i); end
      if (a.peek(i) !== ref_mem[i]) begin errs = errs + 1; if (errs < 4) $display("peek %0d mismatch", i); end
    end
    // back-to-back reads across the split boundary: address 4095, 4096, 4095, one per clock; data follows one clock later
    @(negedge clk); ra = 4095;
    @(negedge clk); ra = 4096; if (rd_a !== ref_mem[4095]) begin errs = errs + 1; $display("boundary 4095 (lo) wrong"); end
    @(negedge clk); ra = 4095; if (rd_a !== ref_mem[4096]) begin errs = errs + 1; $display("boundary 4096 (hi) wrong"); end
    @(negedge clk);            if (rd_a !== ref_mem[4095]) begin errs = errs + 1; $display("boundary 4095 again wrong"); end
    // overwrite read-during-write: old data
    if (errs == 0) $display("PASS tile_ram_split (3 sizes, boundary reads, peek)"); else $display("FAIL tile_ram_split: %0d errors", errs);
    $finish;
  end
endmodule
