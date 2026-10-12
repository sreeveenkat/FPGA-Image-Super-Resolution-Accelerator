# M6 - in-system Vivado build `m6_sr` (PS7 + AXI DMA + `sr_accel_top_0`)

Vivado project `/home/sreevenkat/Desktop/venkat/vitis/m6_sr`, block design with the Zynq PS7, AXI DMA and `sr_accel_top_0`, `FCLK_CLK0` = 100 MHz.
`sr_accel_top_0/s_axi` is at 0x4000_0000 (4K); full address map in `docs/REGISTER_MAP.md`.
**These are Vivado post-implementation numbers as reported by the owner. Nothing here was measured on a board.**

## Results of the in-system build
| Item | Value |
|---|---|
| Setup slack (WNS) | **+0.239 ns**, TNS 0 |
| Hold slack (WHS) | **+0.023 ns** |
| Failing endpoints | 0 of 23,269 |
| LUT | 5,146 (9.67 %), of which LUTRAM 240 |
| FF | 7,605 (7.15 %) |
| Block RAM tiles | 72 (51.43 %) |
| DSP48 | 68 (30.91 %) |
| BUFG | 1 |
| Estimated on-chip power | 1.919 W (Vivado estimate, confidence **Low**) |
| DRC | 111 warnings, 2 advisories (no errors reported) |
| Weights | all 12 `.mem` files "read successfully" (Synth 8-3876) from the absolute WDIR path |

## Compared with the out-of-context build of the top alone (`m6_top.md`, 100 MHz, same RTL)
| | `sr_accel_top` alone (OOC) | whole system (PS7 + DMA + top) | difference |
|---|---|---|---|
| LUT | 1,988 | 5,146 | +3,158 (DMA, interconnects, reset, glue) |
| FF | 3,479 | 7,605 | +4,126 |
| BRAM tiles | 70 | 72 | +2 |
| DSP | 68 | 68 | 0 (all DSPs are the CNN) |
| WNS (ns) | +0.677 | +0.239 | -0.438 |
| WHS (ns) | +0.085 | +0.023 | -0.062 |
| Power estimate | 0.279 W (no PS, no I/O, confidence medium) | 1.919 W (includes the PS7, confidence low) | not comparable |

## Notes
* Same DSP count (68) and almost the same BRAM count (70 -> 72) confirm that the weights loaded in the full design as well; the +2 BRAM tiles are not explained by this record (probably the DMA).
* Timing is met at 100 MHz but with a thin margin, especially hold (+0.023 ns); a different placement can move it by 0.1 ns or more (seen before on the core). Re-check WNS/WHS after every rebuild.
* The power figure includes the PS7 and is a low-confidence estimate; do not quote it as measured power.
* The DRC warnings were not inspected here.
