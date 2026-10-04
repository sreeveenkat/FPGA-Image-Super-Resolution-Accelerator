# M5 tile core (`sr_tile_core`): simulated cycles, resources, timing, netlist simulation

Sources: `hardware/verification/run_tests.sh` (Icarus Verilog; `quick` and `full`), `hardware/verification/run_postsynth.sh` (Vivado xsim on the
synthesized netlist) and `hardware/vivado/scripts/synth_sr_tile_core.tcl` (Vivado 2024.1, out-of-context, xc7z020clg484-1, 10 ns clock).
Raw reports: `m5_core_{utilization,timing}.txt` (synthesis) and `m5_core_routed_{utilization,timing}.txt` (after place and route).
Caveats for every number: out-of-context run (clock constraint only, no I/O timing, no AXI/DMA wrapper), nothing measured on a board.

## What the core is
`sr_tile_core`: byte stream in (70x70x3 = 14,700 bytes) -> input loader -> ram0 -> L1 -> ram1 -> L2 -> ram2 -> L3 -> ram3 -> L4 -> ram4 ->
pixel shuffle + packer -> byte stream out (128x128x3 = 49,152 bytes). Four `conv_engine` instances (one per layer, run one after the other)
and one `tile_ram_split` activation RAM per layer boundary (no ping-pong).

## Cycles per tile (simulated, no stalls, 64x64 core tile)
| Item | Cycles |
|---|---|
| Whole tile, start to done (identical on all 9 golden tiles) | **926,197** |
| of which the four engines (M4) | 854,145 |
| of which byte-wide loading and output (difference) | 72,052 (about 14,700 load + 49,152 output bytes + about 8,200 RAM-fetch cycles; derived, not separately measured) |

Frame estimate for 960x540 (135 tiles, one after the other, byte-wide streams, no overlap between loading, compute and output):
135 x 926,197 = 125.0 M cycles = about **1.25 s at 100 MHz (~0.80 fps)**. Simulated cycle counting, NOT a board measurement; DMA and ARM time
(M6) are not included.

## Resources and timing, whole core (HC = 64)
| | LUT | FF | DSP48E1 | BRAM36 tiles | WNS @ 100 MHz | WHS |
|---|---|---|---|---|---|---|
| Synthesis | 2,028 | 3,337 | 68 (31 %) | 70 (50 %): 68 RAMB36 + 4 RAMB18 | +0.850 ns | +0.207 ns |
| After place and route | 1,900 (3.6 %) | 3,337 (3.1 %) | 68 | 70 | **+0.234 ns** | +0.081 ns |

* The same design routed to +0.146 ns before a two-line hygiene fix (reset of `cycles`, `out_last` gated by `out_valid`) and to +0.234 ns after it:
  placement noise alone moves the slack by about 0.1 ns, so treat the margin as FRAGILE, not as a guaranteed +0.234 ns.
* 0 failing endpoints, 0 routing errors, no latches, no ignored initial blocks; Vivado confirmed that all 12 weight/bias/multiplier files were read.
* The setup margin is thin (+0.234 ns). Critical path: `e1/res` / `e2/res` register mux (the worst endpoint moves between runs) -> requantizer DSP (8.3 ns of data path), the same path as in M4;
  registering the mux output would be the first fix (not done).
* **Activation memory:** the plain `tile_ram` needs 32 RAMB36 for one 4624x128-bit buffer because Vivado rounds the cascade depth up to a power
  of two. `tile_ram_split` (4096-deep part + remainder) needs 18.5 (4624x128), 16.5 (4356x128), 11 (4096x96) and 4 (4900x24), so the five buffers
  take about 66.5 of the 70 BRAM tiles (the rest are the weight ROMs). Naive mapping would have needed about 118 tiles.

## Post-synthesis simulation (HC = 6 geometry)
The synthesized core netlist passes the same testbench on the stream interface: tile small12 then small12b, re-run, abort sweep (6 aborts),
bit-exact, 10,957 cycles = identical to the RTL simulation. Internal buffers are not visible in a netlist, so only the output stream is checked there.
