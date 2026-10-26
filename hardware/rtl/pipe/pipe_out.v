// Output side of the pipeline (docs/ARCHITECTURE_PIPELINE.md): L4 results (12 bytes per LR pixel) -> HR frame in raster order on a 32-bit stream.
//
//   two banks of MAXW x 96 bits: bank (y & 1) holds LR row y.  L4 may START the first pixel of a row only when that row's bank is free (`ok`).
//   When the last pixel of a row is written the bank is full; the reader then sends HR row 2y (dy = 0) and 2y+1 (dy = 1):
//   for every x, HR pixel (2x+dx, 2y+dy) = colours c = 0..2 of L4 channel 4c + 2dy + dx (PyTorch pixel shuffle), R first.
//   A 24 -> 32-bit packer makes little-endian beats (first byte = bits 7:0).  TLAST on beat 3*W*H - 1; `done` = that beat was accepted.
module pipe_out #(
    parameter MAXW = 1024,
    parameter AW   = $clog2(MAXW)
) (
    input  wire         clk,
    input  wire         rst,
    input  wire         start,
    input  wire [15:0]  lr_w,
    input  wire [31:0]  n_beats,      // 3 * W * H, stable from `start` on (computed by the core)
    // L4 side
    input  wire         px_start,     // L4 starts a pixel (raster order)
    output wire         ok,
    input  wire         in_valid,     // L4 result (raster order)
    input  wire [95:0]  in_data,
    // stream
    output wire [31:0]  m_axis_tdata,
    output wire         m_axis_tvalid,
    input  wire         m_axis_tready,
    output wire         m_axis_tlast,
    output reg          done,
    output reg  [31:0]  beats
);
    reg [95:0] mem [0:2*MAXW-1];      // address {bank, x}
    reg [1:0]  free, full;
    reg [15:0] sx, wx, rx;            // next L4 start column, next write column, read column
    reg        sb, wb, rb, dy;        // bank of the next L4 start, of the next write, being read; HR row within the bank
    assign ok = (sx != 16'd0) || free[sb];

    always @(posedge clk) begin
        if (in_valid) mem[{wb, wx[AW-1:0]}] <= in_data;
    end

    // ------------------------------------------------------------------ reader
    localparam S_IDLE = 2'd0, S_RD = 2'd1, S_E0 = 2'd2, S_E1 = 2'd3;
    reg [1:0]  st;
    reg [95:0] rq;
    wire       rel;                  // the bank being read is finished this cycle
    wire       pk_ok;
    reg [AW:0] raddr;
    always @(posedge clk) rq <= mem[raddr];

    wire [23:0] pix0 = {rq[8*(8 + 2*dy) +: 8], rq[8*(4 + 2*dy) +: 8], rq[8*(0 + 2*dy) +: 8]};
    wire [23:0] pix1 = {rq[8*(9 + 2*dy) +: 8], rq[8*(5 + 2*dy) +: 8], rq[8*(1 + 2*dy) +: 8]};
    wire        pv   = (st == S_E0) || (st == S_E1);
    wire [23:0] pix  = (st == S_E0) ? pix0 : pix1;
    assign rel = (st == S_E1) && pk_ok && (rx == lr_w - 1) && dy;

    always @(posedge clk) begin
        if (rst || start) begin
            st <= S_IDLE; rx <= 16'd0; rb <= 1'b0; dy <= 1'b0; raddr <= 0;
        end else begin
            case (st)
                S_IDLE: if (full[rb]) begin raddr <= {rb, {AW{1'b0}}}; st <= S_RD; end
                S_RD:   st <= S_E0;                                     // rq valid in S_E0 (raddr is held)
                S_E0:   if (pk_ok) st <= S_E1;
                S_E1:   if (pk_ok) begin
                            if (rx == lr_w - 1) begin
                                rx <= 16'd0;
                                if (dy) begin dy <= 1'b0; rb <= !rb; st <= S_IDLE; end
                                else begin dy <= 1'b1; raddr <= {rb, {AW{1'b0}}}; st <= S_RD; end
                            end else begin
                                rx <= rx + 16'd1; raddr <= {rb, rx[AW-1:0] + 1'b1}; st <= S_RD;
                            end
                        end
            endcase
        end
    end

    // ------------------------------------------------------------------ bank bookkeeping
    always @(posedge clk) begin
        if (rst || start) begin
            free <= 2'b11; full <= 2'b00; sx <= 16'd0; wx <= 16'd0; sb <= 1'b0; wb <= 1'b0;
        end else begin
            if (px_start) begin
                if (sx == 16'd0) free[sb] <= 1'b0;
                if (sx == lr_w - 1) begin sx <= 16'd0; sb <= !sb; end else sx <= sx + 16'd1;
            end
            if (in_valid) begin
                if (wx == lr_w - 1) begin wx <= 16'd0; wb <= !wb; full[wb] <= 1'b1; end else wx <= wx + 16'd1;
            end
            if (rel) begin full[rb] <= 1'b0; free[rb] <= 1'b1; end
        end
    end

    // ------------------------------------------------------------------ 24 -> 32-bit packer and the stream register
    reg [55:0] pb;
    reg [2:0]  n;                    // bytes in pb (0..7)
    reg [31:0] ow;
    reg        ov, olast;
    wire       emit = (n >= 3'd4) && (!ov || m_axis_tready);
    wire [2:0] n1   = emit ? n - 3'd4 : n;
    wire [55:0] pb1 = emit ? {32'd0, pb[55:32]} : pb;
    assign pk_ok = (n1 <= 3'd4);
    wire       pacc = pv && pk_ok;
    assign m_axis_tdata  = ow;
    assign m_axis_tvalid = ov;
    assign m_axis_tlast  = ov && olast;

    always @(posedge clk) begin
        done <= 1'b0;
        if (rst || start) begin
            pb <= 56'd0; n <= 3'd0; ow <= 32'd0; ov <= 1'b0; olast <= 1'b0; beats <= 32'd0;
        end else begin
            pb <= pacc ? (pb1 | ({32'd0, pix} << (8 * n1))) : pb1;
            n  <= n1 + (pacc ? 3'd3 : 3'd0);
            if (emit) begin
                ow <= pb[31:0]; ov <= 1'b1; olast <= (beats == n_beats - 1); beats <= beats + 32'd1;
            end else if (ov && m_axis_tready) ov <= 1'b0;
            if (ov && m_axis_tready && olast) done <= 1'b1;
        end
    end

endmodule
