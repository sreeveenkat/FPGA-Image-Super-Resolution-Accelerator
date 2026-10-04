// Self-checking testbench: ONE layer of the conv engine against the golden hex dumps (M4).
//   iverilog -g2012 -P tb_conv_layer.LAYER=1 -P tb_conv_layer.HC=6 ...   vvp ... +TILE=small12
//   LAYER 1..4 selects the geometry/files; HC is the output core WIDTH of the tile (6 for small12, 64 for the 70x70 tiles),
//   HH the core HEIGHT (default HC; the randomized tests use HC=6, HH=4 to test non-square address maths).
//   RAND=1: use data/golden/unit/randL<LAYER>_{wrom,bias,mult}.mem (distinct M per channel, extreme values), SHIFT 20, and the
//   input/expected files data/golden/unit/randL<LAYER>_{in,out}.hex; +TILE is ignored.
// Layer n reads the golden output of layer n-1 (layer 1 reads <tile>_in.hex) and must reproduce <tile>_Ln.hex exactly.
// Run from the project root (paths are relative to it).  Prints "PASS ..." or "FAIL ...".
`timescale 1ns/1ps
module tb_conv_layer;
    parameter LAYER = 1;
    parameter HC    = 6;
    parameter HH    = HC;
    parameter RAND  = 0;

    // geometry per layer: 1 conv3x3 3->16 | 2 depthwise3x3 16 | 3 pointwise 16->16 | 4 conv3x3 16->12
    localparam C_IN      = (LAYER == 1) ? 3 : 16;
    localparam C_OUT     = (LAYER == 4) ? 12 : 16;
    localparam K         = (LAYER == 3) ? 1 : 3;
    localparam DEPTHWISE = (LAYER == 2) ? 1 : 0;
    localparam IN_W      = (LAYER == 1) ? HC + 6 : (LAYER == 2) ? HC + 4 : HC + 2;
    localparam IN_H      = IN_W - (HC - HH);
    localparam OW        = IN_W - K + 1;
    localparam OH        = IN_H - K + 1;
    `include "hardware/rtl/weights/network_params.vh"
    localparam SHIFT = RAND ? 20 : (LAYER == 1) ? L1_SHIFT : (LAYER == 2) ? L2_SHIFT : (LAYER == 3) ? L3_SHIFT : L4_SHIFT;
    localparam NIN   = IN_W * IN_H;
    localparam NOUT  = OW * OH;

    reg clk = 0, rst = 1, start = 0;
    always #5 clk = ~clk;

    wire [$clog2(NIN)-1:0]  in_addr;
    wire [8*C_IN-1:0]       in_data;
    wire                    out_we;
    wire [$clog2(NOUT)-1:0] out_addr;
    wire [8*C_OUT-1:0]      out_data;
    wire busy, done;
    wire [31:0] cycles;

    tile_ram #(.WIDTH(8*C_IN), .DEPTH(NIN)) ram_in (
        .clk(clk), .we(1'b0), .waddr({$clog2(NIN){1'b0}}), .wdata({8*C_IN{1'b0}}), .raddr(in_addr), .rdata(in_data));
    tile_ram #(.WIDTH(8*C_OUT), .DEPTH(NOUT)) ram_out (
        .clk(clk), .we(out_we), .waddr(out_addr), .wdata(out_data), .raddr({$clog2(NOUT){1'b0}}), .rdata());

`ifdef POSTSYNTH
    // post-synthesis functional netlist: no parameters, the geometry/weights are baked into the netlist (LAYER/HC must match)
    localparam PERIOD_INFO = 0;
    conv_engine dut (
`else
    localparam PERIOD_INFO = (((K*K*(DEPTHWISE ? 1 : C_IN)) > C_OUT) ? (K*K*(DEPTHWISE ? 1 : C_IN)) : C_OUT);
    conv_engine #(.C_IN(C_IN), .C_OUT(C_OUT), .K(K), .DEPTHWISE(DEPTHWISE), .IN_W(IN_W), .IN_H(IN_H), .SHIFT(SHIFT),
                  .W_FILE(RAND ? {"data/golden/unit/randL", "0" + LAYER[7:0], "_wrom.mem"} : {"hardware/rtl/weights/wrom_L", "0" + LAYER[7:0], ".mem"}),
                  .B_FILE(RAND ? {"data/golden/unit/randL", "0" + LAYER[7:0], "_bias.mem"}    : {"hardware/rtl/weights/bias_L",    "0" + LAYER[7:0], ".mem"}),
                  .M_FILE(RAND ? {"data/golden/unit/randL", "0" + LAYER[7:0], "_mult.mem"}    : {"hardware/rtl/weights/mult_L",    "0" + LAYER[7:0], ".mem"})) dut (
`endif
        .clk(clk), .rst(rst), .start(start), .busy(busy), .done(done),
        .in_addr(in_addr), .in_data(in_data), .out_we(out_we), .out_addr(out_addr), .out_data(out_data), .cycles(cycles));

    reg [7:0] raw_in  [0:NIN*C_IN-1];
    reg [7:0] raw_exp [0:NOUT*C_OUT-1];
    reg [8*64-1:0] tile;
    reg [8*200-1:0] fin, fexp;
    integer nx, p, c, j, errors, shown, timeout, tmax, pass, npass, first_cycles, ok;
    localparam PER_X = (((K*K*(DEPTHWISE ? 1 : C_IN)) > C_OUT) ? (K*K*(DEPTHWISE ? 1 : C_IN)) : C_OUT);
    reg extra;
    reg idle_watch = 0;
`ifdef MONITOR
    integer mon_n = 0;
    always @(posedge clk) begin
        mon_n = mon_n + 1;
        if (mon_n % 50 == 0 || out_we || done) $display("  [mon %0d] rst=%b start=%b busy=%b done=%b out_we=%b out_addr=%0d cycles=%0d in_addr=%0d", mon_n, rst, start, busy, done, out_we, out_addr, cycles, in_addr);
    end
`endif
    always @(posedge clk) if (idle_watch && (busy || out_we || done)) begin
        $display("FAIL layer %0d: activity after an aborting reset (busy=%b out_we=%b done=%b)", LAYER, busy, out_we, done);
        $finish;
    end

    task load_input;
        begin
            for (p = 0; p < NIN; p = p + 1)
                for (c = 0; c < C_IN; c = c + 1)
                    ram_in.mem[p][8*c +: 8] = raw_in[p*C_IN + c];
        end
    endtask

    task clear_output;  // poison the output RAM so that a missing write cannot hide behind an old correct value
        begin
            for (p = 0; p < NOUT; p = p + 1) ram_out.mem[p] = {C_OUT{8'hA5}};
        end
    endtask

    task pulse_start;
        begin
            @(negedge clk); start = 1;
            @(negedge clk); start = 0;
        end
    endtask

    task wait_done;
        begin
            timeout = 0;
            while (!done && timeout < tmax) begin @(posedge clk); timeout = timeout + 1; end
            ok = done;
        end
    endtask

    task compare;
        begin
            errors = 0; shown = 0;
            for (p = 0; p < NOUT; p = p + 1)
                for (c = 0; c < C_OUT; c = c + 1)
                    if (ram_out.mem[p][8*c +: 8] !== raw_exp[p*C_OUT + c]) begin
                        errors = errors + 1;
                        if (shown < 5) begin
                            $display("  mismatch pixel %0d (y=%0d x=%0d) ch %0d: got %0d expected %0d", p, p / OW, p % OW, c,
                                     ram_out.mem[p][8*c +: 8], raw_exp[p*C_OUT + c]);
                            shown = shown + 1;
                        end
                    end
        end
    endtask

    initial begin
        if (!$value$plusargs("TILE=%s", tile)) tile = "small12";
        if (!$value$plusargs("TIMEOUT=%d", tmax)) tmax = 5000000;
        if (RAND) begin
            tile = "rand";
            $sformat(fin,  "data/golden/unit/randL%0d_in.hex",  LAYER);
            $sformat(fexp, "data/golden/unit/randL%0d_out.hex", LAYER);
        end else begin
            if (LAYER == 1) $sformat(fin, "data/golden/%0s_in.hex", tile);
            else            $sformat(fin, "data/golden/%0s_L%0d.hex", tile, LAYER - 1);
            $sformat(fexp, "data/golden/%0s_L%0d.hex", tile, LAYER);
        end
        $readmemh(fin, raw_in);
        $readmemh(fexp, raw_exp);
        // guard against a vacuous pass: X compares equal to X with !==, so a missing/short golden file must be detected explicitly
        nx = 0;
        for (p = 0; p < NIN*C_IN;   p = p + 1) if (^raw_in[p]  === 1'bx) nx = nx + 1;
        for (p = 0; p < NOUT*C_OUT; p = p + 1) if (^raw_exp[p] === 1'bx) nx = nx + 1;
        if (nx != 0) begin
            $display("FAIL layer %0d tile %0s: %0d undefined bytes in the golden files %0s / %0s (missing or too short?)", LAYER, tile, nx, fin, fexp);
            $finish;
        end
        load_input;
        // Small tiles (and always with +REPEAT) are run three times:
        //   pass 0: normal run
        //   pass 1: second run right after the first one (counters/addresses must restart cleanly), output RAM poisoned first
        //   pass 2: PERIOD+6 runs, each aborted by a ONE-cycle reset at a different cycle; the engine must stay quiet afterwards; then a fresh run
        extra = (HC <= 8) || $test$plusargs("REPEAT");
        npass = extra ? 3 : 1;
        first_cycles = -1;
`ifdef POSTSYNTH
        wait (glbl.GSR === 1'b0);     // the Xilinx global set/reset holds every flip-flop for the first 100 ns of a netlist simulation
`endif
        repeat (4) @(negedge clk);   // stimulus is driven on the falling edge: no race with the DUT's rising-edge sampling
        rst = 0;
        repeat (2) @(negedge clk);
        for (pass = 0; pass < npass; pass = pass + 1) begin
            if (pass == 2) begin
                // abort the run with a ONE-cycle reset at many different moments (a sweep over more than one pixel period, so every
                // pipeline stage is caught holding live data); afterwards the engine must stay completely quiet
                for (j = 0; j < PER_X + 6; j = j + 1) begin
                    clear_output;
                    pulse_start;
                    repeat (3 * PER_X + j) @(negedge clk);
                    rst = 1; @(negedge clk); rst = 0;
                    idle_watch = 1;
                    repeat (2 * PER_X + 40) @(negedge clk);
                    idle_watch = 0;
                end
            end
            clear_output;
            pulse_start;
            wait_done;
            if (!ok) begin
                $display("FAIL layer %0d tile %0s: timeout (pass %0d)", LAYER, tile, pass);
                $finish;
            end
            compare;
            if (errors != 0) begin
                $display("FAIL layer %0d tile %0s: %0d wrong bytes (pass %0d)", LAYER, tile, errors, pass);
                $finish;
            end
            if (first_cycles < 0) first_cycles = cycles;
            else if (cycles != first_cycles) begin
                $display("FAIL layer %0d tile %0s: cycle count changed between runs (%0d vs %0d)", LAYER, tile, first_cycles, cycles);
                $finish;
            end
            repeat (3) @(negedge clk);
            if (busy || out_we) begin
                $display("FAIL layer %0d tile %0s: engine not idle after done (pass %0d)", LAYER, tile, pass);
                $finish;
            end
        end
        $display("PASS layer %0d tile %0s%0s: %0d pixels (%0dx%0d) x %0d ch bit-exact, %0d cycles (%0d per pixel, PERIOD %0d)%0s",
                 LAYER, tile, RAND ? " (randomized params)" : "", NOUT, OW, OH, C_OUT, first_cycles, first_cycles / NOUT, PER_X,
                 extra ? ", re-run + abort/recover OK" : "");
        $finish;
    end
endmodule
