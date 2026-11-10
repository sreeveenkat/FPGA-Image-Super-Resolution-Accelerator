// One layer stage of the whole-frame pipeline (docs/ARCHITECTURE_PIPELINE.md).  VALID convolution of a streamed frame, NS cycles ("slots") per output pixel.
// Branch pipe2 (docs/ARCHITECTURE_PIPELINE_V2.md): NS = 16 is the original design (P = 1, unchanged behaviour); NS = 8 handles P = 16 / NS = 2 channels
// per slot with P times the lanes and P requantizers (MODE 2: ceil(C_OUT / NS) requantizers).  Lanes with index >= NDSP use LUT multipliers.
// Branch pipe2p: PACK = 1 puts two lanes that share an activation into one DSP48 (pipe_mul2; docs/ARCHITECTURE_PIPELINE_V2P.md).
//
//   input pixels (raster, in_w x in_h, 8*C_IN bits, channel c at bits 8c+:8)
//     -> line buffer (K = 3: rows y-1 and y-2 in one simple dual-port RAM) -> KxK window shift register -> snapshot S (taken when a pixel starts)
//     -> NL multiplier lanes (DSP) -> NG pipelined adder trees -> bias / accumulator -> requant.v -> output word (8*C_OUT bits)
//
// MODE 0  output-serial, dense      (L1 conv3x3 3->16, L3 conv1x1 16->16): NL = P*K*K*C_IN lanes, slot s computes output channels s*P+r (tree r).
// MODE 1  output-serial, depthwise  (L2 dw3x3 16):                         NL = P*K*K lanes,      slot s computes channels s*P+r from the same window channels.
// MODE 2  input-serial              (L4 conv3x3 16->12):                   NL = P*K*K*C_OUT lanes, slot s adds input channels s*P+q to C_OUT accumulators;
//                                                                          after the last slot the C_OUT results are requantized NRQ per cycle.
// Weights: W_FILE (wpipe_Ln.mem for NS = 16, wpipe8_Ln.mem for NS = 8) = NS lines, line s = the NL lane weights of slot s, lane 0 = rightmost byte
//   (export_pipe.py).  Lane L = g*NT + t (tree g, term t).  MODE 0: t = tap*C_IN + ci, w[s*P+g][ci][tap];  MODE 1: t = tap, w[s*P+g][0][tap];
//   MODE 2: t = q*K*K + tap, w[g][s*P+q][tap];  tap = ky*K + kx.
// ANCHOR = 1 (MODE 2 only): output channel k = 4c + 2dy + dx gets colour c of `anc_data` added in the requantizer (requant ADD_EN); one anc_pop per pixel.
//
// Flow control (per pixel, never inside one): an input pixel is taken only while no completed window is waiting; a pixel starts (`px_start`, snapshot)
// when its window is complete AND `out_ok` (the consumer has room for one more result).  A started pixel runs its 16 slots without a stall and
// produces exactly one `out_valid` pulse some cycles later.  (Comments below that say 16 slots mean NS slots.)  `start` (frame start, only while the stage is empty) resets the input coordinates.
module pipe_stage #(
    parameter C_IN   = 3,
    parameter C_OUT  = 16,
    parameter K      = 3,
    parameter MODE   = 0,
    parameter SHIFT  = 24,
    parameter ANCHOR = 0,
    parameter NS     = 16,                   // slots per output pixel: 16 (original) or 8 (pipe2)
    parameter NDSP   = 1 << 20,              // lanes 0..NDSP-1 on DSP48 multipliers, the rest in LUTs (default: all DSP)
    parameter PACK   = 0,                    // pipe2p: two lanes per DSP48 (pipe_mul2) where two trees share the activations: MODE 2, and MODE 0 with 2 trees
                                             // (NS = 8); MODE 1 is never packed (its trees read different channels).  With PACK = 1, NDSP is ignored.
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
    localparam NCH = 16;                                        // channels walked per pixel (C_OUT of MODE 0/1, C_IN of MODE 2)
    localparam P   = NCH / NS;                                  // channels per slot
    localparam SW  = $clog2(NS);                                // slot counter width
    localparam KK  = K * K;
    localparam IWB = 8 * C_IN;
    localparam OWB = 8 * C_OUT;
    localparam NL  = (MODE == 0) ? P * KK * C_IN : (MODE == 1) ? P * KK : P * KK * C_OUT;
    localparam NG  = (MODE == 2) ? C_OUT : P;
    localparam NRQ = (MODE == 2) ? (C_OUT + NS - 1) / NS : P;   // requantizers
    localparam NT  = NL / NG;                                   // terms per adder tree
    localparam PK  = (PACK != 0) && ((MODE == 2) || (MODE == 0 && NG % 2 == 0));   // packing used in this stage
    localparam NTT = PK ? NT + 1 : NT;                          // terms per tree: + the borrow count of the high products (pipe_mul2)
    localparam LV  = $clog2(NTT);
    localparam D   = 2 + LV;                                    // slot issue -> tree sum

    // synthesis translate_off
    initial begin
        if (K != 1 && K != 3)                    begin $display("pipe_stage: K must be 1 or 3"); $finish; end
        if (NS != 16 && NS != 8)                 begin $display("pipe_stage: NS must be 16 or 8"); $finish; end
        if (MODE == 2 && C_OUT % NRQ != 0)       begin $display("pipe_stage: MODE 2 needs C_OUT divisible by the requantizer count"); $finish; end
        if (MODE != 2 && C_OUT != NCH)           begin $display("pipe_stage: MODE 0/1 need C_OUT == 16"); $finish; end
        if (MODE == 1 && C_IN != C_OUT)          begin $display("pipe_stage: MODE 1 needs C_IN == C_OUT"); $finish; end
        if (MODE == 2 && C_IN != NCH)            begin $display("pipe_stage: MODE 2 needs C_IN == 16"); $finish; end
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

    (* max_fanout = 64 *) reg d1_v;          // pipe2: drives the clock enable of the whole KxK window (~1,150 FFs at C_IN = 16); replicated for timing
    reg             d1_prod;
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
    (* max_fanout = 64 *) reg [SW-1:0] s;
    assign px_start = win_rdy && out_ok && (!run || s == NS - 1);

    always @(posedge clk) begin
        if (rst || start) begin
            run <= 1'b0; s <= {SW{1'b0}}; win_rdy <= 1'b0;
        end else begin
            if (d1_prod) win_rdy <= 1'b1;
            if (px_start) begin
                win_rdy <= 1'b0; run <= 1'b1; s <= {SW{1'b0}}; snap <= win;
            end else if (run) begin
                s <= s + 1'b1;
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
    // PK: lane L of an even tree g and lane L + NT of tree g + 1 (same term t, same activation) share one pipe_mul2: the even tree takes `lo`,
    // the odd tree takes `hi_raw` (pk_hi) and its borrow bit (pk_b); every tree adds the count of its borrow bits as one extra term.
    wire [24*NG-1:0] sums;
    wire signed [16:0] pk_hi [0:NL-1];
    wire               pk_b  [0:NL-1];
    genvar g, t;
    generate
        for (g = 0; g < NG; g = g + 1) begin : tree
            wire [17*NTT-1:0] prods;
            wire [NT-1:0]     bor;
            for (t = 0; t < NT; t = t + 1) begin : lane
                localparam integer L = g * NT + t;                      // lane index
                wire [7:0] a_l;
                if (MODE == 0) begin : g_fix
                    assign a_l = snap[t * 8 +: 8];                                          // tap*C_IN + ci, the same for every tree
                end else if (MODE == 1) begin : g_sel
                    assign a_l = snap[((t % KK) * C_IN + s * P + g) * 8 +: 8];              // channel s*P+g of tap t
                end else begin : g_sel2
                    assign a_l = snap[((t % KK) * C_IN + s * P + t / KK) * 8 +: 8];         // channel s*P+q of tap t % KK, q = t / KK
                end
                wire signed [16:0] p_l;
                wire               b_l;
                if (!PK) begin : g_one
                    if (L < NDSP) begin : g_dsp
                        pipe_mul u_mul (.clk(clk), .a(a_l), .w(wrow[8*L +: 8]), .prod(p_l));
                    end else begin : g_lut
                        pipe_mul_lut u_mul (.clk(clk), .a(a_l), .w(wrow[8*L +: 8]), .prod(p_l));
                    end
                    assign b_l = 1'b0;
                end else if (g % 2 == 0) begin : g_pk
                    wire signed [16:0] hi;
                    wire               bb;
                    pipe_mul2 u_mul (.clk(clk), .a(a_l), .w1(wrow[8*L +: 8]), .w2(wrow[8*(L + NT) +: 8]), .lo(p_l), .hi_raw(hi), .b(bb));
                    assign pk_hi[L + NT] = hi;
                    assign pk_b[L + NT]  = bb;
                    assign b_l = 1'b0;
                end else begin : g_pko
                    assign p_l = pk_hi[L];
                    assign b_l = pk_b[L];
                end
                assign prods[17*t +: 17] = p_l;
                assign bor[t] = b_l;
            end
            if (PK) begin : g_bc
                reg [5:0] bc;                                    // borrow count of this tree's high products (0 for an even tree)
                integer bi;
                always @* begin
                    bc = 6'd0;
                    for (bi = 0; bi < NT; bi = bi + 1) bc = bc + {5'd0, bor[bi]};
                end
                assign prods[17*NT +: 17] = {11'd0, bc};
            end
            wire signed [23:0] s_g;
            adder_tree #(.N(NTT), .IW(17), .OW(24)) u_tree (.clk(clk), .in(prods), .sum(s_g));
            assign sums[24*g +: 24] = s_g;
        end
    endgenerate

    // slot tags follow the data: vd[k] / sd[k] belong to the data that is k cycles after its slot was issued
    reg [D:0] vd;
    reg [SW-1:0] sd [0:D];
    integer k;
    always @(posedge clk) begin
        vd[0] <= 1'b0;                                           // unused (index 0 = issue cycle, see below)
        for (k = 1; k <= D; k = k + 1) begin
            vd[k] <= (k == 1) ? (run && !rst) : (vd[k-1] && !rst);
            sd[k] <= (k == 1) ? s : sd[k-1];
        end
    end

    // ------------------------------------------------------------------ accumulate and feed the requantizers (NRQ of them, in lockstep)
    wire [NRQ-1:0]   rq_v;
    wire [8*NRQ-1:0] rq_y;
    wire [5*NRQ-1:0] rq_tag;
    genvar r;

    generate
        if (MODE != 2) begin : g_oser
            for (r = 0; r < NRQ; r = r + 1) begin : rq
                reg signed [31:0] bias_r;                        // bias of the channel that reaches the adder next cycle
                reg signed [31:0] acc;
                reg               acc_v;
                reg [4:0]         acc_c;                         // output channel s*P + r
                reg               rq_v_r;
                reg signed [31:0] rq_acc_r;
                reg [15:0]        rq_m_r;
                reg [4:0]         rq_tag_r;
                always @(posedge clk) begin
                    bias_r <= bias_mem[sd[D-1] * P + r];
                    acc    <= bias_r + {{8{sums[24*r+23]}}, sums[24*r +: 24]};
                    acc_v  <= vd[D] && !rst;
                    acc_c  <= sd[D] * P + r;
                    rq_acc_r <= acc;
                    rq_m_r   <= mult_mem[acc_c];
                    rq_tag_r <= acc_c;
                    rq_v_r   <= acc_v && !rst;
                end
                requant #(.SHIFT(SHIFT), .TW(5), .ADD_EN(0)) u_rq (
                    .clk(clk), .rst(rst), .v_in(rq_v_r), .acc(rq_acc_r), .m(rq_m_r), .add(8'd0), .tag_in(rq_tag_r),
                    .v_out(rq_v[r]), .y(rq_y[8*r +: 8]), .tag_out(rq_tag[5*r +: 5]));
            end
            assign anc_pop = 1'b0;
        end else begin : g_iser
            localparam NJ = C_OUT / NRQ;                         // serial requantizer steps per pixel (<= NS)
            reg signed [31:0] acc  [0:NG-1];
            reg signed [31:0] hold_r [0:NG-1];
            reg               ser_go;
            reg               ser_run;
            reg [4:0]         j;
            integer gi;
            always @(posedge clk) begin
                for (gi = 0; gi < NG; gi = gi + 1)
                    if (vd[D]) begin
                        acc[gi] <= ((sd[D] == 0) ? bias_mem[gi] : acc[gi]) + {{8{sums[24*gi+23]}}, sums[24*gi +: 24]};
                        if (sd[D] == NS - 1)
                            hold_r[gi] <= ((sd[D] == 0) ? bias_mem[gi] : acc[gi]) + {{8{sums[24*gi+23]}}, sums[24*gi +: 24]};
                    end
                ser_go <= vd[D] && (sd[D] == NS - 1) && !rst;
                if (rst) begin
                    ser_run <= 1'b0; j <= 5'd0;
                end else begin
                    if (ser_go) begin ser_run <= 1'b1; j <= 5'd0; end
                    else if (ser_run) begin
                        j <= j + 5'd1;
                        if (j == NJ - 1) ser_run <= 1'b0;
                    end
                end
            end
            for (r = 0; r < NRQ; r = r + 1) begin : rq
                wire [4:0]        ch = j * NRQ + r;              // output channel of this requantizer in this step
                reg               rq_v_r;
                reg signed [31:0] rq_acc_r;
                reg [15:0]        rq_m_r;
                reg [7:0]         rq_add_r;
                reg [4:0]         rq_tag_r;
                always @(posedge clk) begin
                    rq_v_r   <= ser_run && !rst;
                    rq_acc_r <= hold_r[ch];
                    rq_m_r   <= mult_mem[ch];
                    rq_tag_r <= ch;
                    rq_add_r <= ANCHOR ? anc_data[8 * (ch >> 2) +: 8] : 8'd0;
                end
                requant #(.SHIFT(SHIFT), .TW(5), .ADD_EN(ANCHOR)) u_rq (
                    .clk(clk), .rst(rst), .v_in(rq_v_r), .acc(rq_acc_r), .m(rq_m_r), .add(rq_add_r), .tag_in(rq_tag_r),
                    .v_out(rq_v[r]), .y(rq_y[8*r +: 8]), .tag_out(rq_tag[5*r +: 5]));
            end
            assign anc_pop = ser_go && (ANCHOR != 0);            // FIFO data valid from the next cycle, held until the next pop (>= NS cycles)
        end
    endgenerate

    // ------------------------------------------------------------------ output word (all requantizers are valid in the same cycles)
    reg  [OWB-1:0] word;
    reg  [OWB-1:0] word_n;
    integer ri;
    always @* begin
        word_n = word;
        for (ri = 0; ri < NRQ; ri = ri + 1)
            word_n[8 * rq_tag[5*ri +: 5] +: 8] = rq_y[8*ri +: 8];
    end
    always @(posedge clk) begin
        out_valid <= 1'b0;
        if (rst) word <= {OWB{1'b0}};
        else if (rq_v[NRQ-1]) begin
            word <= word_n;
            if (rq_tag[5*(NRQ-1) +: 5] == C_OUT - 1) begin out_valid <= 1'b1; out_data <= word_n; end
        end
    end
endmodule
