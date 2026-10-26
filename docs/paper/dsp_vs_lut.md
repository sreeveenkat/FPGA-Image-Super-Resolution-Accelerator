# DSP vs LUT multipliers: one conv engine (layer 1)

Built 2026-10-26. One `conv_engine` instance, layer 1 (3 -> 16 channels, 3x3, 16 MAC lanes + one requantizer), RTL of the
`r3q_125` sandbox (R3q weights, the extra MAC input register of the 125 MHz design). Out-of-context synthesis + place + route with
`hardware/vivado/scripts/synth_conv_engine.tcl 1 8.0 impl` (8 ns = 125 MHz), plus `report_power` on the routed design. Three variants,
each a scratch copy of the RTL (nothing in the repo was changed; the edits are in `results/utilization/dsp_vs_lut/variants.diff`):

* **DSP**: as built (`(* use_dsp = "yes" *)` on `mac_unit`; the requantizer's 32x17 multiply goes to DSPs by default).
* **MAC in LUT**: `use_dsp = "no"` on `mac_unit` only; the requantizer stays on 2 DSPs.
* **All LUT**: as MAC in LUT, plus `synth_design -max_dsp 0` (no DSP anywhere, the requantizer multiply also in LUTs).

| Variant | LUT | FF | DSP | BRAM tile | Routed WNS at 8 ns | Fmax (= 1 / (8 ns - WNS)) | Power total / dynamic (W) |
|---|---|---|---|---|---|---|---|
| DSP | 322 | 883 | 18 | 1.5 | +1.798 ns | 161.2 MHz | 0.152 / 0.048 |
| MAC in LUT | 1,853 | 1,690 | 2 | 1.5 | +0.504 ns | 133.4 MHz | 0.139 / 0.035 |
| All LUT | 2,177 | 1,751 | 0 | 1.5 | -3.073 ns (29 failing endpoints) | 90.3 MHz | 0.148 / 0.045 |

Sources: `results/utilization/dsp_vs_lut/L1_{dsp,lutmac,lut}_{utilization,timing,power}_routed.txt`.

Reading:
* A 9x8-bit MAC lane in LUTs costs about (1,853 - 322) / 16 = **96 LUT and 50 FF more per lane** than in a DSP, and the engine still
  closes 125 MHz (+0.504 ns). The critical path moves from control (`last_d2` -> result register enable) to the weight ROM -> LUT
  multiplier (`waddr_r` -> `lane[0].u_mac/prod_reg`).
* The requantizer multiply (32 x 17 bits) is what breaks timing without DSPs: the all-LUT critical path is `rq_acc_r` -> `u_rq/p1_reg`
  (19 logic levels, 15 CARRY4). Keep the requantizers on DSPs.
* Power: the three estimates lie within 13 mW of each other (vectorless, default toggle rates, out of context, confidence Medium). Device
  static power (0.103 W) is the same in all three, so the differences are in dynamic power, and that is within what the
  estimator can resolve at these toggle assumptions. Do not read a power ranking from this table. It is an estimate, not a measurement.
* Consequence for a bigger design: the 220 DSPs are not a hard ceiling. At ~96 LUT per extra lane, 100 extra LUT lanes would cost
  ~10k of the 53,200 LUTs, but each one is slower than a DSP lane (Fmax 133 vs 161 MHz in this engine). The Phase 2 design
  (`docs/ARCHITECTURE_PIPELINE.md`) stays within the DSPs.

Limits: one engine (layer 1) only, out of context (no I/O timing, no system around it), one place-and-route run per variant
(placement noise ~0.1 ns was seen before on this design).
