// Top module of the super-resolution accelerator, whole-frame PIPELINE version (branch `pipe`, docs/ARCHITECTURE_PIPELINE.md): AXI4-Lite control +
// AXI-Stream data around sr_pipe_core.  Same module name and ports as the tiled design, so the Vivado block design is unchanged.
//
//   ARM --AXI4-Lite--> registers --start/soft reset/size--> sr_pipe_core;  DMA MM2S --s_axis--> sr_pipe_core --m_axis--> DMA S2MM
//
// Register map (byte offsets, 32-bit registers; software/board/sr_regs.h and docs/REGISTER_MAP.md must agree):
//   0x00 CONTROL    W: bit0 start (ignored while busy; refused with ERROR_CODE 4 if FRAME_W/FRAME_H are out of range; an accepted start clears
//                      DONE and ERROR), bit1 soft reset (clears DONE/ERROR, aborts a frame).  Only bits written with wstrb[0] set take effect.  Reads 0.
//   0x04 STATUS     R: bit0 busy, bit1 done (sticky), bit2 error (sticky, = ERROR_CODE != 0)
//   0x08 FRAME_W    RW: LR frame width W, 1..MAX_W (sampled at start)
//   0x0C CYCLES     R: cycles from the accepted start to the last output beat of the frame (running count while busy)
//   0x10 ERROR_CODE R: 0 none | 1 TLAST before the last input beat | 2 last input beat without TLAST | 3 TKEEP != 4'hF | 4 frame size out of range (W 1..MAX_W, H 1..4096)
//                      (start refused) | 5 internal FIFO error (never expected).  The FIRST error is kept.  Errors are only reported (except 4).
//   0x14 VERSION    R: 32'h5352_5301  (pipeline, R3q weights + anchor, 125 MHz)
//   0x18 FRAME_H    RW: LR frame height H, 1..4096 (sampled at start)
//   0x1C MAX_W      R: largest W (MAXW - 6)
//   0x20 DBG_IN_BEATS  R: input beats accepted in the current/last frame
//   0x24 DBG_OUT_BEATS R: output beats sent in the current/last frame
//   other addresses read 0, writes to them are accepted and ignored (OKAY response).
// Streams: input = the replicate-padded LR frame, ceil(3 (W+6)(H+6) / 4) beats (the last one may carry unused bytes), TLAST on the last beat;
// output = 3 W H beats (2W x 2H x 3 bytes, raster), TLAST on the last beat.  s_axis_tready stays low until a frame has started.
//
// WDIR default is an ABSOLUTE path (the .mem files must be found by $readmemh during synthesis); build_m6_system.tcl points it at the checkout.
module sr_accel_top #(
    parameter MAXW = 1024,
    parameter WDIR = "/home/sreevenkat/Desktop/venkat/sem_project_all/hardware/rtl/weights/"
) (
    (* X_INTERFACE_INFO = "xilinx.com:signal:clock:1.0 aclk CLK" *)
    (* X_INTERFACE_PARAMETER = "ASSOCIATED_BUSIF s_axi:s_axis:m_axis, ASSOCIATED_RESET aresetn, FREQ_HZ 125000000" *)
    input  wire        aclk,
    (* X_INTERFACE_INFO = "xilinx.com:signal:reset:1.0 aresetn RST" *)
    (* X_INTERFACE_PARAMETER = "POLARITY ACTIVE_LOW" *)
    input  wire        aresetn,

    // AXI4-Lite slave (control registers)
    (* X_INTERFACE_INFO = "xilinx.com:interface:aximm:1.0 s_axi AWADDR" *)  input  wire [5:0]  s_axi_awaddr,
    (* X_INTERFACE_INFO = "xilinx.com:interface:aximm:1.0 s_axi AWPROT" *)  input  wire [2:0]  s_axi_awprot,
    (* X_INTERFACE_INFO = "xilinx.com:interface:aximm:1.0 s_axi AWVALID" *) input  wire        s_axi_awvalid,
    (* X_INTERFACE_INFO = "xilinx.com:interface:aximm:1.0 s_axi AWREADY" *) output wire        s_axi_awready,
    (* X_INTERFACE_INFO = "xilinx.com:interface:aximm:1.0 s_axi WDATA" *)   input  wire [31:0] s_axi_wdata,
    (* X_INTERFACE_INFO = "xilinx.com:interface:aximm:1.0 s_axi WSTRB" *)   input  wire [3:0]  s_axi_wstrb,
    (* X_INTERFACE_INFO = "xilinx.com:interface:aximm:1.0 s_axi WVALID" *)  input  wire        s_axi_wvalid,
    (* X_INTERFACE_INFO = "xilinx.com:interface:aximm:1.0 s_axi WREADY" *)  output wire        s_axi_wready,
    (* X_INTERFACE_INFO = "xilinx.com:interface:aximm:1.0 s_axi BRESP" *)   output wire [1:0]  s_axi_bresp,
    (* X_INTERFACE_INFO = "xilinx.com:interface:aximm:1.0 s_axi BVALID" *)  output wire        s_axi_bvalid,
    (* X_INTERFACE_INFO = "xilinx.com:interface:aximm:1.0 s_axi BREADY" *)  input  wire        s_axi_bready,
    (* X_INTERFACE_INFO = "xilinx.com:interface:aximm:1.0 s_axi ARADDR" *)  input  wire [5:0]  s_axi_araddr,
    (* X_INTERFACE_INFO = "xilinx.com:interface:aximm:1.0 s_axi ARPROT" *)  input  wire [2:0]  s_axi_arprot,
    (* X_INTERFACE_INFO = "xilinx.com:interface:aximm:1.0 s_axi ARVALID" *) input  wire        s_axi_arvalid,
    (* X_INTERFACE_INFO = "xilinx.com:interface:aximm:1.0 s_axi ARREADY" *) output wire        s_axi_arready,
    (* X_INTERFACE_INFO = "xilinx.com:interface:aximm:1.0 s_axi RDATA" *)   output wire [31:0] s_axi_rdata,
    (* X_INTERFACE_INFO = "xilinx.com:interface:aximm:1.0 s_axi RRESP" *)   output wire [1:0]  s_axi_rresp,
    (* X_INTERFACE_INFO = "xilinx.com:interface:aximm:1.0 s_axi RVALID" *)  output wire        s_axi_rvalid,
    (* X_INTERFACE_INFO = "xilinx.com:interface:aximm:1.0 s_axi RREADY" *)  input  wire        s_axi_rready,

    // AXI-Stream slave: DMA MM2S -> accelerator
    (* X_INTERFACE_INFO = "xilinx.com:interface:axis:1.0 s_axis TDATA" *)  input  wire [31:0] s_axis_tdata,
    (* X_INTERFACE_INFO = "xilinx.com:interface:axis:1.0 s_axis TKEEP" *)  input  wire [3:0]  s_axis_tkeep,
    (* X_INTERFACE_INFO = "xilinx.com:interface:axis:1.0 s_axis TVALID" *) input  wire        s_axis_tvalid,
    (* X_INTERFACE_INFO = "xilinx.com:interface:axis:1.0 s_axis TREADY" *) output wire        s_axis_tready,
    (* X_INTERFACE_INFO = "xilinx.com:interface:axis:1.0 s_axis TLAST" *)  input  wire        s_axis_tlast,

    // AXI-Stream master: accelerator -> DMA S2MM
    (* X_INTERFACE_INFO = "xilinx.com:interface:axis:1.0 m_axis TDATA" *)  output wire [31:0] m_axis_tdata,
    (* X_INTERFACE_INFO = "xilinx.com:interface:axis:1.0 m_axis TKEEP" *)  output wire [3:0]  m_axis_tkeep,
    (* X_INTERFACE_INFO = "xilinx.com:interface:axis:1.0 m_axis TVALID" *) output wire        m_axis_tvalid,
    (* X_INTERFACE_INFO = "xilinx.com:interface:axis:1.0 m_axis TREADY" *) input  wire        m_axis_tready,
    (* X_INTERFACE_INFO = "xilinx.com:interface:axis:1.0 m_axis TLAST" *)  output wire        m_axis_tlast
);
    localparam [31:0] VERSION = 32'h5352_5301;

    // ------------------------------------------------------------------ AXI4-Lite slave: AW and W may arrive in any order, one write at a time
    reg         aw_got, w_got, bvalid, rvalid;
    reg  [5:0]  aw_addr;
    reg  [31:0] w_data;
    reg  [3:0]  w_strb;
    reg  [31:0] rdata;

    assign s_axi_awready = !aw_got && !bvalid;
    assign s_axi_wready  = !w_got  && !bvalid;
    assign s_axi_bresp   = 2'b00;
    assign s_axi_bvalid  = bvalid;
    assign s_axi_arready = !rvalid;
    assign s_axi_rresp   = 2'b00;
    assign s_axi_rvalid  = rvalid;
    assign s_axi_rdata   = rdata;

    wire wr_fire = aw_got && w_got && !bvalid;               // both halves of a write are here: perform it now
    wire ar_fire = s_axi_arvalid && s_axi_arready;

    // ------------------------------------------------------------------ the accelerator
    reg         start_r, srst_r;                              // one-cycle pulses
    reg  [15:0] frame_w, frame_h;
    wire        core_busy, core_done;
    wire [31:0] core_cycles, in_beats, out_beats;
    wire [3:0]  core_flags;
    localparam  MAXH = 4096;                                  // H + 6 must fit the 16-bit row counters and sums of the core (audit 2026-10-27: 65,530+ wrapped)
    wire        size_ok  = (frame_w != 16'd0) && (frame_w <= MAXW - 6) && (frame_h != 16'd0) && (frame_h <= MAXH);
    wire        start_ok = start_r && !core_busy && size_ok;

    sr_pipe_core #(.MAXW(MAXW), .WDIR(WDIR)) core (
        .clk(aclk), .rst(!aresetn || srst_r), .start(start_ok), .lr_w(frame_w), .lr_h(frame_h),
        .busy(core_busy), .done(core_done), .cycles(core_cycles), .error_flags(core_flags), .in_beats(in_beats), .out_beats(out_beats),
        .s_axis_tdata(s_axis_tdata), .s_axis_tkeep(s_axis_tkeep), .s_axis_tvalid(s_axis_tvalid), .s_axis_tready(s_axis_tready), .s_axis_tlast(s_axis_tlast),
        .m_axis_tdata(m_axis_tdata), .m_axis_tvalid(m_axis_tvalid), .m_axis_tready(m_axis_tready), .m_axis_tlast(m_axis_tlast));
    assign m_axis_tkeep = 4'hF;

    // ------------------------------------------------------------------ sticky status
    reg         done_s;
    reg  [2:0]  err_code;
    wire        busy_st = core_busy || start_r || core_done;   // no cycle where busy is low and done not yet set
    always @(posedge aclk) begin
        if (!aresetn || srst_r) begin
            done_s <= 1'b0; err_code <= 3'd0;
        end else begin
            if (start_ok) begin done_s <= 1'b0; err_code <= 3'd0; end
            if (core_done) done_s <= 1'b1;
            if (err_code == 3'd0 && !start_ok) begin            // keep the first error
                if (start_r && !core_busy && !size_ok) err_code <= 3'd4;
                else if (core_flags[0])  err_code <= 3'd1;
                else if (core_flags[1])  err_code <= 3'd2;
                else if (core_flags[2])  err_code <= 3'd3;
                else if (core_flags[3])  err_code <= 3'd5;
            end
        end
    end

    // ------------------------------------------------------------------ write channel
    always @(posedge aclk) begin
        start_r <= 1'b0;
        srst_r  <= 1'b0;
        if (!aresetn) begin
            aw_got <= 1'b0; w_got <= 1'b0; bvalid <= 1'b0; frame_w <= 16'd0; frame_h <= 16'd0;
        end else begin
            if (s_axi_awvalid && s_axi_awready) begin aw_got <= 1'b1; aw_addr <= s_axi_awaddr; end
            if (s_axi_wvalid  && s_axi_wready)  begin w_got  <= 1'b1; w_data <= s_axi_wdata; w_strb <= s_axi_wstrb; end
            if (wr_fire) begin
                aw_got <= 1'b0; w_got <= 1'b0; bvalid <= 1'b1;
                if (aw_addr[5:2] == 4'd0 && w_strb[0]) begin
                    start_r <= w_data[0];
                    srst_r  <= w_data[1];
                end
                if (aw_addr[5:2] == 4'd2) begin
                    if (w_strb[0]) frame_w[7:0]  <= w_data[7:0];
                    if (w_strb[1]) frame_w[15:8] <= w_data[15:8];
                end
                if (aw_addr[5:2] == 4'd6) begin
                    if (w_strb[0]) frame_h[7:0]  <= w_data[7:0];
                    if (w_strb[1]) frame_h[15:8] <= w_data[15:8];
                end
            end
            if (bvalid && s_axi_bready) bvalid <= 1'b0;
        end
    end

    // ------------------------------------------------------------------ read channel (data is sampled when the address is accepted)
    always @(posedge aclk) begin
        if (!aresetn) begin
            rvalid <= 1'b0; rdata <= 32'd0;
        end else begin
            if (ar_fire) begin
                rvalid <= 1'b1;
                case (s_axi_araddr[5:2])
                    4'd0:    rdata <= 32'd0;
                    4'd1:    rdata <= {29'd0, (err_code != 3'd0), done_s, busy_st};
                    4'd2:    rdata <= {16'd0, frame_w};
                    4'd3:    rdata <= core_cycles;
                    4'd4:    rdata <= {29'd0, err_code};
                    4'd5:    rdata <= VERSION;
                    4'd6:    rdata <= {16'd0, frame_h};
                    4'd7:    rdata <= MAXW - 6;
                    4'd8:    rdata <= in_beats;
                    4'd9:    rdata <= out_beats;
                    default: rdata <= 32'd0;
                endcase
            end
            if (rvalid && s_axi_rready) rvalid <= 1'b0;
        end
    end

    wire unused = &{1'b0, s_axi_awprot, s_axi_arprot, w_strb[3:2], aw_addr[1:0]};
endmodule
