// Whole-frame super-resolution pipeline core (docs/ARCHITECTURE_PIPELINE.md).  Replaces the tiled sr_tile_core in branch `pipe`.
//
//   s_axis (32 bit) -> unpack -> 24-bit pixels of the padded frame (W+6) x (H+6) -> L1 -> FIFO -> L2 -> FIFO -> L3 -> FIFO -> L4 (+ anchor) -> pipe_out -> m_axis
//
// One frame per accepted `start` (the top only gives it while !busy and with a valid size; FRAME_W/H are sampled at start).
//   input : 3 (W+6)(H+6) bytes, replicate-padded LR frame, raster [y][x][c], little-endian beats; the last beat may carry 1-3 unused bytes;
//           TLAST expected on beat ceil(3 (W+6)(H+6) / 4) - 1.  s_axis_tready is low outside a frame (the DMA may be armed before start).
//   output: 12 W H bytes = 2W x 2H x 3 HR frame in raster order, TLAST on the last beat.  `done` = last output beat accepted.
// SHIFT1..4 / ANCHOR must equal network_params.vh (the testbench checks this).  error_flags (sticky until the next start or reset):
//   [0] TLAST before the last input beat  [1] last input beat without TLAST  [2] TKEEP != 4'hF  [3] internal (FIFO or anchor FIFO misuse; never expected)
module sr_pipe_core #(
    parameter SHIFT1 = 22,
    parameter SHIFT2 = 22,
    parameter SHIFT3 = 21,
    parameter SHIFT4 = 25,
    parameter ANCHOR = 1,
    parameter MAXW   = 1024,              // line-buffer depth: W + 6 <= MAXW
    parameter WDIR   = "hardware/rtl/weights/"
) (
    input  wire        clk,
    input  wire        rst,
    input  wire        start,
    input  wire [15:0] lr_w,
    input  wire [15:0] lr_h,
    output wire        busy,
    output wire        done,
    output reg  [31:0] cycles,
    output reg  [3:0]  error_flags,
    output reg  [31:0] in_beats,
    output wire [31:0] out_beats,
    input  wire [31:0] s_axis_tdata,
    input  wire [3:0]  s_axis_tkeep,
    input  wire        s_axis_tvalid,
    output wire        s_axis_tready,
    input  wire        s_axis_tlast,
    output wire [31:0] m_axis_tdata,
    output wire        m_axis_tvalid,
    input  wire        m_axis_tready,
    output wire        m_axis_tlast
);
    // ------------------------------------------------------------------ frame state: sizes and totals (computed in a few cycles after start)
    reg  [15:0] fw, fh;
    reg  [2:0]  prep;                    // 0 = idle or running; counts down after start, the frame runs when it reaches 1 -> 0
    reg         run_f;                   // frame running (from the end of prep until done)
    reg  [15:0] pw_a, ph_a, w_a, h_a;    // multiplier inputs (registered: DSP A/B registers)
    reg  [31:0] npix_p, nlr_p;           // (W+6)(H+6) and W*H
    reg  [31:0] npix, nbi, nbo;          // input pixels, input beats, output beats
    reg         stage_start;             // one-cycle frame start for the stages and pipe_out
    always @(posedge clk) begin
        pw_a <= fw + 16'd6; ph_a <= fh + 16'd6; w_a <= fw; h_a <= fh;
        npix_p <= pw_a * ph_a;
        nlr_p  <= w_a * h_a;
        stage_start <= 1'b0;
        if (rst) begin
            prep <= 3'd0; run_f <= 1'b0;
        end else if (start && !busy) begin
            fw <= lr_w; fh <= lr_h; prep <= 3'd5; run_f <= 1'b0;
        end else if (prep != 3'd0) begin
            prep <= prep - 3'd1;
            if (prep == 3'd1) begin
                npix <= npix_p;
                nbi  <= (3 * npix_p + 3) >> 2;
                nbo  <= 3 * nlr_p;
                run_f <= 1'b1; stage_start <= 1'b1;
            end
        end else if (done) run_f <= 1'b0;
    end
    assign busy = run_f || (prep != 3'd0);

    always @(posedge clk) begin
        if (rst) cycles <= 32'd0;
        else if (start && !busy) cycles <= 32'd1;
        else if (busy && !done) cycles <= cycles + 32'd1;
    end

    // ------------------------------------------------------------------ input: 32-bit beats -> 24-bit pixels
    reg  [55:0] ub;
    reg  [2:0]  un;                      // bytes in ub
    reg  [31:0] pcnt;                    // pixels sent to L1
    reg  [15:0] px, py;                  // padded-frame coordinates of the next pixel
    wire        l1_ready, anc_full;
    wire        pix_left = run_f && (pcnt != npix);
    wire        l1_valid = (un >= 3'd3) && pix_left && !anc_full;
    wire        ext      = l1_valid && l1_ready;
    wire [2:0]  un1      = ext ? un - 3'd3 : un;
    wire [55:0] ub1      = ext ? {24'd0, ub[55:24]} : ub;
    assign s_axis_tready = run_f && (in_beats != nbi) && (un1 <= 3'd3);
    wire        s_take   = s_axis_tvalid && s_axis_tready;
    wire        anc_push = ext && (px >= 16'd3) && (px < fw + 16'd3) && (py >= 16'd3) && (py < fh + 16'd3);

    wire        fstart   = start && !busy;   // accepted start: the frame state resets here (s_axis_tready is low until the end of prep)
    always @(posedge clk) begin
        if (rst || fstart) begin
            ub <= 56'd0; un <= 3'd0; pcnt <= 32'd0; px <= 16'd0; py <= 16'd0; in_beats <= 32'd0;
        end else begin
            ub <= s_take ? (ub1 | ({24'd0, s_axis_tdata} << (8 * un1))) : ub1;
            un <= un1 + (s_take ? 3'd4 : 3'd0);
            if (s_take) in_beats <= in_beats + 32'd1;
            if (ext) begin
                pcnt <= pcnt + 32'd1;
                if (px == fw + 16'd5) begin px <= 16'd0; py <= py + 16'd1; end else px <= px + 16'd1;
            end
            if (pcnt == npix && run_f) un <= 3'd0;       // drop the unused bytes of the last beat
        end
    end

    // ------------------------------------------------------------------ stages
    wire         s1_start, s2_start, s3_start, s4_start;
    wire         s1_ov, s2_ov, s3_ov, s4_ov;
    wire [127:0] s1_od, s2_od, s3_od, f1_d, f2_d, f3_d;
    wire [95:0]  s4_od;
    wire         f1_ok, f2_ok, f3_ok, o_ok, f1_v, f2_v, f3_v, s2_rdy, s3_rdy, s4_rdy;
    wire         f1_err, f2_err, f3_err, anc_err, anc_pop;
    wire [23:0]  anc_q;
    wire         nc1, nc2, nc3;

    pipe_stage #(.C_IN(3), .C_OUT(16), .K(3), .MODE(0), .SHIFT(SHIFT1), .MAXW(MAXW),
                 .W_FILE({WDIR, "wpipe_L1.mem"}), .B_FILE({WDIR, "bias_L1.mem"}), .M_FILE({WDIR, "mult_L1.mem"})) s1 (
        .clk(clk), .rst(rst), .start(stage_start), .in_w(fw + 16'd6), .in_h(fh + 16'd6),
        .in_valid(l1_valid), .in_data(ub[23:0]), .in_ready(l1_ready), .out_ok(f1_ok), .px_start(s1_start),
        .out_valid(s1_ov), .out_data(s1_od), .anc_pop(nc1), .anc_data(24'd0));
    pipe_fifo #(.W(128)) f1 (.clk(clk), .rst(rst || stage_start), .reserve(s1_start), .ok(f1_ok), .push(s1_ov), .din(s1_od),
        .out_valid(f1_v), .dout(f1_d), .out_ready(s2_rdy), .err(f1_err));

    pipe_stage #(.C_IN(16), .C_OUT(16), .K(3), .MODE(1), .SHIFT(SHIFT2), .MAXW(MAXW),
                 .W_FILE({WDIR, "wpipe_L2.mem"}), .B_FILE({WDIR, "bias_L2.mem"}), .M_FILE({WDIR, "mult_L2.mem"})) s2 (
        .clk(clk), .rst(rst), .start(stage_start), .in_w(fw + 16'd4), .in_h(fh + 16'd4),
        .in_valid(f1_v), .in_data(f1_d), .in_ready(s2_rdy), .out_ok(f2_ok), .px_start(s2_start),
        .out_valid(s2_ov), .out_data(s2_od), .anc_pop(nc2), .anc_data(24'd0));
    pipe_fifo #(.W(128)) f2 (.clk(clk), .rst(rst || stage_start), .reserve(s2_start), .ok(f2_ok), .push(s2_ov), .din(s2_od),
        .out_valid(f2_v), .dout(f2_d), .out_ready(s3_rdy), .err(f2_err));

    pipe_stage #(.C_IN(16), .C_OUT(16), .K(1), .MODE(0), .SHIFT(SHIFT3), .MAXW(MAXW),
                 .W_FILE({WDIR, "wpipe_L3.mem"}), .B_FILE({WDIR, "bias_L3.mem"}), .M_FILE({WDIR, "mult_L3.mem"})) s3 (
        .clk(clk), .rst(rst), .start(stage_start), .in_w(fw + 16'd2), .in_h(fh + 16'd2),
        .in_valid(f2_v), .in_data(f2_d), .in_ready(s3_rdy), .out_ok(f3_ok), .px_start(s3_start),
        .out_valid(s3_ov), .out_data(s3_od), .anc_pop(nc3), .anc_data(24'd0));
    pipe_fifo #(.W(128)) f3 (.clk(clk), .rst(rst || stage_start), .reserve(s3_start), .ok(f3_ok), .push(s3_ov), .din(s3_od),
        .out_valid(f3_v), .dout(f3_d), .out_ready(s4_rdy), .err(f3_err));

    pipe_stage #(.C_IN(16), .C_OUT(12), .K(3), .MODE(2), .SHIFT(SHIFT4), .ANCHOR(ANCHOR), .MAXW(MAXW),
                 .W_FILE({WDIR, "wpipe_L4.mem"}), .B_FILE({WDIR, "bias_L4.mem"}), .M_FILE({WDIR, "mult_L4.mem"})) s4 (
        .clk(clk), .rst(rst), .start(stage_start), .in_w(fw + 16'd2), .in_h(fh + 16'd2),
        .in_valid(f3_v), .in_data(f3_d), .in_ready(s4_rdy), .out_ok(o_ok), .px_start(s4_start),
        .out_valid(s4_ov), .out_data(s4_od), .anc_pop(anc_pop), .anc_data(anc_q));

    anchor_fifo u_anc (.clk(clk), .rst(rst || stage_start), .push(anc_push && ANCHOR != 0), .din(ub[23:0]), .pop(anc_pop),
        .dout(anc_q), .full(anc_full), .err(anc_err));

    pipe_out #(.MAXW(MAXW)) u_out (
        .clk(clk), .rst(rst), .start(stage_start), .lr_w(fw), .n_beats(nbo),
        .px_start(s4_start), .ok(o_ok), .in_valid(s4_ov), .in_data(s4_od),
        .m_axis_tdata(m_axis_tdata), .m_axis_tvalid(m_axis_tvalid), .m_axis_tready(m_axis_tready), .m_axis_tlast(m_axis_tlast),
        .done(done), .beats(out_beats));

    // ------------------------------------------------------------------ error flags
    always @(posedge clk) begin
        if (rst || fstart) error_flags <= 4'd0;
        else begin
            if (s_take) begin
                if (s_axis_tlast && in_beats != nbi - 1) error_flags[0] <= 1'b1;
                if (!s_axis_tlast && in_beats == nbi - 1) error_flags[1] <= 1'b1;
                if (s_axis_tkeep != 4'hF) error_flags[2] <= 1'b1;
            end
            if (f1_err || f2_err || f3_err || anc_err) error_flags[3] <= 1'b1;
        end
    end

    wire unused = &{1'b0, nc1, nc2, nc3};
endmodule
