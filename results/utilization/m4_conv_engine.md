# M4 conv engine: simulated cycles, Vivado synthesis, place-and-route and post-synthesis simulation

Sources: `hardware/verification/run_tests.sh` (Icarus Verilog), `hardware/verification/run_postsynth.sh` (Vivado xsim on the synthesized
netlist) and `hardware/vivado/scripts/synth_conv_engine.tcl` (Vivado 2024.1, out-of-context, part xc7z020clg484-1, 10 ns clock).
Raw reports: `m4_conv_L<n>_{utilization,timing}.txt` (synthesis) and `m4_conv_L<n>_routed_{utilization,timing}.txt` (after place and route).

Caveats that apply to every number below: out-of-context runs (clock constraint only, no I/O timing, clock source property not set, so no
clock-skew estimation), one engine at a time, no activation RAMs, nothing measured on a board.

## Cycles for one 64x64-core tile (70x70 input), simulated, bit-exact with the integer model

| Layer | Steps / pixel | Cycles / pixel (PERIOD) | Output pixels | Cycles per tile |
|---|---|---|---|---|
| L1 conv3x3 3->16 | 27 | 27 | 68x68 = 4,624 | 124,872 |
| L2 depthwise3x3 16 | 9 | **16** (the shared requantizer needs 16 cycles/pixel) | 66x66 = 4,356 | 69,713 |
| L3 pointwise 16->16 | 16 | 16 | 66x66 = 4,356 | 69,720 |
| L4 conv3x3 16->12 | 144 | 144 | 64x64 = 4,096 | 589,844 |
| **Total** | | | | **854,149** |

The cycle counts are identical on every tile, on re-runs, and in the post-synthesis netlist simulation (data independent).
The M4 guide estimated about 196 cycles per input pixel; the engine needs 27 + 16 + 16 + 144 = 203 in steady state. Compute-only consequence for
a 960x540 frame (135 tiles, layers one after the other, no DMA/ARM/shuffle time): 135 x 854,149 = 115.3 M cycles = about **1.15 s at 100 MHz
(~0.87 fps)**. This is simulated cycle counting, NOT a board measurement.

## Resources and timing (one engine instance per layer, 64x64-core tile geometry)

| Layer | LUT (synth / routed) | FF | DSP48E1 | BRAM36 tiles | WNS synth | WNS routed | WHS routed |
|---|---|---|---|---|---|---|---|
| L1 | 310 / 298 | 851 | 18 | 2 | +4.255 ns | +3.853 ns | +0.131 ns |
| L2 | 432 / 398 | 953 | 18 | 0 | +4.255 ns | +3.393 ns | +0.138 ns |
| L3 | 432 / 369 | 841 | 18 | 0 | +4.255 ns | +2.913 ns | +0.097 ns |
| L4 | 359 / 349 | 693 | 14 | 1.5 | +4.255 ns | +3.146 ns | +0.144 ns |
| **All four** | **1,533 / 1,414 (2.7 %)** | **3,338 (3.1 %)** | **68 (31 %)** | **3.5 (2.5 %)** | | | |

* All four routed designs: 0 failing timing endpoints, 0 routing errors, 0 latches. Every layer meets 100 MHz; the smallest margin is
  in L3 (+2.913 ns). **Timing fix (2026-10-09):** the critical path used to be `rq_i` -> result-register mux -> requantizer DSP (8.4 ns of data path, slack
  +0.135 / +0.261 / +0.582 / +0.698 ns for L1..L4). One register stage after that mux (`rq_acc_r`, `rq_m_r`, `rq_tag_r`, `rq_v_r` in `conv_engine.v`) gave the slacks in the table
  at the price of one extra cycle per run (the cycle counts above include it: previously 124,871 / 69,712 / 69,719 / 589,843). The 100 MHz target now has large
  margin per engine; the cheapest remaining limit is the DSP multiply itself, so 125-150 MHz may be possible but was NOT tried.
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
