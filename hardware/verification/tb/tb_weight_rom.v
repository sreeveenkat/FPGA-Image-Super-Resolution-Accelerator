// weight_rom.v + wrom_Ln.mem: the step-major ROM must hold exactly flat[(co, ci, ky, kx)] of the canonical weights_Ln.mem, for every
// layer shape.  Expected values are recomputed in the testbench from the flat file with the documented index formula.
`timescale 1ns/1ps
module tb_weight_rom;
    parameter LAYER = 1;
    localparam C_IN      = (LAYER == 1) ? 3 : 16;
    localparam C_OUT     = (LAYER == 4) ? 12 : 16;
    localparam K         = (LAYER == 3) ? 1 : 3;
    localparam DEPTHWISE = (LAYER == 2) ? 1 : 0;
    localparam CI_W      = DEPTHWISE ? 1 : C_IN;
    localparam STEPS     = K * K * CI_W;

    reg clk = 0;
    always #5 clk = ~clk;
    reg [$clog2(STEPS)-1:0] addr = 0;
    wire [8*C_OUT-1:0] q;
    weight_rom #(.C_IN(C_IN), .C_OUT(C_OUT), .K(K), .DEPTHWISE(DEPTHWISE),
                 .FILE({"hardware/rtl/weights/wrom_L", "0" + LAYER[7:0], ".mem"})) dut (.clk(clk), .addr(addr), .q(q));

    reg [7:0] flat [0:C_OUT*CI_W*K*K-1];
    integer s, co, ci, ky, kx, errors = 0;
    initial begin
        $readmemh({"hardware/rtl/weights/weights_L", "0" + LAYER[7:0], ".mem"}, flat);
        for (s = 0; s < C_OUT*CI_W*K*K; s = s + 1) if (^flat[s] === 1'bx) begin $display("FAIL weight_rom layer %0d: canonical weights file missing or short", LAYER); $finish; end
        for (s = 0; s < STEPS; s = s + 1) begin
            @(negedge clk); addr = s;
            @(negedge clk);   // q valid one clock after the address
            ci = s % CI_W; kx = (s / CI_W) % K; ky = s / (CI_W * K);
            for (co = 0; co < C_OUT; co = co + 1)
                if (q[8*co +: 8] !== flat[((co*CI_W + ci)*K + ky)*K + kx]) begin
                    errors = errors + 1;
                    if (errors < 5) $display("  step %0d (ky=%0d kx=%0d ci=%0d) co=%0d got %h expected %h", s, ky, kx, ci, co, q[8*co +: 8], flat[((co*CI_W + ci)*K + ky)*K + kx]);
                end
        end
        if (errors == 0) $display("PASS weight_rom layer %0d: %0d steps x %0d ch", LAYER, STEPS, C_OUT);
        else             $display("FAIL weight_rom layer %0d: %0d errors", LAYER, errors);
        $finish;
    end
endmodule
