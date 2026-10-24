# Plan: raise the fabric clock above 100 MHz (PROPOSAL ONLY, 2026-10-24; no RTL was edited, nothing was built)

Based on the stored reports of the 152.38 MHz trial: `results/utilization/timing_150mhz/` (README there) and `docs/paper/timing_150mhz.md`. Everything marked *estimate* is arithmetic on those stored numbers and has not been
synthesized. Whether to build it, and in which sandbox, is the owner's decision.

## 1. What the stored paths say
* 434 of the 580 failing endpoints (worst **-1.693 ns**) are one path type: activation RAM (`ramN/mem_lo_reg`, RAMB36E1, clock-to-output 2.454 ns) -> `sel_hi` mux in `tile_ram_split` -> the engine's channel select
  `in_data[8*ci1 +: 8]` (LUT6 + MUXF7 + LUT6, fan-out 12) -> **A pin of the MAC's DSP48E1**. That pin has no input register in the current RTL, so it needs **1.928 ns** setup.
  For comparison, in the same checkpoint: a DSP input with its own register (the requantizer) needs 0.362 ns, a fabric flip-flop 0.062 ns (`path_rq_to_dsp.txt`, `path_to_fdre.txt`).
* After this class the next worst is inside the Xilinx AXI DMA (-0.885 ns, `sig_btt_eq_0_reg`), then the requantizer feed (-0.392 ns), our AXI-Lite reset fan-out (-0.174 ns), weight ROM -> DSP B (-0.153 ns), `ram4` -> `ow_reg` (-0.091 ns).

## 2. Where one register goes (RAM -> mux -> MAC)
File `hardware/rtl/conv_engine/conv_engine.v`, in the block "stages 2-3: MAC lanes" (generate loop `lane`), between the channel select and `mac_unit`:
```
// today:   a_co = in_data[8*ci1 +: 8]      (or in_data[8*co +: 8] for the depthwise layer)   -> mac_unit.a   (DSP A pin, no input register)
// proposed: always @(posedge clk) a_r <= a_co;   -> mac_unit.a = a_r                          (Vivado can absorb it into the DSP's A register)
```
Because the activation arrives one cycle later, three things move by one cycle so that data, weight and control stay aligned (all inside the same module):
1. the weight ROM address `issue ? step : 0` is delayed by one cycle (a few flip-flops; cheaper than delaying the 8*C_OUT-bit weight vector, which would be 96-128 FF per engine),
2. `v1` / `first1` are delayed by one cycle (2 FF),
3. the `last_d1 / last_d2` chain that says "final accumulators are visible" gets one more stage.

`mac_unit.v` and the requantizer stay unchanged. The register is the same kind of change as the 2026-10-09 stage in front of the requantizer (+1 cycle per engine run, throughput unchanged).

## 3. Cost
| Item | Estimate (not built) |
|---|---|
| Cycles per tile | **+4** (+1 per engine run x 4 engines): 926,201 -> 926,205 in simulation; the 2026-10-09 stage of the same kind went 926,197 -> 926,201 |
| Frame time at 100 MHz | unchanged within 0.01 ms (135 x 4 cycles = 5.4 us) |
| Fabric FF | 0 if Vivado absorbs the register into the DSP A register; otherwise at most about 8 FF per broadcast engine (L1, L3, L4), 128 FF for the depthwise engine (16 lanes x 8), plus about 10 per engine for the delayed ROM address and control: **below 250 FF in total (about 3 % of 7,831)** |
| LUT / BRAM / DSP | 0 / 0 / 0 |

## 4. Predicted timing effect (estimate: stored slack + changed setup, placement assumed unchanged)
Replacing the A-pin setup 1.928 ns by 0.362 ns (register absorbed) gains **1.566 ns**; by 0.062 ns (separate fabric register) 1.866 ns.

| Clock | Period | Worst RAM->A path today | With one register (absorbed) | Next limit (stored classes) |
|---|---|---|---|---|
| 125 MHz (IO PLL 1000 MHz / 8: exactly reachable, inferred from the 142.86 MHz the IO PLL gave for a 150 MHz request) | 8.000 ns | -1.693 + 1.438 = **-0.255 ns** (engine 4), -0.180 (engine 3), engines 1-2 positive | -0.255 + 1.566 = **+1.31 ns** | AXI DMA +0.553 ns (-0.885 + 1.438) |
| 152.38 MHz (what the trial used) | 6.562 ns | -1.693 ns | **-0.127 ns** (engine 4), -0.052 (engine 3) | AXI DMA -0.885 ns |
| 150 MHz | 6.667 ns | -1.588 ns | about **-0.02 ns** | AXI DMA about -0.78 ns |

Not modelled: a different PLL setting also changes clock uncertainty and skew, and a new placement changes every route delay (the 100 MHz builds of this project moved by +-0.1 ns between placements).

So **125 MHz looks reachable with this one register** (every stored failing class is positive by estimate; the smallest margin is the DMA IP at about +0.5 ns). **150 MHz does not**:
the one register leaves the RAM->A path at about 0, and the DMA IP still fails by about 0.8 ns. Options for 150 MHz, none tried:
(a) a second register (separate fabric flip-flop after the mux, plus the absorbed A register: +2 cycles per run), which would also need a look at the 2.454 ns RAM clock-to-output (output register, read latency 2);
(b) the DMA: its failing registers `sig_btt_cntr_reg[17..25]` and `sig_btt_eq_0_reg` belong to the 26-bit byte counter (`c_sg_length_width {26}` in `design_1_m6.tcl`); one tile is at most 49,152 bytes = 16 bits, so a narrower length register is a hypothesis worth trying (and another implementation strategy);
(c) the requantizer feed (-0.392 ns): one more register after the result mux.

## 5. Predicted speed (model, `software/analysis/fmax_prediction.py`, same convention as `cycle_model.py` Part 3: overhead 61.5 ms held constant)
| Clock | Cycles per tile | Frame time | fps |
|---|---|---|---|
| 100 MHz, today (board-measured 1,311.9 ms) | 926,220 | 1,311.9 ms | 0.762 |
| 100 MHz, +4 cycles per tile (predicted) | 926,224 | 1,311.9 ms | 0.762 |
| 125 MHz, +4 cycles per tile (predicted) | 926,224 | 1,061.8 ms | 0.942 |
| 150 MHz, +4 cycles per tile (predicted) | 926,224 | 895.1 ms | 1.117 |

Tiles per frame 135; overhead held at 61.5 ms (ARM padding + copies + DMA handshakes, as measured at 100 MHz).

Reading: 125 MHz would give about **0.94 fps** (+24 %), 150 MHz about **1.12 fps** (+47 %) if everything closed. These are small next to the architecture changes in `cycle_model.md` (layer pipeline about 3.9 fps, shared engine 2.2-3.9 fps, also predictions): a faster clock alone does not change the main problem (only one of four engines busy, 17.2 % DSP utilization).
The ARM/DMA overhead is held constant, which is conservative for the DMA part and exact for the ARM copy and padding.

## 6. If the owner decides to build it
* New worktree/branch off `main` (not in `main`, not touching the deployed bitstream); change only `conv_engine.v` (and `block design` clock: FCLK0 125 MHz from the IO PLL, remove the `FREQ_HZ 100000000` text from `sr_accel_top.v`'s X_INTERFACE_PARAMETER or set it to the new value).
* Check list: `run_tests.sh quick` and `full` (cycles per tile change by +4, so every cycle-count check in the testbenches must be updated and the new numbers explained), `run_postsynth.sh`, the mutation study quick suite (`docs/paper/mutation_study.md`), Vivado at 125 MHz (WNS must be positive; save the reports under `results/utilization/`), then the board checklist (T1, T2 byte-exact 0xcf947f22 for the same weights, 119 images, 20-frame timing) with a new VERSION value.
* Not analysed here: PS-PL interface timing at 125 MHz (everything uses `FCLK_CLK0`, no clock-domain crossing), board power at the faster clock (more switching), and that the ARM/DMA part may change with the clock.
