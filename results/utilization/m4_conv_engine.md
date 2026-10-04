# M4 conv engine: simulated cycles, Vivado synthesis, place-and-route and post-synthesis simulation

Sources: `hardware/verification/run_tests.sh` (Icarus Verilog), `hardware/verification/run_postsynth.sh` (Vivado xsim on the synthesized
netlist) and `hardware/vivado/scripts/synth_conv_engine.tcl` (Vivado 2024.1, out-of-context, part xc7z020clg484-1, 10 ns clock).
Raw reports: `m4_conv_L<n>_{utilization,timing}.txt` (synthesis) and `m4_conv_L<n>_routed_{utilization,timing}.txt` (after place and route).

Caveats that apply to every number below: out-of-context runs (clock constraint only, no I/O timing, clock source property not set, so no
clock-skew estimation), one engine at a time, no activation RAMs, nothing measured on a board.

## Cycles for one 64x64-core tile (70x70 input), simulated, bit-exact with the integer model

| Layer | Steps / pixel | Cycles / pixel (PERIOD) | Output pixels | Cycles per tile |
|---|---|---|---|---|
| L1 conv3x3 3->16 | 27 | 27 | 68x68 = 4,624 | 124,871 |
| L2 depthwise3x3 16 | 9 | **16** (the shared requantizer needs 16 cycles/pixel) | 66x66 = 4,356 | 69,712 |
| L3 pointwise 16->16 | 16 | 16 | 66x66 = 4,356 | 69,719 |
| L4 conv3x3 16->12 | 144 | 144 | 64x64 = 4,096 | 589,843 |
| **Total** | | | | **854,145** |

The cycle counts are identical on every tile, on re-runs, and in the post-synthesis netlist simulation (data independent).
The M4 guide estimated about 196 cycles per input pixel; the engine needs 27 + 16 + 16 + 144 = 203 in steady state. Compute-only consequence for
a 960x540 frame (135 tiles, layers one after the other, no DMA/ARM/shuffle time): 135 x 854,145 = 115.3 M cycles = about **1.15 s at 100 MHz
(~0.87 fps)**. This is simulated cycle counting, NOT a board measurement.

## Resources and timing (one engine instance per layer, 64x64-core tile geometry)

| Layer | LUT (synth / routed) | FF | DSP48E1 | BRAM36 tiles | WNS synth | WNS routed | WHS routed |
|---|---|---|---|---|---|---|---|
| L1 | 389 / 360 | 850 | 18 | 2 | +0.850 ns | +0.135 ns | +0.128 ns |
| L2 | 431 / 397 | 952 | 18 | 0 | +0.850 ns | +0.261 ns | +0.100 ns |
| L3 | 424 / 361 | 840 | 18 | 0 | +0.821 ns | +0.582 ns | +0.111 ns |
| L4 | 358 / 347 | 692 | 14 | 1.5 | +0.938 ns | +0.698 ns | +0.147 ns |
| **All four** | **1,602 / 1,465 (2.8 %)** | **3,334 (3.1 %)** | **68 (31 %)** | **3.5 (2.5 %)** | | | |

* All four routed designs: 0 failing timing endpoints, 0 routing errors, 0 latches. Every layer meets 100 MHz with **the smallest margin in
  L1 (+0.135 ns)**; there is no room for 125-150 MHz without extra pipelining. In L1 and L2 the critical path is `rq_i` -> result-register mux -> requantizer DSP (8.4 ns of data path); registering the mux output (one extra requantizer stage) is the obvious first fix, not done.
* DSPs = one per MAC lane (C_OUT) + 2 for the shared 32x17-bit requantizer multiplier.
* **Activation buffer (measured):** a 70x70 x 128-bit `tile_ram` infers **32 RAMB36 (23 % of the chip)**, not the ~20 estimated in the guide
  (`m4_tile_ram_70x70x128_utilization.txt`). Two ping-pong buffers would take 64 of 140 BRAM36 (46 %); M5 solved this with a split RAM (about 18.5 tiles, see m5_tile_core.md)
  (for example a narrower/other word organisation, or one buffer per boundary only where needed).

## Post-synthesis functional simulation (the synthesized netlist itself)

`hardware/verification/run_postsynth.sh` writes a functional netlist per layer (small 12x12 tile geometry), and runs the SAME self-checking
testbench on it in xsim: normal run, immediate re-run, and the reset-abort sweep. Result: **4 of 4 bit-exact**, with the same cycle counts as
the RTL simulation (2723 / 1040 / 1047 / 5203). The testbench has to wait for the Xilinx global reset (`glbl.GSR`, first 100 ns) before
stimulating, otherwise the netlist ignores `start`.
This is the check that would have caught the ROM problem found earlier (a ROM initialisation that RTL simulation accepted but Vivado ignored).
