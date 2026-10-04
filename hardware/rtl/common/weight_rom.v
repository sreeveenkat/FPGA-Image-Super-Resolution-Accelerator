// Weight ROM of one conv layer (M4), step-major so ONE read gives the weights of every output channel for one step.
//   FILE      : wrom_Ln.mem, derived from the canonical weights_Ln.mem ([co][ci][ky][kx], one int8 per line) by export_rtl.py:
//               line s = step (ky*K + kx)*CI_W + ci   (CI_W = 1 for depthwise, else C_IN),
//               value  = C_OUT*8 bits, channel co at bits [8*co +: 8], written as hex digits (channel 0 = rightmost byte)
// Loaded with a plain $readmemh (synthesizable). NOTE: an `initial` loop that rearranges a flat file is silently IGNORED by Vivado
// (Synth 8-311), which is why the rearrangement is done by the exporter and checked by tb_weight_rom / test_export.
// Synchronous read, 1-cycle latency.
module weight_rom #(
    parameter C_IN      = 3,
    parameter C_OUT     = 16,
    parameter K         = 3,
    parameter DEPTHWISE = 0,
    parameter FILE      = "wrom.mem",
    parameter STEPS     = K * K * (DEPTHWISE ? 1 : C_IN),
    parameter AW        = (STEPS > 1) ? $clog2(STEPS) : 1
) (
    input  wire                clk,
    input  wire [AW-1:0]       addr,
    output reg  [8*C_OUT-1:0]  q
);
    reg [8*C_OUT-1:0] rom [0:STEPS-1];
    initial $readmemh(FILE, rom);

    always @(posedge clk) q <= rom[addr];
endmodule
