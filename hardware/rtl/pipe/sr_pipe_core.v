// Whole-frame super-resolution pipeline core (docs/ARCHITECTURE_PIPELINE.md).  Replaces the tiled sr_tile_core in branch `pipe`.
//
//   s_axis (32 bit) -> unpack -> 24-bit pixels of the padded frame (W+6) x (H+6) -> L1 -> FIFO -> L2 -> FIFO -> L3 -> FIFO -> L4 (+ anchor) -> pipe_out -> m_axis
//
// One frame per accepted `start` (the top only gives it while !busy and with a valid size; FRAME_W/H and pad_en are sampled at start).
//   input, pad_en = 0: 3 (W+6)(H+6) bytes, replicate-padded LR frame (or a real-neighbour tile), raster [y][x][c], little-endian beats; the last
//           beat may carry 1-3 unused bytes; TLAST expected on beat ceil(3 (W+6)(H+6) / 4) - 1.
//   input, pad_en = 1 (branch pipe3): 3 W H bytes, the RAW LR frame; TLAST on beat ceil(3 W H / 4) - 1.  The core pads it itself (replicate, 3 px):
//           a 2-row buffer (raw row r in half r % 2) feeds L1 with exactly the stream that pad_en = 0 would have received, so the output is the same.
//           The ARM padding step (3.3 ms per 960x540 frame on the board) disappears.
//   s_axis_tready is low outside a frame (the DMA may be armed before start).
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
    parameter WDIR   = "hardware/rtl/weights/",
    parameter NS     = 6,                 // slots per LR pixel in every stage (16 = the original `pipe` design, 8 = v2, 6 = pipe4)
    parameter PACK   = 1,                 // pipe2p: two lanes per DSP48 where trees share activations (L1, L3, L4 at NS = 8; L4 at NS = 16); 0 = branch pipe2
    parameter NDSP4  = (NS == 8) ? 98 : (1 << 20),  // pipe2: L4 lanes on DSPs (L1-L3 all DSP); 220 DSP - 16 requantizer DSP - 2 core - 104 L1-L3 lanes
    parameter NDSP24 = (NS == 6) ? 76 : (1 << 20)   // pipe4: L4 packed pairs on DSP48s (the other 68 pairs = 136 LUT multipliers); see ARCHITECTURE_PIPELINE_V4.md
) (
    input  wire        clk,
    input  wire        rst,
    input  wire        start,
    input  wire [15:0] lr_w,
    input  wire [15:0] lr_h,
    input  wire        pad_en,           // pipe3: 1 = raw W x H input, padded in the PL
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
    reg         pe;                      // pipe3: PL padding for this frame
    reg  [15:0] fw3, fh3, fw5, rw1, rh1; // pipe3: registered fw+3, fh+3, fw+5, W-1, H-1 (constant during a frame; timing, see the anchor push)
    reg  [2:0]  prep;                    // 0 = idle or running; counts down after start, the frame runs when it reaches 1 -> 0
    reg         run_f;                   // frame running (from the end of prep until done)
    reg  [15:0] pw_a, ph_a, w_a, h_a;    // multiplier inputs (registered: DSP A/B registers)
    reg  [15:0] sw6, sh6, sw4, sh4, sw2, sh2;   // stage frame sizes, registered (pipe2 timing fix: fw + 2 feeding s3's column compare was the
                                                 // critical path, WNS +0.035 ns); fw/fh are fixed from the accepted start, the stages start 5 cycles later
    reg  [31:0] npix_p, nlr_p;           // (W+6)(H+6) and W*H
    reg  [31:0] npix, nbi, nbo;          // L1 input pixels (padded frame), input beats, output beats
    reg  [31:0] nu;                      // pipe3: pixels taken from the unpacker (= npix, or W*H with PL padding)
    reg         stage_start;             // one-cycle frame start for the stages and pipe_out
    always @(posedge clk) begin
        pw_a <= fw + 16'd6; ph_a <= fh + 16'd6; w_a <= fw; h_a <= fh;
        sw6 <= fw + 16'd6; sh6 <= fh + 16'd6; sw4 <= fw + 16'd4; sh4 <= fh + 16'd4; sw2 <= fw + 16'd2; sh2 <= fh + 16'd2;
        fw3 <= fw + 16'd3; fh3 <= fh + 16'd3; fw5 <= fw + 16'd5; rw1 <= fw - 16'd1; rh1 <= fh - 16'd1;
        npix_p <= pw_a * ph_a;
        nlr_p  <= w_a * h_a;
        stage_start <= 1'b0;
        if (rst) begin
            prep <= 3'd0; run_f <= 1'b0;
        end else if (start && !busy) begin
            fw <= lr_w; fh <= lr_h; pe <= pad_en; prep <= 3'd5; run_f <= 1'b0;
        end else if (prep != 3'd0) begin
            prep <= prep - 3'd1;
            if (prep == 3'd1) begin
                npix <= npix_p;
                nu   <= pe ? nlr_p : npix_p;
                nbi  <= pe ? (3 * nlr_p + 3) >> 2 : (3 * npix_p + 3) >> 2;
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
    reg  [31:0] ucnt;                    // pipe3: pixels taken from the unpacker (= pcnt without PL padding)
    reg         u_left;                  // pipe3: = run_f && ucnt != nu, registered (timing)
    reg  [15:0] px, py;                  // padded-frame coordinates of the next pixel
    reg         pix_left;                // = run_f && pcnt != npix, registered (pipe3 timing: was a 32-bit compare in front of the anchor FIFO enable)
    reg         xin, yin;                // = px in [3, W+3) and py in [3, H+3), registered (pipe3 timing: were two 16-bit compares, same path)
    wire        l1_ready, anc_full;
    wire        pv;                      // pipe3: padded pixel ready from the 2-row buffer
    wire [23:0] pd;
    wire        u_avail  = un >= 3'd3;
    wire        l1_valid = (pe ? pv : u_avail) && pix_left && !anc_full;
    wire [23:0] l1_data  = pe ? pd : ub[23:0];
    wire        ext      = l1_valid && l1_ready;
    wire        wr_take;                 // pipe3: raw pixel written into the row buffer
    wire        u_take   = pe ? wr_take : ext;
    wire [2:0]  un1      = u_take ? un - 3'd3 : un;
    wire [55:0] ub1      = u_take ? {24'd0, ub[55:24]} : ub;
    assign s_axis_tready = run_f && (in_beats != nbi) && (un1 <= 3'd3);
    wire        s_take   = s_axis_tvalid && s_axis_tready;
    wire        anc_push = ext && xin && yin;

    wire        fstart   = start && !busy;   // accepted start: the frame state resets here (s_axis_tready is low until the end of prep)
    always @(posedge clk) begin
        if (rst || fstart) begin
            ub <= 56'd0; un <= 3'd0; pcnt <= 32'd0; ucnt <= 32'd0; px <= 16'd0; py <= 16'd0; in_beats <= 32'd0;
            pix_left <= 1'b0; xin <= 1'b0; yin <= 1'b0; u_left <= 1'b0;
        end else begin
            ub <= s_take ? (ub1 | ({24'd0, s_axis_tdata} << (8 * un1))) : ub1;
            un <= un1 + (s_take ? 3'd4 : 3'd0);
            if (s_take) in_beats <= in_beats + 32'd1;
            if (u_take) begin ucnt <= ucnt + 32'd1; u_left <= (ucnt + 32'd1 != nu); end
            if (prep == 3'd1) begin pix_left <= 1'b1; u_left <= 1'b1; end   // run_f rises with them; npix >= 49 and W*H >= 1 are never 0
            if (ext) begin
                pcnt <= pcnt + 32'd1;
                pix_left <= (pcnt + 32'd1 != npix);
                if (px == fw5) begin
                    px <= 16'd0; py <= py + 16'd1; xin <= 1'b0;
                    if (py + 16'd1 == 16'd3) yin <= 1'b1;
                    if (py + 16'd1 == fh3)   yin <= 1'b0;
                end else begin
                    px <= px + 16'd1;
                    if (px + 16'd1 == 16'd3) xin <= 1'b1;
                    if (px + 16'd1 == fw3)   xin <= 1'b0;
                end
            end
            if (done) begin pix_left <= 1'b0; u_left <= 1'b0; end
            if (!u_left && run_f) un <= 3'd0;            // drop the unused bytes of the last beat (u_left = ucnt != nu)
        end
    end

    // ------------------------------------------------------------------ pipe3: PL replicate padding (pad_en = 1)
    // Writer: raw row r (r = 0..H-1) goes into half r % 2 of a 2 x MAXW x 24-bit RAM.  It may write row r once the reader has moved on to raw row
    // r - 1 or later (so half r % 2 is free).  Reader: padded row py (0..H+5) reads raw row clamp(py - 3, 0, H - 1), padded column px reads raw column
    // clamp(px - 3, 0, W - 1); a row is read only when it is complete.  Reads have one cycle latency; a 2-entry queue in front of L1 holds the data.
    localparam AW = $clog2(MAXW);
    reg  [23:0] rb [0:(2 << AW) - 1];   // 2 x 2^AW words (address {row % 2, column})
    reg  [AW-1:0] wx, rx;
    reg  [15:0] wrow;                    // completed raw rows (= the row being written)
    reg  [15:0] rrow;                    // raw row of the padded row being read
    reg  [15:0] qx, qy;                  // padded coordinates of the next read
    reg  [31:0] rcnt;                    // reads issued
    reg         rd_left;                 // = rcnt != npix, registered (timing)
    reg  [1:0]  ahead;                   // = wrow - rrow (0..2), kept as a counter so the two permissions below are 2-bit tests (timing: the 16-bit
                                         // compares rrow + 1 >= wrow / wrow > rrow fed the unpacker in the same cycle, WNS -0.770 ns at 142.86 MHz)
    reg         rd_v;                    // a read was issued last cycle
    reg  [23:0] rq, q0, q1;
    reg  [1:0]  qn;                      // entries in the queue
    // writer may write row wrow (half wrow % 2) when the reader is on row wrow - 1 or later: wrow - rrow <= 1 (also covers wrow < 2)
    // reader may read row rrow when it is complete: wrow > rrow
    assign wr_take = pe && run_f && u_avail && u_left && (ahead <= 2'd1);
    wire   wr_eol  = wr_take && ({{(16-AW){1'b0}}, wx} == rw1);   // writer completes a row
    wire   rd_go   = pe && run_f && rd_left && (ahead != 2'd0) && ({1'b0, qn} + {2'b0, rd_v} < 3'd2);
    wire   rd_nxr  = rd_go && (qx == fw5) && (qy >= 16'd3) && (rrow != rh1);   // reader moves to the next raw row
    wire   q_pop   = pe && ext;
    assign pv = qn != 2'd0;
    assign pd = q0;
    always @(posedge clk) begin
        if (wr_take) rb[{wrow[0], wx}] <= ub[23:0];
        rq <= rb[{rrow[0], rx}];
    end
    always @(posedge clk) begin
        if (rst || fstart) begin
            wx <= 0; rx <= 0; wrow <= 16'd0; rrow <= 16'd0; qx <= 16'd0; qy <= 16'd0; rcnt <= 32'd0; rd_v <= 1'b0; qn <= 2'd0;
            rd_left <= 1'b0; ahead <= 2'd0;
        end else begin
            if (prep == 3'd1) rd_left <= 1'b1;
            if (wr_take) begin
                if (wr_eol) begin wx <= 0; wrow <= wrow + 16'd1; end else wx <= wx + 1'b1;
            end
            ahead <= ahead + {1'b0, wr_eol} - {1'b0, rd_nxr};
            rd_v <= rd_go;
            if (rd_go) begin
                rcnt <= rcnt + 32'd1;
                rd_left <= (rcnt + 32'd1 != npix);
                if (qx == fw5) begin
                    qx <= 16'd0; rx <= 0; qy <= qy + 16'd1;
                    if (rd_nxr) rrow <= rrow + 16'd1;
                end else begin
                    qx <= qx + 16'd1;
                    if (qx >= 16'd3 && {{(16-AW){1'b0}}, rx} != rw1) rx <= rx + 1'b1;
                end
            end
            // queue: push the RAM data one cycle after the read, pop when L1 takes a pixel
            case ({rd_v, q_pop})
                2'b10: begin if (qn == 2'd0) q0 <= rq; else q1 <= rq; qn <= qn + 2'd1; end
                2'b01: begin q0 <= q1; qn <= qn - 2'd1; end
                2'b11: begin if (qn == 2'd1) q0 <= rq; else begin q0 <= q1; q1 <= rq; end end
                default: ;
            endcase
        end
    end

    // ------------------------------------------------------------------ stages
    localparam WP = (NS == 16) ? "/wpipe_" : (NS == 8) ? "wpipe8_" : "wpipe6_";  // weight ROM layout (export_pipe.py); same length on purpose: a shorter string would be
                                                         // NUL-padded inside the file name (WDIR ends in "/", so "//" is harmless)
    wire         s1_start, s2_start, s3_start, s4_start;
    wire         s1_ov, s2_ov, s3_ov, s4_ov;
    wire [127:0] s1_od, s2_od, s3_od, f1_d, f2_d, f3_d;
    wire [95:0]  s4_od;
    wire         f1_ok, f2_ok, f3_ok, o_ok, f1_v, f2_v, f3_v, s2_rdy, s3_rdy, s4_rdy;
    wire         f1_err, f2_err, f3_err, anc_err, anc_pop;
    wire [23:0]  anc_q;
    wire         nc1, nc2, nc3;

    pipe_stage #(.C_IN(3), .C_OUT(16), .K(3), .MODE(0), .SHIFT(SHIFT1), .MAXW(MAXW),
                 .NS(NS), .PACK(PACK), .W_FILE({WDIR, WP, "L1.mem"}), .B_FILE({WDIR, "bias_L1.mem"}), .M_FILE({WDIR, "mult_L1.mem"})) s1 (
        .clk(clk), .rst(rst), .start(stage_start), .in_w(sw6), .in_h(sh6),
        .in_valid(l1_valid), .in_data(l1_data), .in_ready(l1_ready), .out_ok(f1_ok), .px_start(s1_start),
        .out_valid(s1_ov), .out_data(s1_od), .anc_pop(nc1), .anc_data(24'd0));
    pipe_fifo #(.W(128)) f1 (.clk(clk), .rst(rst || stage_start), .reserve(s1_start), .ok(f1_ok), .push(s1_ov), .din(s1_od),
        .out_valid(f1_v), .dout(f1_d), .out_ready(s2_rdy), .err(f1_err));

    pipe_stage #(.C_IN(16), .C_OUT(16), .K(3), .MODE(1), .SHIFT(SHIFT2), .MAXW(MAXW),
                 .NS(NS), .W_FILE({WDIR, WP, "L2.mem"}), .B_FILE({WDIR, "bias_L2.mem"}), .M_FILE({WDIR, "mult_L2.mem"})) s2 (
        .clk(clk), .rst(rst), .start(stage_start), .in_w(sw4), .in_h(sh4),
        .in_valid(f1_v), .in_data(f1_d), .in_ready(s2_rdy), .out_ok(f2_ok), .px_start(s2_start),
        .out_valid(s2_ov), .out_data(s2_od), .anc_pop(nc2), .anc_data(24'd0));
    pipe_fifo #(.W(128)) f2 (.clk(clk), .rst(rst || stage_start), .reserve(s2_start), .ok(f2_ok), .push(s2_ov), .din(s2_od),
        .out_valid(f2_v), .dout(f2_d), .out_ready(s3_rdy), .err(f2_err));

    pipe_stage #(.C_IN(16), .C_OUT(16), .K(1), .MODE(0), .SHIFT(SHIFT3), .MAXW(MAXW),
                 .NS(NS), .PACK(PACK), .W_FILE({WDIR, WP, "L3.mem"}), .B_FILE({WDIR, "bias_L3.mem"}), .M_FILE({WDIR, "mult_L3.mem"})) s3 (
        .clk(clk), .rst(rst), .start(stage_start), .in_w(sw2), .in_h(sh2),
        .in_valid(f2_v), .in_data(f2_d), .in_ready(s3_rdy), .out_ok(f3_ok), .px_start(s3_start),
        .out_valid(s3_ov), .out_data(s3_od), .anc_pop(nc3), .anc_data(24'd0));
    pipe_fifo #(.W(128)) f3 (.clk(clk), .rst(rst || stage_start), .reserve(s3_start), .ok(f3_ok), .push(s3_ov), .din(s3_od),
        .out_valid(f3_v), .dout(f3_d), .out_ready(s4_rdy), .err(f3_err));

    pipe_stage #(.C_IN(16), .C_OUT(12), .K(3), .MODE((NS == 6) ? 0 : 2), .SHIFT(SHIFT4), .ANCHOR(ANCHOR), .MAXW(MAXW),   // pipe4: L4 output-serial at NS = 6
                 .NS(NS), .NDSP(NDSP4), .NDSP2(NDSP24), .MLAT((NS == 6) ? 3 : 2), .PACK(PACK), .W_FILE({WDIR, WP, "L4.mem"}), .B_FILE({WDIR, "bias_L4.mem"}), .M_FILE({WDIR, "mult_L4.mem"})) s4 (
        .clk(clk), .rst(rst), .start(stage_start), .in_w(sw2), .in_h(sh2),
        .in_valid(f3_v), .in_data(f3_d), .in_ready(s4_rdy), .out_ok(o_ok), .px_start(s4_start),
        .out_valid(s4_ov), .out_data(s4_od), .anc_pop(anc_pop), .anc_data(anc_q));

    anchor_fifo u_anc (.clk(clk), .rst(rst || stage_start), .push(anc_push && ANCHOR != 0), .din(l1_data), .pop(anc_pop),
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
