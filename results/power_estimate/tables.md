# Vivado power estimates (NOT measured)

Total on-chip power, W, and breakdown (W). PS7 = the Zynq processing system as Vivado models it (not our design).

| Run | Total | Dynamic | Static | Clocks | Slice Logic | Signals | BRAM | DSP | I/O | PS7 | Confidence | Nets matched (design) | Nets matched (core instance) |
|---|---|---|---|---|---|---|---|---|---|---|---|---|---|
| pipe vectorless | 2.290 | 2.128 | 0.162 | 0.058 | 0.096 | 0.154 | 0.022 | 0.235 | 0.0005 | 1.564 | Low | NA | NA |
| r0 vectorless | 1.913 | 1.758 | 0.155 | 0.025 | 0.009 | 0.025 | 0.081 | 0.056 | 0.0005 | 1.562 | Low | NA | NA |
| pipe RTL SAIF (400k cycles) | 2.213 | 2.053 | 0.160 | 0.058 | 0.082 | 0.123 | 0.017 | 0.210 | 0.0005 | 1.564 | Low | 25%   (9680/38954) | 32% (9678/29963) |
| r0 RTL SAIF (whole tile) | 1.904 | 1.750 | 0.155 | 0.025 | 0.009 | 0.022 | 0.080 | 0.052 | 0.0005 | 1.562 | Low | 7%   (1488/20821) | 13% (1486/11313) |
| r0 post-impl SAIF (5 windows, whole tile) | 1.903 | 1.749 | 0.155 | 0.025 | 0.009 | 0.020 | 0.089 | 0.044 | 0.0005 | 1.562 | Low | 13%   (2664/20821) | 24% (2662/11313) |
| pipe post-impl SAIF (2 windows, 150k cycles) | 2.219 | 2.059 | 0.160 | 0.059 | 0.085 | 0.134 | 0.017 | 0.202 | 0.0005 | 1.564 | Low | 67%   (26250/38954) | 88% (26248/29963) |
| pipe3 vectorless | 2.685 | 2.508 | 0.177 | 0.105 | 0.151 | 0.336 | 0.056 | 0.296 | 0.0005 | 1.565 | Low | NA | NA |
| pipe3 RTL SAIF (300k cycles) | 2.661 | 2.485 | 0.176 | 0.100 | 0.154 | 0.329 | 0.030 | 0.307 | 0.0005 | 1.565 | Low | 25%   (13537/54342) | 30% (13535/45835) |
| pipe3 post-impl SAIF (3 windows, 225k cycles) | 2.691 | 2.513 | 0.178 | 0.101 | 0.157 | 0.355 | 0.029 | 0.306 | 0.0005 | 1.565 | Low | 73%   (39614/54342) | 86% (39612/45835) |
| pipe4 vectorless | 3.059 | 2.865 | 0.194 | 0.173 | 0.309 | 0.466 | 0.054 | 0.299 | 0.0005 | 1.565 | Low | NA | NA |
| pipe4 RTL SAIF (300k cycles) | 2.863 | 2.678 | 0.185 | 0.175 | 0.249 | 0.394 | 0.046 | 0.248 | 0.0005 | 1.565 | Low | 15%   (13606/91457) | 16% (13604/83324) |
| pipe4 post-impl SAIF (1 window, 75k cycles) | 3.013 | 2.822 | 0.192 | 0.177 | 0.275 | 0.494 | 0.053 | 0.259 | 0.0005 | 1.565 | Low | 55%   (50121/91457) | 60% (50119/83324) |

Per window (post-implementation netlist SAIF), total W: R0 w1 1.907, w2 1.910, w3 1.900, w4 1.900, w5 1.900; pipeline w1 2.219, w2 2.219; pipe3 w1 2.689, w2 2.693, w3 2.692; pipe4 w1 3.013

## Energy per frame (Vivado estimate, not measured)

E = P x t with the board frame times of 2026-10-28 (pipeline 95.4 ms and 70.5 ms, R0 1,312.5 ms) and 2026-11-18 (pipe3 29.44 / 51.45 ms, pipe4 22.10 / 44.11 ms). 'PL' = total on-chip minus PS7 (includes the device static power); 'PL dynamic' = dynamic minus PS7.
P_active = the power with the simulated activity (compute phase). 'Simple' assumes P_active for the whole frame; 'refined' uses P_active only while the core computes (core time / frame time) and P_idle = P_active minus the dynamic power of slice logic, signals, BRAM and DSP for the rest.

| Case | Power source | Frame ms | P_total W | E_total mJ | P_PL W | E_PL mJ | P_PL dynamic W | E_PL dynamic mJ | refined E_total mJ | refined E_PL mJ |
|---|---|---|---|---|---|---|---|---|---|---|
| Pipeline (default build) | pipe vectorless | 95.4 | 2.290 | 218 | 0.726 | 69 | 0.564 | 53.8 | 204 | 55 |
| Pipeline (default build) | pipe post-impl SAIF | 95.4 | 2.219 | 212 | 0.655 | 62 | 0.495 | 47.2 | 199 | 50 |
| Pipeline (non-cacheable DMA buffers) | pipe vectorless | 70.5 | 2.290 | 161 | 0.726 | 51 | 0.564 | 39.8 | 160 | 50 |
| Pipeline (non-cacheable DMA buffers) | pipe post-impl SAIF | 70.5 | 2.219 | 156 | 0.655 | 46 | 0.495 | 34.9 | 155 | 45 |
| R0 (100 MHz) | r0 vectorless | 1312.5 | 1.913 | 2511 | 0.351 | 461 | 0.196 | 257.2 | 2500 | 450 |
| R0 (100 MHz) | r0 post-impl SAIF | 1312.5 | 1.903 | 2498 | 0.341 | 448 | 0.187 | 245.3 | 2488 | 438 |
| pipe3 (non-cacheable, PL padding) | pipe3 vectorless | 29.44 | 2.685 | 79 | 1.120 | 33 | 0.943 | 27.8 | 79 | 33 |
| pipe3 (non-cacheable, PL padding) | pipe3 post-impl SAIF | 29.44 | 2.691 | 79 | 1.126 | 33 | 0.948 | 27.9 | 79 | 33 |
| pipe3 (cached) | pipe3 vectorless | 51.45 | 2.685 | 138 | 1.120 | 58 | 0.943 | 48.5 | 120 | 39 |
| pipe3 (cached) | pipe3 post-impl SAIF | 51.45 | 2.691 | 138 | 1.126 | 58 | 0.948 | 48.8 | 120 | 39 |
| pipe4 (non-cacheable, PL padding) | pipe4 vectorless | 22.1 | 3.059 | 68 | 1.494 | 33 | 1.300 | 28.7 | 68 | 33 |
| pipe4 (non-cacheable, PL padding) | pipe4 post-impl SAIF | 22.1 | 3.013 | 67 | 1.448 | 32 | 1.257 | 27.8 | 67 | 32 |
| pipe4 (cached) | pipe4 vectorless | 44.11 | 3.059 | 135 | 1.494 | 66 | 1.300 | 57.3 | 110 | 41 |
| pipe4 (cached) | pipe4 post-impl SAIF | 44.11 | 3.013 | 133 | 1.448 | 64 | 1.257 | 55.4 | 109 | 40 |
