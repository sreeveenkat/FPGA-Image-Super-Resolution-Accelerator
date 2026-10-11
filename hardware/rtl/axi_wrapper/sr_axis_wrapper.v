// AXI-Stream wrapper around sr_tile_core (M6 prep).  32-bit streams for the AXI DMA, byte streams for the core.
//
//   DMA MM2S --s_axis (32 bit)--> unpack (little-endian: first byte = bits 7:0) --bytes--> sr_tile_core --bytes--> pack --m_axis (32 bit)--> DMA S2MM
//
// One tile per `start`:  (HC+6)^2*3 bytes in = NWI words (14,700 B = 3,675 words for HC = 64),  (2HC)^2*3 bytes out = NWO words (49,152 B = 12,288 words).
// HC must be even (the byte counts must be multiples of 4; checked in simulation).
//
// Behaviour
//   * s_axis_tready is high only while the core is in its load phase and a word can be unpacked without loss: words sent before `start` just wait (back-pressure).
//     The DMA may therefore be armed before `start` is given.
//   * m_axis: tvalid stays high with stable tdata/tlast until tready (AXI rule); TLAST on the last word of the tile, TKEEP = 4'hF.
//   * `done`: one-cycle pulse, the cycle after the last output word was accepted by the DMA.  `busy` is high from `start` until that last word is accepted.
//   * `start` is ignored (and error bit 2 is set) while busy.  A start that is accepted clears the error flags.
//   * error_flags (sticky until the next accepted start or reset): [0] TLAST on an input word that is not the last one, [1] last input word without TLAST,
//     [2] start while busy.  Errors do not stop the tile: the data is still processed (the driver decides what to do).
//   * Reset: aresetn (active low, AXI convention) OR soft_rst (active high, from the CONTROL register) - synchronous, ONE cycle is enough.
//   * `cycles` = core cycles from start to its last output byte (same counter as sr_tile_core).
module sr_axis_wrapper #(
    parameter HC   = 64,
    parameter WDIR = "hardware/rtl/weights/",
    parameter NWI  = (HC + 6) * (HC + 6) * 3 / 4,    // input words per tile (do not override)
    parameter NWO  = 3 * HC * HC                     // output words per tile (do not override)
) (
    input  wire        aclk,
    input  wire        aresetn,
    input  wire        soft_rst,
    input  wire        start,
    output wire        busy,
    output reg         done,
    output wire [31:0] cycles,
    output reg  [2:0]  error_flags,
    // slave stream: DMA -> core
    input  wire [31:0] s_axis_tdata,
    input  wire        s_axis_tvalid,
    output wire        s_axis_tready,
    input  wire        s_axis_tlast,
    // master stream: core -> DMA
    output wire [31:0] m_axis_tdata,
    output wire        m_axis_tvalid,
    input  wire        m_axis_tready,
    output wire        m_axis_tlast,
    output wire [3:0]  m_axis_tkeep
);
    // simulation-only parameter check
    // synthesis translate_off
    initial if (HC % 2 != 0) begin $display("sr_axis_wrapper: HC must be even"); $finish; end
    // synthesis translate_on

    wire rst = !aresetn || soft_rst;

    // ------------------------------------------------------------------ core
    wire        core_busy, core_done, core_in_ready, core_out_valid, core_out_last, core_out_ready;
    wire [7:0]  core_out_data;
    reg         core_in_valid_r;                // = `have`
    wire [7:0]  core_in_data;

    wire        start_ok = start && !busy;
    wire        start_core = start_ok;

    sr_tile_core #(.HC(HC), .WDIR(WDIR)) core (
        .clk(aclk), .rst(rst), .start(start_core), .busy(core_busy), .done(core_done),
        .in_valid(core_in_valid_r), .in_data(core_in_data), .in_ready(core_in_ready),
        .out_valid(core_out_valid), .out_data(core_out_data), .out_ready(core_out_ready), .out_last(core_out_last),
        .cycles(cycles));

    // ------------------------------------------------------------------ input: word -> 4 bytes
    reg [31:0] iw;
    reg [1:0]  ib;                               // byte of the word being sent to the core
    reg [15:0] wcnt;                             // index of the next input word of this tile
    assign core_in_data  = iw[8*ib +: 8];
    // a new word may be taken when the register is empty or its last byte is being consumed in this very cycle
    assign s_axis_tready = core_in_ready && (!core_in_valid_r || ib == 2'd3);
    wire   s_take = s_axis_tvalid && s_axis_tready;

    always @(posedge aclk) begin
        if (rst) begin
            core_in_valid_r <= 1'b0; ib <= 2'd0; wcnt <= 16'd0;
        end else begin
            if (start_ok) wcnt <= 16'd0;
            if (core_in_valid_r && core_in_ready) begin
                ib <= ib + 2'd1;
                if (ib == 2'd3) core_in_valid_r <= 1'b0;
            end
            if (s_take) begin
                iw <= s_axis_tdata;
                core_in_valid_r <= 1'b1;
                ib <= 2'd0;
                wcnt <= (wcnt == NWI - 1) ? 16'd0 : wcnt + 16'd1;
            end
        end
    end

    // ------------------------------------------------------------------ output: 4 bytes -> word
    reg [31:0] ow;
    reg [1:0]  ob;
    reg        ov, olast;
    assign core_out_ready = !ov || m_axis_tready;
    assign m_axis_tdata  = ow;
    assign m_axis_tvalid = ov;
    assign m_axis_tlast  = ov && olast;
    assign m_axis_tkeep  = 4'hF;
    wire   m_take = ov && m_axis_tready;
    wire   o_take = core_out_valid && core_out_ready;

    always @(posedge aclk) begin
        done <= 1'b0;
        if (rst) begin
            ov <= 1'b0; ob <= 2'd0; olast <= 1'b0;
        end else begin
            if (m_take) begin
                ov <= 1'b0;
                if (olast) done <= 1'b1;
            end
            if (o_take) begin
                ow[8*ob +: 8] <= core_out_data;
                ob <= ob + 2'd1;
                if (ob == 2'd3) begin ov <= 1'b1; olast <= core_out_last; end
            end
        end
    end

    assign busy = core_busy || ov;

    // ------------------------------------------------------------------ error flags
    always @(posedge aclk) begin
        if (rst) error_flags <= 3'b000;
        else begin
            if (start_ok) error_flags <= 3'b000;
            if (start && busy) error_flags[2] <= 1'b1;
            if (s_take) begin
                if (s_axis_tlast && wcnt != NWI - 1) error_flags[0] <= 1'b1;
                if (!s_axis_tlast && wcnt == NWI - 1) error_flags[1] <= 1'b1;
            end
        end
    end

    wire unused = &{1'b0, core_done};
endmodule
