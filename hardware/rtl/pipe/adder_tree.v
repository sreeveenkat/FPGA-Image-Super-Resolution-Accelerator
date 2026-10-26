// Pipelined adder tree: sum of N signed inputs (each IW bits, sign-extended to OW bits), one register per tree level.
// Latency LV = clog2(N) cycles (inputs at cycle t -> sum from t+LV).  N >= 2.  Integer sums: the order does not change the result.
// One register vector per level (generate), filled by one clocked loop: an odd node count passes its last node through unchanged.
// (Written this way for simulation speed: many partial assigns into one wide net make Icarus ~30x slower.)
module adder_tree #(
    parameter N  = 9,
    parameter IW = 17,
    parameter OW = 24,
    parameter LV = $clog2(N)                  // do not override
) (
    input  wire              clk,
    input  wire [N*IW-1:0]   in,              // term j at bits j*IW +: IW
    output wire signed [OW-1:0] sum
);
    function integer cnt(input integer n, input integer lev);   // nodes on level `lev` (level 0 = the inputs)
        integer i, c;
        begin
            c = n;
            for (i = 0; i < lev; i = i + 1) c = (c + 1) / 2;
            cnt = c;
        end
    endfunction

    wire [(N+1)*IW-1:0] inx = {{IW{1'b0}}, in};   // one zero term past the end: no out-of-range select for odd N

    genvar l;
    generate
        for (l = 1; l <= LV; l = l + 1) begin : lev
            localparam integer C  = cnt(N, l);
            localparam integer CP = cnt(N, l - 1);
            reg [OW*C-1:0] v;
            integer j;
            if (l == 1) begin : g_first
                always @(posedge clk)
                    for (j = 0; j < C; j = j + 1)
                        v[j*OW +: OW] <= $signed({{(OW-IW){inx[(2*j)*IW+IW-1]}}, inx[(2*j)*IW +: IW]})
                                       + ((2*j + 1 < CP) ? $signed({{(OW-IW){inx[(2*j+1)*IW+IW-1]}}, inx[(2*j+1)*IW +: IW]}) : $signed({OW{1'b0}}));
            end else begin : g_next
                always @(posedge clk)
                    for (j = 0; j < C; j = j + 1)
                        v[j*OW +: OW] <= $signed(lev[l-1].v[(2*j)*OW +: OW])     // the second index is clamped: never past the previous level
                                       + ((2*j + 1 < CP) ? $signed(lev[l-1].v[((2*j + 1 < CP) ? 2*j + 1 : 2*j)*OW +: OW]) : $signed({OW{1'b0}}));
            end
        end
    endgenerate
    assign sum = lev[LV].v[OW-1:0];
endmodule
