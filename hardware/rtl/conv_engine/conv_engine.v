// Folded convolution engine for ONE layer of SRNet (M4).  VALID convolution, uint8 in, uint8 out, bit-exact with
// software/ai/quantization/integer_reference.py.
//
// Compile-time configuration (one instance per layer; the M5 sequencer starts them one after the other):
//   C_IN, C_OUT, K (1 or 3), DEPTHWISE (needs C_IN == C_OUT), IN_W x IN_H input size, SHIFT, and the three exported files (wrom_Ln.mem, bias_Ln.mem, mult_Ln.mem).
// Memories (outside, so M5 can chain them ping-pong): input RAM read port  in_addr -> in_data   (1-cycle latency)
//                                                     output RAM write port out_we/out_addr/out_data
// Word format: pixel-major, channel c at bits [8*c +: 8]; address = y * width + x.
//
// Schedule, per output pixel (x,y in raster order):
//   STEPS = K*K*CI_LOOP steps (CI_LOOP = 1 for depthwise, else C_IN); step s = (ky*K + kx)*CI_LOOP + ci
//   each step: ONE input word is read; every one of the C_OUT MAC lanes does acc += a * w[co][..]
//     (depthwise: lane co uses channel co of the word; otherwise all lanes use channel ci)
//   a new pixel starts every PERIOD = max(STEPS, C_OUT) cycles: the single shared requantizer needs C_OUT cycles per
//   pixel and runs in the shadow of the next pixel's MAC steps (the accumulators are copied to `res` at the end).
// Expected total: cycles ~ NPIX * PERIOD + ~(C_OUT + 12)   (reported in `cycles`, measured in the testbench).
// Reset: synchronous; a single-cycle `rst` is enough: it stops the sequencer and clears every valid flag of the MAC and requantizer
// pipelines, so nothing is written afterwards. `start` may be pulsed again as soon as `done` (or `busy` low) is seen; the output RAM is rewritten completely each run.
module conv_engine #(
    parameter C_IN      = 3,
    parameter C_OUT     = 16,
    parameter K         = 3,
    parameter DEPTHWISE = 0,
    parameter IN_W      = 12,
    parameter IN_H      = 12,
    parameter SHIFT     = 24,
    parameter W_FILE    = "wrom.mem",      // step-major weight ROM file (wrom_Ln.mem), see weight_rom.v
    parameter B_FILE    = "bias.mem",
    parameter M_FILE    = "mult.mem",
    parameter AWI       = $clog2(IN_W * IN_H),
    parameter AWO       = $clog2((IN_W - K + 1) * (IN_H - K + 1))
) (
    input  wire                 clk,
    input  wire                 rst,      // synchronous, active high
    input  wire                 start,    // one-cycle pulse, ignored while busy
    output reg                  busy,
    output reg                  done,     // one-cycle pulse after the last output word was written
    // input activation RAM (synchronous read)
    output wire [AWI-1:0]       in_addr,
    input  wire [8*C_IN-1:0]    in_data,
    // output activation RAM (write port)
    output wire                 out_we,
    output wire [AWO-1:0]       out_addr,
    output wire [8*C_OUT-1:0]   out_data,
    output reg  [31:0]          cycles    // clock cycles from start until done
);
    localparam OW      = IN_W - K + 1;
    localparam OH      = IN_H - K + 1;
    localparam NPIX    = OW * OH;
    localparam CI_LOOP = DEPTHWISE ? 1 : C_IN;
    localparam STEPS   = K * K * CI_LOOP;
    localparam PERIOD  = (STEPS > C_OUT) ? STEPS : C_OUT;
    localparam WAW     = (STEPS > 1) ? $clog2(STEPS) : 1;

    // simulation-only parameter checks (ignored by synthesis)
    // synthesis translate_off
    initial begin
        if (DEPTHWISE && C_IN != C_OUT) begin $display("conv_engine: DEPTHWISE needs C_IN == C_OUT"); $finish; end
        if (C_IN > 256 || C_OUT > 256)  begin $display("conv_engine: channel counts are limited to 256 (8-bit counters)"); $finish; end
        if (K != 1 && K != 3)           begin $display("conv_engine: K must be 1 or 3"); $finish; end
        if (IN_W < K || IN_H < K)       begin $display("conv_engine: input smaller than the kernel"); $finish; end
    end
    // synthesis translate_on

    // ------------------------------------------------------------------ sequencer (address generation)
    reg         running;
    reg  [15:0] x, y, step;
    reg  [7:0]  ky, kx, ci;
    reg  [AWI-1:0] base, ky_off;       // base = y*IN_W + x, ky_off = ky*IN_W

    wire issue = running && (step < STEPS);
    assign in_addr = base + ky_off + kx;

    always @(posedge clk) begin
        if (rst) begin
            running <= 1'b0;
        end else if (start && !busy) begin
            running <= 1'b1;
            x <= 0; y <= 0; step <= 0; ky <= 0; kx <= 0; ci <= 0; base <= 0; ky_off <= 0;
        end else if (running) begin
            // step counter and pixel advance
            if (step == PERIOD - 1) begin
                step <= 0;
                if (x == OW - 1) begin
                    x <= 0;
                    base <= base + K;                  // (y+1)*IN_W - y*IN_W - (OW-1) = K
                    if (y == OH - 1) running <= 1'b0;  // last pixel issued
                    else y <= y + 1;
                end else begin
                    x <= x + 1;
                    base <= base + 1;
                end
            end else begin
                step <= step + 1;
            end
            // (ky, kx, ci) loop nest, advanced only on cycles that issue a step
            if (step < STEPS) begin
                if (ci == CI_LOOP - 1) begin
                    ci <= 0;
                    if (kx == K - 1) begin
                        kx <= 0;
                        if (ky == K - 1) begin ky <= 0; ky_off <= 0; end
                        else begin ky <= ky + 1; ky_off <= ky_off + IN_W; end
                    end else kx <= kx + 1;
                end else ci <= ci + 1;
            end
        end
    end

    // ------------------------------------------------------------------ stage 1: data and weights arrive (1-cycle RAM/ROM latency)
    reg        v1, first1, last1;
    reg [7:0]  ci1;
    wire [8*C_OUT-1:0] wvec;

    weight_rom #(.C_IN(C_IN), .C_OUT(C_OUT), .K(K), .DEPTHWISE(DEPTHWISE), .FILE(W_FILE)) u_wrom (
        .clk(clk), .addr(issue ? step[WAW-1:0] : {WAW{1'b0}}), .q(wvec));

    always @(posedge clk) begin
        v1     <= issue && !rst;
        first1 <= (step == 0);
        last1  <= (step == STEPS - 1);
        ci1    <= ci;
    end

    reg signed [31:0] bias_mem [0:C_OUT-1];
    reg        [15:0] mult_mem [0:C_OUT-1];
    initial begin
        $readmemh(B_FILE, bias_mem);
        $readmemh(M_FILE, mult_mem);
    end

    // ------------------------------------------------------------------ stages 2-3: MAC lanes
    wire [32*C_OUT-1:0] acc_flat;
    genvar co;
    generate
        for (co = 0; co < C_OUT; co = co + 1) begin : lane
            wire [7:0] a_co;
            if (DEPTHWISE) begin : dw_sel
                assign a_co = in_data[8*co +: 8];
            end else begin : bc_sel
                assign a_co = in_data[8*ci1 +: 8];
            end
            mac_unit u_mac (
                .clk(clk), .v(v1), .first(first1), .bias(bias_mem[co]),
                .a(a_co), .w(wvec[8*co +: 8]), .acc(acc_flat[32*co +: 32]));
        end
    endgenerate

    // final accumulators are visible 2 cycles after the last step's stage-1 cycle
    reg last_d1, last_d2;
    always @(posedge clk) begin
        last_d1 <= v1 && last1 && !rst;
        last_d2 <= last_d1 && !rst;
    end

    // ------------------------------------------------------------------ shared requantizer, runs in the shadow of the next pixel
    reg [32*C_OUT-1:0] res;
    reg                rq_busy;
    reg [7:0]          rq_i;
    always @(posedge clk) begin
        if (rst) rq_busy <= 1'b0;
        else if (last_d2) begin
            res     <= acc_flat;
            rq_busy <= 1'b1;
            rq_i    <= 8'd0;
        end else if (rq_busy) begin
            if (rq_i == C_OUT - 1) rq_busy <= 1'b0;
            else rq_i <= rq_i + 8'd1;
        end
    end

    wire         rq_v;
    wire [7:0]   rq_y;
    wire [8:0]   rq_tag;
    requant #(.SHIFT(SHIFT), .TW(9)) u_rq (
        .clk(clk), .rst(rst), .v_in(rq_busy), .acc(res[32*rq_i +: 32]), .m(mult_mem[rq_i]),
        .tag_in({rq_i == C_OUT - 1, rq_i}), .v_out(rq_v), .y(rq_y), .tag_out(rq_tag));

    // ------------------------------------------------------------------ output word assembly and write
    reg [8*C_OUT-1:0] out_word;
    reg               wr_pend;
    reg [AWO:0]       out_cnt;
    always @(posedge clk) begin
        wr_pend <= 1'b0;
        if (rq_v && !rst) begin
            out_word[8*rq_tag[7:0] +: 8] <= rq_y;
            if (rq_tag[8]) wr_pend <= 1'b1;        // last channel stored -> write the whole word next cycle
        end
    end
    assign out_we   = wr_pend;
    assign out_data = out_word;
    assign out_addr = out_cnt[AWO-1:0];

    always @(posedge clk) begin
        if (rst || (start && !busy)) out_cnt <= 0;
        else if (wr_pend) out_cnt <= out_cnt + 1;
    end

    // ------------------------------------------------------------------ status
    always @(posedge clk) begin
        if (rst) begin
            busy <= 1'b0; done <= 1'b0; cycles <= 0;
        end else begin
            done <= wr_pend && (out_cnt == NPIX - 1);
            if (start && !busy) begin busy <= 1'b1; cycles <= 0; end
            else begin
                if (done) busy <= 1'b0;
                if (busy && !done) cycles <= cycles + 1;
            end
        end
    end
endmodule
