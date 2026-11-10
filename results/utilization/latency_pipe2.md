# Latency of the pipeline accelerators (simulation, 2026-11-10)

Measured in `tb_sr_pipe_top.v` (new INFO line): CYCLES count at the first accepted input beat and at the first accepted output beat of a frame
(RTL simulation, Icarus 12, no stalls). Frame `pw960x24` (960 x 24 LR): the latency depends on the frame WIDTH only (the first HR rows need
the first ~5 padded LR rows through all four layers), so it equals the 960x540 latency. Logs: `~/Desktop/venkat/pipe2_artifacts/latency/`.

| Design | Input -> first output beat | at 125 MHz | Whole 960x540 frame (cycles / board) |
|---|---|---|---|
| `pipe` (NS = 16, board-tested) | 79,181 cycles | **0.63 ms** | 8,398,481 cycles = 67.2 ms compute; board 95.36 ms |
| `pipe2` (NS = 8) | 40,592 cycles | **0.32 ms** | 4,203,124 cycles = 33.6 ms compute; board not measured |

Both frames bit-exact in the same runs. 40,592 / (966 x 8) = 5.25 padded rows: the latency is set by the line buffers of the three 3x3 layers plus
the two-HR-row output buffer, not by the frame size.

Limits: accelerator latency (first input beat to first output beat), simulated. In the system as built the ARM pads the WHOLE frame before the
DMA starts (3.3 ms non-cacheable / 5.8 ms cached, board-measured for `pipe`) and the output lands in DDR, so the end-to-end latency of the
present ARM program is pad + about one frame. A streaming source (camera, video input) with on-the-fly padding would see the accelerator latency.
Not measured on the board.
