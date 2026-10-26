// One layer stage of the whole-frame pipeline (docs/ARCHITECTURE_PIPELINE.md).  VALID convolution of a streamed frame, 16 cycles ("slots") per output pixel.
//
//   input pixels (raster, in_w x in_h, 8*C_IN bits, channel c at bits 8c+:8)
//     -> line buffer (K = 3: rows y-1 and y-2 in one simple dual-port RAM) -> KxK window shift register -> snapshot S (taken when a pixel starts)
//     -> NL multiplier lanes (DSP) -> NG pipelined adder trees -> bias / accumulator -> requant.v -> output word (8*C_OUT bits)
//
// MODE 0  output-serial, dense      (L1 conv3x3 3->16, L3 conv1x1 16->16): NL = K*K*C_IN lanes, slot s computes output channel s in one go.
// MODE 1  output-serial, depthwise  (L2 dw3x3 16):                         NL = K*K lanes,      slot s computes channel s from channel s of the window.
// MODE 2  input-serial              (L4 conv3x3 16->12):                   NL = K*K*C_OUT lanes, slot s adds input channel s to C_OUT accumulators;
//                                                                          after slot 15 the C_OUT results are requantized one per cycle.
// Weights: W_FILE (wpipe_Ln.mem) = 16 lines, line s = the NL lane weights of slot s, lane 0 = rightmost byte (export_pipe.py).
//   MODE 0 lane l = tap*C_IN + ci: w[s][ci][tap];  MODE 1 lane l = tap: w[s][0][tap];  MODE 2 lane l = g*K*K + tap: w[g][s][tap];  tap = ky*K + kx.
// ANCHOR = 1 (MODE 2 only): output channel k = 4c + 2dy + dx gets colour c of `anc_data` added in the requantizer (requant ADD_EN); one anc_pop per pixel.
//
// Flow control (per pixel, never inside one): an input pixel is taken only while no completed window is waiting; a pixel starts (`px_start`, snapshot)
// when its window is complete AND `out_ok` (the consumer has room for one more result).  A started pixel runs its 16 slots without a stall and
// produces exactly one `out_valid` pulse some cycles later.  `start` (frame start, only while the stage is empty) resets the input coordinates.
module pipe_stage #(
    parameter C_IN   = 3,
    parameter C_OUT  = 16,
    parameter K      = 3,
    parameter MODE   = 0,
    parameter SHIFT  = 24,
    parameter ANCHOR = 0,
    parameter MAXW   = 1024,                 // line-buffer depth = maximum in_w
    parameter W_FILE = "wpipe.mem",
    parameter B_FILE = "bias.mem",
    parameter M_FILE = "mult.mem",
    parameter AW     = $clog2(MAXW)
) (
    input  wire                 clk,
    input  wire                 rst,
    input  wire                 start,
    input  wire [15:0]          in_w,
    input  wire [15:0]          in_h,
    input  wire                 in_valid,
    input  wire [8*C_IN-1:0]    in_data,
    output wire                 in_ready,
    input  wire                 out_ok,
    output wire                 px_start,
    output reg                  out_valid,
    output reg  [8*C_OUT-1:0]   out_data,
    output wire                 anc_pop,
    input  wire [23:0]          anc_data
);
    localparam NS  = 16;                                        // slots per output pixel
    localparam KK  = K * K;
    localparam IWB = 8 * C_IN;
    localparam OWB = 8 * C_OUT;
    localparam NL  = (MODE == 0) ? KK * C_IN : (MODE == 1) ? KK : KK * C_OUT;
    localparam NG  = (MODE == 2) ? C_OUT : 1;
    localparam NT  = NL / NG;                                   // terms per adder tree
    localparam LV  = $clog2(NT);
    localparam D   = 2 + LV;                                    // slot issue -> tree sum

    // synthesis translate_off
    initial begin
        if (K != 1 && K != 3)                    begin $display("pipe_stage: K must be 1 or 3"); $finish; end
        if (MODE != 2 && C_OUT != NS)            begin $display("pipe_stage: MODE 0/1 need C_OUT == 16"); $finish; end
        if (MODE == 1 && C_IN != C_OUT)          begin $display("pipe_stage: MODE 1 needs C_IN == C_OUT"); $finish; end
        if (MODE == 2 && C_IN != NS)             begin $display("pipe_stage: MODE 2 needs C_IN == 16"); $finish; end
        if (ANCHOR && (MODE != 2 || C_OUT != 12)) begin $display("pipe_stage: ANCHOR needs MODE 2 and C_OUT == 12"); $finish; end
        if (NT < 2)                              begin $display("pipe_stage: fewer than 2 terms per tree"); $finish; end
    end
    // synthesis translate_on

    // ------------------------------------------------------------------ front end: input coordinates, line buffer, window
    reg [15:0]  ix, iy;                      // coordinates of the next input pixel
    reg         in_done;                     // every pixel of the frame taken (also high after reset until the first start)
    reg         hold;                        // a pixel that completes a window was taken; its window has not started yet
    reg         win_rdy;                     // the window register holds a complete, not yet started window
    wire        produce = (ix >= K - 1) && (iy >= K - 1);
    assign      in_ready = !hold && !in_done;
    wire        take = in_valid && in_ready;

    reg             d1_v, d1_prod;
    reg [IWB-1:0]   d1_p;
    reg [AW-1:0]    d1_x;
    reg [KK*IWB-1:0] win;                    // tap (ky,kx) at bits (ky*K+kx)*IWB, ky = 0 is the oldest row
    reg [KK*IWB-1:0] snap;                   // window of the pixel being computed

    always @(posedge clk) begin
        d1_v    <= take;
        d1_prod <= take && produce;
        d1_p    <= in_data;
        d1_x    <= ix[AW-1:0];
        if (rst) begin
            in_done <= 1'b1; hold <= 1'b0; ix <= 16'd0; iy <= 16'd0; d1_v <= 1'b0; d1_prod <= 1'b0;
        end else if (start) begin
            in_done <= 1'b0; hold <= 1'b0; ix <= 16'd0; iy <= 16'd0;
        end else begin
            if (take) begin
                if (produce) hold <= 1'b1;
                if (ix == in_w - 1) begin
                    ix <= 16'd0; iy <= iy + 16'd1;
                    if (iy == in_h - 1) in_done <= 1'b1;
                end else ix <= ix + 16'd1;
            end
            if (px_start) hold <= 1'b0;
        end
    end

    generate
        if (K == 3) begin : g_lb
            reg [2*IWB-1:0] lb [0:MAXW-1];   // {row y-2, row y-1} of each column
            reg [2*IWB-1:0] lb_q;
            always @(posedge clk) begin
                if (take) lb_q <= lb[ix[AW-1:0]];
                if (d1_v) lb[d1_x] <= {lb_q[IWB-1:0], d1_p};
            end
            integer ky, kx;
            always @(posedge clk)
                if (d1_v)
                    for (ky = 0; ky < 3; ky = ky + 1) begin
                        for (kx = 0; kx < 2; kx = kx + 1) win[(ky*3+kx)*IWB +: IWB] <= win[(ky*3+kx+1)*IWB +: IWB];
                        win[(ky*3+2)*IWB +: IWB] <= (ky == 0) ? lb_q[IWB +: IWB] : (ky == 1) ? lb_q[0 +: IWB] : d1_p;
                    end
        end else begin : g_nolb
            always @(posedge clk) if (d1_v) win <= d1_p;
        end
    endgenerate

    // ------------------------------------------------------------------ slot counter
    reg        run;
    (* max_fanout = 64 *) reg [3:0] s;
    assign px_start = win_rdy && out_ok && (!run || s == NS - 1);

    always @(posedge clk) begin
        if (rst || start) begin
            run <= 1'b0; s <= 4'd0; win_rdy <= 1'b0;
        end else begin
            if (d1_prod) win_rdy <= 1'b1;
            if (px_start) begin
                win_rdy <= 1'b0; run <= 1'b1; s <= 4'd0; snap <= win;
            end else if (run) begin
                s <= s + 4'd1;
                if (s == NS - 1) run <= 1'b0;
            end
        end
    end

    // ------------------------------------------------------------------ weights, bias, multipliers
    reg [8*NL-1:0]    rom [0:NS-1];
    reg signed [31:0] bias_mem [0:C_OUT-1];
    reg [15:0]        mult_mem [0:C_OUT-1];
    initial begin
        $readmemh(W_FILE, rom);
        $readmemh(B_FILE, bias_mem);
        $readmemh(M_FILE, mult_mem);
    end
    wire [8*NL-1:0] wrow = rom[s];

    // lanes and adder trees, one generate block per tree (group): each tree's input bus has only its own NT drivers (a single NL-wide bus with NL
    // partial drivers makes Icarus re-resolve it NL times per cycle and run ~100x slower; the hardware is the same either way)
    wire [24*NG-1:0] sums;
    genvar g, t;
    generate
        for (g = 0; g < NG; g = g + 1) begin : tree
            wire [17*NT-1:0] prods;
            for (t = 0; t < NT; t = t + 1) begin : lane
                localparam integer L = g * NT + t;                      // lane index
                wire [7:0] a_l;
                if (MODE == 0) begin : g_fix
                    assign a_l = snap[((L / C_IN) * C_IN + (L % C_IN)) * 8 +: 8];
                end else begin : g_sel
                    assign a_l = snap[((L % KK) * C_IN + s) * 8 +: 8];
                end
                wire signed [16:0] p_l;
                pipe_mul u_mul (.clk(clk), .a(a_l), .w(wrow[8*L +: 8]), .prod(p_l));
                assign prods[17*t +: 17] = p_l;
            end
            wire signed [23:0] s_g;
            adder_tree #(.N(NT), .IW(17), .OW(24)) u_tree (.clk(clk), .in(prods), .sum(s_g));
            assign sums[24*g +: 24] = s_g;
        end
    endgenerate

    // slot tags follow the data: vd[k] / sd[k] belong to the data that is k cycles after its slot was issued
    reg [D:0] vd;
    reg [3:0] sd [0:D];
    integer k;
    always @(posedge clk) begin
        vd[0] <= 1'b0;                                           // unused (index 0 = issue cycle, see below)
        for (k = 1; k <= D; k = k + 1) begin
            vd[k] <= (k == 1) ? (run && !rst) : (vd[k-1] && !rst);
            sd[k] <= (k == 1) ? s : sd[k-1];
        end
    end

    // ------------------------------------------------------------------ accumulate and feed the requantizer
    reg               rq_v_r;
    reg signed [31:0] rq_acc_r;
    reg [15:0]        rq_m_r;
    reg [7:0]         rq_add_r;
    reg [4:0]         rq_tag_r;
    reg               ser_go;

    generate
        if (MODE != 2) begin : g_oser
            reg signed [31:0] bias_r;                            // bias of the slot that reaches the adder next cycle
            reg signed [31:0] acc;
            reg               acc_v;
            reg [3:0]         acc_s;
            always @(posedge clk) begin
                bias_r <= bias_mem[sd[D-1]];
                acc    <= bias_r + {{8{sums[23]}}, sums[23:0]};
                acc_v  <= vd[D] && !rst;
                acc_s  <= sd[D];
                rq_acc_r <= acc;
                rq_m_r   <= mult_mem[acc_s];
                rq_tag_r <= {1'b0, acc_s};
                rq_add_r <= 8'd0;
                rq_v_r   <= acc_v && !rst;
                ser_go   <= 1'b0;
            end
            assign anc_pop = 1'b0;
        end else begin : g_iser
            reg signed [31:0] acc  [0:NG-1];
            reg signed [31:0] hold_r [0:NG-1];
            reg               ser_run;
            reg [4:0]         j;
            integer gi;
            always @(posedge clk) begin
                for (gi = 0; gi < NG; gi = gi + 1)
                    if (vd[D]) begin
                        acc[gi] <= ((sd[D] == 4'd0) ? bias_mem[gi] : acc[gi]) + {{8{sums[24*gi+23]}}, sums[24*gi +: 24]};
                        if (sd[D] == NS - 1)
                            hold_r[gi] <= ((sd[D] == 4'd0) ? bias_mem[gi] : acc[gi]) + {{8{sums[24*gi+23]}}, sums[24*gi +: 24]};
                    end
                ser_go <= vd[D] && (sd[D] == NS - 1) && !rst;
                if (rst) begin
                    ser_run <= 1'b0; j <= 5'd0; rq_v_r <= 1'b0;
                end else begin
                    if (ser_go) begin ser_run <= 1'b1; j <= 5'd0; end
                    else if (ser_run) begin
                        j <= j + 5'd1;
                        if (j == C_OUT - 1) ser_run <= 1'b0;
                    end
                    rq_v_r <= ser_run;
                end
                rq_acc_r <= hold_r[j];
                rq_m_r   <= mult_mem[j];
                rq_tag_r <= j;
                rq_add_r <= ANCHOR ? anc_data[8 * (j >> 2) +: 8] : 8'd0;
            end
            assign anc_pop = ser_go && (ANCHOR != 0);            // FIFO data valid from the next cycle, held until the next pop (>= 16 cycles)
        end
    endgenerate

    wire       rq_v;
    wire [7:0] rq_y;
    wire [4:0] rq_tag;
    requant #(.SHIFT(SHIFT), .TW(5), .ADD_EN(ANCHOR)) u_rq (
        .clk(clk), .rst(rst), .v_in(rq_v_r), .acc(rq_acc_r), .m(rq_m_r), .add(rq_add_r), .tag_in(rq_tag_r),
        .v_out(rq_v), .y(rq_y), .tag_out(rq_tag));

    // ------------------------------------------------------------------ output word
    reg  [OWB-1:0] word;
    wire [OWB-1:0] word_n = (word & ~({{(OWB-8){1'b0}}, 8'hFF} << (8 * rq_tag))) | ({{(OWB-8){1'b0}}, rq_y} << (8 * rq_tag));
    always @(posedge clk) begin
        out_valid <= 1'b0;
        if (rst) word <= {OWB{1'b0}};
        else if (rq_v) begin
            word <= word_n;
            if (rq_tag == C_OUT - 1) begin out_valid <= 1'b1; out_data <= word_n; end
        end
    end
endmodule
