// One-tile super-resolution core (M5): 70x70x3 bytes in  ->  128x128x3 bytes out (for HC = 64), bit-exact with the integer model.
//
//   byte stream in (RGB, raster, 3 bytes per pixel, tile WITH the 3 px halo)
//     -> ram0 (24 bit)  -L1-> ram1 (128 bit) -L2-> ram2 (128 bit) -L3-> ram3 (128 bit) -L4-> ram4 (96 bit)
//     -> pixel shuffle + packer -> byte stream out (RGB, raster, 2*HC x 2*HC pixels)
//
// Four conv_engine instances (one per layer) run one after the other, started by a small sequencer; there is one activation RAM per
// layer boundary (no ping-pong, simplest to verify).  The RAMs are tile_ram_split (block RAM friendly depth split).
//
// Handshakes (AXI-Stream-like, one byte per transfer): a byte moves when valid && ready.
//   start     : one-cycle pulse while idle.  The core then accepts exactly (HC+6)^2 * 3 input bytes (in_ready high only in that phase).
//   done      : one-cycle pulse after the last output byte was accepted.  out_last marks that last byte.
//   rst       : synchronous; ONE cycle is enough, the core returns to idle and stays quiet (also aborts the engines).
// Pixel shuffle: output pixel (2y+dy, 2x+dx), colour c  =  layer-4 channel k = 4*c + 2*dy + dx at (y,x)   (PyTorch order).
//
// HC is the core size (64 for the real 70x70 tile; small values are used in tests).  SHIFT1..4 must equal the L*_SHIFT values in
// hardware/rtl/weights/network_params.vh (the testbench checks this).  WDIR is the directory of the exported *.mem files.
module sr_tile_core #(
    parameter HC     = 64,
    parameter SHIFT1 = 24,
    parameter SHIFT2 = 23,
    parameter SHIFT3 = 21,
    parameter SHIFT4 = 24,
    parameter WDIR   = "hardware/rtl/weights/",
    // derived sizes (do not override)
    parameter IW1 = HC + 6,           // L1 input  (tile with halo)
    parameter IW2 = HC + 4,           // L1 output = L2 input
    parameter IW3 = HC + 2,           // L2 output = L3 input
    parameter IW4 = HC + 2,           // L3 output = L4 input
    parameter N0  = IW1 * IW1,
    parameter N1  = IW2 * IW2,
    parameter N2  = IW3 * IW3,
    parameter N3  = IW4 * IW4,
    parameter N4  = HC * HC,
    parameter A0  = $clog2(N0),
    parameter A1  = $clog2(N1),
    parameter A2  = $clog2(N2),
    parameter A3  = $clog2(N3),
    parameter A4  = $clog2(N4)
) (
    input  wire        clk,
    input  wire        rst,
    input  wire        start,
    output wire        busy,
    output reg         done,
    // input byte stream
    input  wire        in_valid,
    input  wire [7:0]  in_data,
    output wire        in_ready,
    // output byte stream
    output wire        out_valid,
    output wire [7:0]  out_data,
    input  wire        out_ready,
    output wire        out_last,
    output reg  [31:0] cycles          // clock cycles from start until done
);
    // ------------------------------------------------------------------ sequencer state
    localparam S_IDLE = 3'd0, S_LOAD = 3'd1, S_L1 = 3'd2, S_L2 = 3'd3, S_L3 = 3'd4, S_L4 = 3'd5, S_OUT = 3'd6;
    reg [2:0] state;
    reg       entry;                      // high during the first cycle in a state (launches an engine)
    assign busy = (state != S_IDLE);

    // ------------------------------------------------------------------ memories
    wire             r0_we;
    wire [A0-1:0]    r0_waddr, r0_raddr;
    wire [23:0]      r0_wdata, r0_rdata;
    wire             r1_we, r2_we, r3_we, r4_we;
    wire [A1-1:0]    r1_waddr, r1_raddr;
    wire [A2-1:0]    r2_waddr, r2_raddr;
    wire [A3-1:0]    r3_waddr, r3_raddr;
    wire [A4-1:0]    r4_waddr, r4_raddr;
    wire [127:0]     r1_wdata, r1_rdata, r2_wdata, r2_rdata, r3_wdata, r3_rdata;
    wire [95:0]      r4_wdata, r4_rdata;

    tile_ram_split #(.WIDTH(24),  .DEPTH(N0)) ram0 (.clk(clk), .we(r0_we), .waddr(r0_waddr), .wdata(r0_wdata), .raddr(r0_raddr), .rdata(r0_rdata));
    tile_ram_split #(.WIDTH(128), .DEPTH(N1)) ram1 (.clk(clk), .we(r1_we), .waddr(r1_waddr), .wdata(r1_wdata), .raddr(r1_raddr), .rdata(r1_rdata));
    tile_ram_split #(.WIDTH(128), .DEPTH(N2)) ram2 (.clk(clk), .we(r2_we), .waddr(r2_waddr), .wdata(r2_wdata), .raddr(r2_raddr), .rdata(r2_rdata));
    tile_ram_split #(.WIDTH(128), .DEPTH(N3)) ram3 (.clk(clk), .we(r3_we), .waddr(r3_waddr), .wdata(r3_wdata), .raddr(r3_raddr), .rdata(r3_rdata));
    tile_ram_split #(.WIDTH(96),  .DEPTH(N4)) ram4 (.clk(clk), .we(r4_we), .waddr(r4_waddr), .wdata(r4_wdata), .raddr(r4_raddr), .rdata(r4_rdata));

    // ------------------------------------------------------------------ input loader: bytes -> 24-bit pixel words in ram0
    reg [A0:0]  lp;                       // pixel index being assembled
    reg [1:0]   lb;                       // byte of the pixel (0 = R, 1 = G, 2 = B)
    reg [7:0]   b0, b1;
    wire        ld_active = (state == S_LOAD);
    assign in_ready = ld_active;
    wire        ld_take = in_valid && in_ready;
    wire        ld_last = ld_take && (lb == 2) && (lp == N0 - 1);
    assign r0_we    = ld_take && (lb == 2);
    assign r0_waddr = lp[A0-1:0];
    assign r0_wdata = {in_data, b1, b0};  // channel c at bits [8c +: 8]

    always @(posedge clk) begin
        if (rst || (state == S_IDLE)) begin
            lp <= 0; lb <= 0;
        end else if (ld_take) begin
            if (lb == 0) b0 <= in_data;
            if (lb == 1) b1 <= in_data;
            if (lb == 2) begin lb <= 0; lp <= lp + 1; end
            else lb <= lb + 2'd1;
        end
    end

    // ------------------------------------------------------------------ the four layer engines
    wire s1 = entry && (state == S_L1), s2 = entry && (state == S_L2), s3 = entry && (state == S_L3), s4 = entry && (state == S_L4);
    wire d1, d2, d3, d4, bz1, bz2, bz3, bz4;
    wire [31:0] cy1, cy2, cy3, cy4;

    conv_engine #(.C_IN(3),  .C_OUT(16), .K(3), .DEPTHWISE(0), .IN_W(IW1), .IN_H(IW1), .SHIFT(SHIFT1),
                  .W_FILE({WDIR, "wrom_L1.mem"}), .B_FILE({WDIR, "bias_L1.mem"}), .M_FILE({WDIR, "mult_L1.mem"})) e1 (
        .clk(clk), .rst(rst), .start(s1), .busy(bz1), .done(d1), .in_addr(r0_raddr), .in_data(r0_rdata),
        .out_we(r1_we), .out_addr(r1_waddr), .out_data(r1_wdata), .cycles(cy1));
    conv_engine #(.C_IN(16), .C_OUT(16), .K(3), .DEPTHWISE(1), .IN_W(IW2), .IN_H(IW2), .SHIFT(SHIFT2),
                  .W_FILE({WDIR, "wrom_L2.mem"}), .B_FILE({WDIR, "bias_L2.mem"}), .M_FILE({WDIR, "mult_L2.mem"})) e2 (
        .clk(clk), .rst(rst), .start(s2), .busy(bz2), .done(d2), .in_addr(r1_raddr), .in_data(r1_rdata),
        .out_we(r2_we), .out_addr(r2_waddr), .out_data(r2_wdata), .cycles(cy2));
    conv_engine #(.C_IN(16), .C_OUT(16), .K(1), .DEPTHWISE(0), .IN_W(IW3), .IN_H(IW3), .SHIFT(SHIFT3),
                  .W_FILE({WDIR, "wrom_L3.mem"}), .B_FILE({WDIR, "bias_L3.mem"}), .M_FILE({WDIR, "mult_L3.mem"})) e3 (
        .clk(clk), .rst(rst), .start(s3), .busy(bz3), .done(d3), .in_addr(r2_raddr), .in_data(r2_rdata),
        .out_we(r3_we), .out_addr(r3_waddr), .out_data(r3_wdata), .cycles(cy3));
    conv_engine #(.C_IN(16), .C_OUT(12), .K(3), .DEPTHWISE(0), .IN_W(IW4), .IN_H(IW4), .SHIFT(SHIFT4),
                  .W_FILE({WDIR, "wrom_L4.mem"}), .B_FILE({WDIR, "bias_L4.mem"}), .M_FILE({WDIR, "mult_L4.mem"})) e4 (
        .clk(clk), .rst(rst), .start(s4), .busy(bz4), .done(d4), .in_addr(r3_raddr), .in_data(r3_rdata),
        .out_we(r4_we), .out_addr(r4_waddr), .out_data(r4_wdata), .cycles(cy4));

    // ------------------------------------------------------------------ pixel shuffle + output packer (reads ram4)
    localparam OWID = 2 * HC;                 // output tile width/height in pixels
    reg [15:0]    oy, ox;                     // output pixel position
    reg [1:0]     oc;                         // colour byte of the pixel
    reg [A4:0]    obase;                      // (oy >> 1) * HC
    reg           ofetch;                     // one-cycle RAM read after the word changes
    wire          out_active = (state == S_OUT);
    wire [15:0]   xh = ox >> 1;
    assign r4_raddr  = obase + xh;
    // channel index inside the 12-channel word: k = 4*c + 2*dy + dx
    wire [3:0]    kch = {oc[1:0], oy[0], ox[0]};
    assign out_valid = out_active && !ofetch;
    assign out_data  = r4_rdata[8*kch +: 8];
    assign out_last  = out_valid && (oy == OWID - 1) && (ox == OWID - 1) && (oc == 2);   // only meaningful (and only high) together with out_valid
    wire          o_take = out_valid && out_ready;

    // ------------------------------------------------------------------ sequencer
    always @(posedge clk) begin
        done <= 1'b0;
        entry <= 1'b0;
        if (rst) begin
            state <= S_IDLE;
            ofetch <= 1'b0;
            cycles <= 0;
        end else begin
            case (state)
                S_IDLE: if (start) begin state <= S_LOAD; cycles <= 0; end
                S_LOAD: if (ld_last) begin state <= S_L1; entry <= 1'b1; end
                S_L1:   if (d1) begin state <= S_L2; entry <= 1'b1; end
                S_L2:   if (d2) begin state <= S_L3; entry <= 1'b1; end
                S_L3:   if (d3) begin state <= S_L4; entry <= 1'b1; end
                S_L4:   if (d4) begin
                            state <= S_OUT;
                            oy <= 0; ox <= 0; oc <= 0; obase <= 0; ofetch <= 1'b1;   // first word must be read
                        end
                S_OUT: begin
                    if (ofetch) begin
                        ofetch <= 1'b0;                                       // RAM data valid from the next cycle
                    end else if (o_take) begin
                        if (oc != 2) begin
                            oc <= oc + 2'd1;
                        end else begin
                            oc <= 0;
                            if (ox == OWID - 1) begin                          // end of an output row
                                ox <= 0;
                                if (oy == OWID - 1) begin                      // end of the tile
                                    state <= S_IDLE;
                                    done  <= 1'b1;
                                end else begin
                                    oy <= oy + 16'd1;
                                    if (oy[0]) obase <= obase + HC;            // moving from an odd to the next even row
                                    ofetch <= 1'b1;
                                end
                            end else begin
                                ox <= ox + 16'd1;
                                if (ox[0]) ofetch <= 1'b1;                     // odd -> even x: new low-res pixel, new word
                            end
                        end
                    end
                end
                default: state <= S_IDLE;
            endcase
            if (state != S_IDLE && !done) cycles <= cycles + 1;
        end
    end
endmodule
