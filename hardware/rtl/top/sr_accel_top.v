// Top module of the super-resolution accelerator (M6): AXI4-Lite control + AXI-Stream data around sr_tile_core.  This is the module the Vivado
// block design uses (as a "module reference").
//
//   ARM --AXI4-Lite--> register block --start/soft reset/status--> sr_axis_wrapper --bytes--> sr_tile_core
//   DMA MM2S --s_axis (32 bit)--> sr_axis_wrapper ... sr_tile_core ... sr_axis_wrapper --m_axis (32 bit)--> DMA S2MM
//
// Register map (byte offsets, 32-bit registers; the C header and docs must agree with this table):
//   0x00 CONTROL    W: bit0 start (one-cycle pulse; ignored while busy; an accepted start also clears sticky DONE and ERROR),
//                      bit1 soft reset (one-cycle pulse, resets the core and wrapper and clears DONE/ERROR).  Reads 0.
//                      Only bits written with wstrb[0] set take effect.
//   0x04 STATUS     R: bit0 busy, bit1 done (sticky), bit2 error (sticky, = ERROR_CODE != 0)
//   0x08 TILE_SIZE  R: HC (core tile edge in input pixels, 64)
//   0x0C CYCLES     R: core cycles of the last/current tile (start to last output byte)
//   0x10 ERROR_CODE R: 0 none | 1 s_axis_tlast on a beat that is not the last input beat | 2 last input beat without tlast | 3 s_axis_tkeep != 4'hF
//                      (the FIRST error of a tile is kept).  Errors are only reported; the tile is still processed.  Recovery = soft reset.
//   0x14 VERSION    R: 32'h5352_3201  (R3q; 0x53520602 = deployed R0 build, 0601 = the first board version, without the debug registers below)
//   Debug registers (read-only, added 2026-10-11 to find the board's first-tile stream errors; they do not change the data path):
//   0x18 DBG_IN_BEATS   input beats accepted since the last accepted start
//   0x1C DBG_TLAST_AT   1 + index (since start) of the first accepted input beat with tlast; 0 = none yet
//   0x20 DBG_START2BEAT bits 30:0 cycles from the accepted start to the first accepted input beat (saturating); bit 31 = s_axis_tvalid was high in the start cycle
//   0x24 DBG_PRE_BEATS  input beats accepted while no tile was running, since aresetn (must stay 0)
//   0x28 DBG_STARTS     bits 15:0 accepted starts, bits 31:16 ignored starts (written while busy), since aresetn
//   0x2C DBG_ERR_BEATS  DBG_IN_BEATS when the first error of the tile was recorded (cleared with ERROR_CODE)
//   0x30 DBG_ERR_CYCLES CYCLES when the first error of the tile was recorded (cleared with ERROR_CODE)
//   other addresses read 0, writes to them are accepted and ignored (OKAY response).
//
// Differences to the first sketch, on purpose: STATUS.busy is the wrapper's busy (core busy OR the last output word not yet taken by the DMA) and also
// high in the cycle after a CONTROL.start write (so a driver that polls right after the write cannot miss it) and in the cycle of the done pulse; STATUS.done is set when the LAST OUTPUT
// BEAT was accepted by the DMA (not when the core computed it), so "done" means the data is in DDR-bound stream.
//
// Streams: one 32-bit beat = 4 bytes, little endian (first byte = tdata[7:0]).  A tile is (HC+6)^2*3 bytes in (3,675 beats at HC=64) and (2HC)^2*3 bytes out
// (12,288 beats).  s_axis_tready stays low until CONTROL.start has been written (the DMA may be armed first).  HC must be even so that the input byte count
// is a multiple of 4 (the output count always is); an odd HC is NOT accepted: there is deliberately no elaboration-time check here (an unresolved dummy module blocks Vivado's module reference). It is enforced by tb_sr_accel_top.v (fails at time 0) and synth_sr_accel_top.tcl (checked before synthesis); sr_axis_wrapper.v also stops a simulation.
//
// WDIR default is an ABSOLUTE path: it ties the build to this machine (the .mem files must be found by $readmemh during synthesis).  Change it, or override
// it in the block design, when the project moves.  The derived parameters of the core are deliberately not exposed here.
module sr_accel_top #(
    parameter HC   = 64,
    parameter WDIR = "/home/sreevenkat/Desktop/venkat/sem_project_all/hardware/rtl/weights/"
) (
    (* X_INTERFACE_INFO = "xilinx.com:signal:clock:1.0 aclk CLK" *)
    (* X_INTERFACE_PARAMETER = "ASSOCIATED_BUSIF s_axi:s_axis:m_axis, ASSOCIATED_RESET aresetn, FREQ_HZ 100000000" *)
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
    localparam [31:0] VERSION = 32'h5352_3201;

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
    wire        wrap_busy, wrap_done;
    wire [31:0] wrap_cycles;
    wire [2:0]  wrap_flags;

    sr_axis_wrapper #(.HC(HC), .WDIR(WDIR)) wrap (
        .aclk(aclk), .aresetn(aresetn), .soft_rst(srst_r), .start(start_r), .busy(wrap_busy), .done(wrap_done), .cycles(wrap_cycles),
        .error_flags(wrap_flags),
        .s_axis_tdata(s_axis_tdata), .s_axis_tvalid(s_axis_tvalid), .s_axis_tready(s_axis_tready), .s_axis_tlast(s_axis_tlast),
        .m_axis_tdata(m_axis_tdata), .m_axis_tvalid(m_axis_tvalid), .m_axis_tready(m_axis_tready), .m_axis_tlast(m_axis_tlast),
        .m_axis_tkeep(m_axis_tkeep));

    // ------------------------------------------------------------------ sticky status
    reg         done_s;
    reg  [1:0]  err_code;
    wire        keep_bad = s_axis_tvalid && s_axis_tready && (s_axis_tkeep != 4'hF);
    wire        busy_st  = wrap_busy || start_r || wrap_done;   // no cycle where busy is low and done not yet set
    wire        start_ok = start_r && !wrap_busy;             // identical condition to the wrapper's own start gate

    always @(posedge aclk) begin
        if (!aresetn || srst_r) begin
            done_s <= 1'b0; err_code <= 2'd0;
        end else begin
            if (start_ok) begin done_s <= 1'b0; err_code <= 2'd0; end
            if (wrap_done) done_s <= 1'b1;
            if (err_code == 2'd0) begin                        // keep the first error
                if (wrap_flags[0])      err_code <= 2'd1;
                else if (wrap_flags[1]) err_code <= 2'd2;
                else if (keep_bad)      err_code <= 2'd3;
            end
        end
    end

    // ------------------------------------------------------------------ debug counters (observation only)
    wire        s_take = s_axis_tvalid && s_axis_tready;
    reg         in_tile_d, first_seen;
    reg  [31:0] dbg_in_beats, dbg_tlast_at, dbg_s2b, dbg_pre, dbg_err_beats, dbg_err_cyc;
    reg  [15:0] dbg_starts_ok, dbg_starts_ign;
    wire        err_now = (err_code == 2'd0) && (wrap_flags[0] || wrap_flags[1] || keep_bad);   // the cycle the first error is recorded
    always @(posedge aclk) begin
        if (!aresetn) begin
            in_tile_d <= 1'b0; first_seen <= 1'b0; dbg_in_beats <= 0; dbg_tlast_at <= 0; dbg_s2b <= 0; dbg_pre <= 0;
            dbg_err_beats <= 0; dbg_err_cyc <= 0; dbg_starts_ok <= 0; dbg_starts_ign <= 0;
        end else begin
            if (start_ok) begin
                in_tile_d <= 1'b1; first_seen <= 1'b0; dbg_in_beats <= 0; dbg_tlast_at <= 0; dbg_s2b <= {s_axis_tvalid, 31'd0};
                dbg_err_beats <= 0; dbg_err_cyc <= 0; dbg_starts_ok <= dbg_starts_ok + 1'b1;
            end else begin
                if (srst_r || wrap_done) in_tile_d <= 1'b0;
                if (srst_r) begin dbg_err_beats <= 0; dbg_err_cyc <= 0; end
                if (start_r) dbg_starts_ign <= dbg_starts_ign + 1'b1;
                if (in_tile_d && !first_seen && !s_take && dbg_s2b[30:0] != 31'h7FFF_FFFF) dbg_s2b[30:0] <= dbg_s2b[30:0] + 1'b1;
                if (s_take) begin
                    if (in_tile_d) begin
                        dbg_in_beats <= dbg_in_beats + 1;
                        first_seen <= 1'b1;
                        if (s_axis_tlast && dbg_tlast_at == 0) dbg_tlast_at <= dbg_in_beats + 1;
                    end else dbg_pre <= dbg_pre + 1;
                end
                if (err_now && !srst_r) begin dbg_err_beats <= dbg_in_beats + (s_take ? 1 : 0); dbg_err_cyc <= wrap_cycles; end
            end
        end
    end

    // ------------------------------------------------------------------ write channel
    always @(posedge aclk) begin
        start_r <= 1'b0;
        srst_r  <= 1'b0;
        if (!aresetn) begin
            aw_got <= 1'b0; w_got <= 1'b0; bvalid <= 1'b0;
        end else begin
            if (s_axi_awvalid && s_axi_awready) begin aw_got <= 1'b1; aw_addr <= s_axi_awaddr; end
            if (s_axi_wvalid  && s_axi_wready)  begin w_got  <= 1'b1; w_data <= s_axi_wdata; w_strb <= s_axi_wstrb; end
            if (wr_fire) begin
                aw_got <= 1'b0; w_got <= 1'b0; bvalid <= 1'b1;
                if (aw_addr[5:2] == 4'd0 && w_strb[0]) begin
                    start_r <= w_data[0];
                    srst_r  <= w_data[1];
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
                    4'd1:    rdata <= {29'd0, (err_code != 2'd0), done_s, busy_st};
                    4'd2:    rdata <= HC;
                    4'd3:    rdata <= wrap_cycles;
                    4'd4:    rdata <= {30'd0, err_code};
                    4'd5:    rdata <= VERSION;
                    4'd6:    rdata <= dbg_in_beats;
                    4'd7:    rdata <= dbg_tlast_at;
                    4'd8:    rdata <= dbg_s2b;
                    4'd9:    rdata <= dbg_pre;
                    4'd10:   rdata <= {dbg_starts_ign, dbg_starts_ok};
                    4'd11:   rdata <= dbg_err_beats;
                    4'd12:   rdata <= dbg_err_cyc;
                    default: rdata <= 32'd0;
                endcase
            end
            if (rvalid && s_axi_rready) rvalid <= 1'b0;
        end
    end

    wire unused = &{1'b0, s_axi_awprot, s_axi_arprot, w_strb[3:1], aw_addr[1:0]};
endmodule
