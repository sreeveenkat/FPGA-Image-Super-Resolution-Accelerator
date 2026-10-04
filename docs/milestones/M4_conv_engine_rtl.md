# M4 — One Convolution Layer in Verilog (the Conv Engine)

**Time:** 2–3 weeks | **Where:** PC (simulation first), then Vivado | **Depends on:** M3 (golden model + test vectors)

---

## 1. Why this milestone exists

This is where the FPGA design starts. We build **one** configurable convolution engine and prove it matches the Python
integer model **bit for bit**. Only then do we reuse it for every layer in M5.

Why one layer first? If you wire five layers at once and the image is wrong, you cannot tell which layer is at fault.
One layer + exact comparison = bugs are found in minutes, not days.

---

## 2. The most important design decision: we cannot do one pixel per clock

Count the maths: **2,560 MACs per input pixel**. A DSP slice does 1 MAC per clock, and we only have 220. Doing one pixel per
clock would need ~2,560 multipliers. We do not have them.

So the hardware **reuses a small number of multipliers over many clock cycles** ("folding"). Each pixel takes tens to
hundreds of cycles. That is fine: it just sets the frame rate.

### Architecture choice: "tile engine" (simple and beginner-friendly)

Instead of a complex streaming pipeline with line buffers, we:
1. Load one **tile** of the image into on-chip BRAM.
2. Run **layer 1** on the whole tile, writing results to a second BRAM.
3. Run **layer 2** reading that BRAM, writing to the first one (ping-pong), and so on.
4. Send the finished tile out.

```
 tile in ─► [BRAM A] ─layer1─► [BRAM B] ─layer2─► [BRAM A] ─layer3─► [BRAM B] ─layer4─► out
                          ▲ same conv engine, reused with different weights/settings
```

This is easier to get right than a line-buffer pipeline, uses little memory (see sizing below), and the halo handling in
M5 becomes simple geometry.

---

## 3. Engine design (version 1)

### Data layout in BRAM
Store activations **pixel-major**: one memory word = all channels of one pixel.
- 16 channels × 8 bits = **128-bit word** per pixel (layer 1 input: 3 × 8 = 24 bits, padded).
- Address = `y × tile_width + x`.

Why: one read gives you every channel of a pixel at once, which is what the engine needs.

### Compute organisation: "broadcast one input, many outputs"
For a 3×3 conv with `C_in` inputs and `C_out` outputs, for one output pixel:

```
for each (ky, kx, ci):              # C_in·9 steps
    a = activation[y+ky][x+kx][ci]  # ONE value, read once
    for every output channel co IN PARALLEL:   # P MAC units
        acc[co] += a * weight[co][ci][ky][kx]
```
- P MAC units = P DSP slices. Version 1: **P = 16** (all output channels at once).
- Cycles per output pixel = number of (ky,kx,ci) steps.

| Layer | Steps/pixel | Parallel MACs used |
|---|---|---|
| L1 conv 3→16 | 27 | 16 |
| L2 depthwise 16 | 9 (each MAC works on its own channel) | 16 |
| L3 pointwise 16→16 | 16 | 16 |
| L4 conv 16→12 | 144 | 12 |
| **Total** | **≈ 196 cycles per input pixel** | *(design estimate; measured 203 because the depthwise layer takes 16, see section 4b)* |

At 100 MHz, 960×540 (518,400 pixels): 518,400 × 196 ≈ 102 M cycles ≈ **~1 s per frame (~1 fps)**.
That is slow but **correct**, and it is only version 1. Once it is verified you can raise P (see Section 8). All numbers here are my estimates.

### Block diagram

```
          ┌────────────┐   addr   ┌───────────────┐
 control ►│  FSM       │─────────►│ activation    │ 128-bit word
 (layer   │ (loops over│          │ BRAM (read)   │──┐
  cfg)    │  x,y,tap,ci)│         └───────────────┘  │  pick channel ci → 8-bit "a"
          │            │   addr   ┌───────────────┐  │
          │            │─────────►│ weight ROM    │──┼─► P weights (8-bit each)
          └─────┬──────┘          └───────────────┘  │
                │                       ┌────────────▼──────────┐
                │                       │ P × MAC (acc int32)   │
                │                       └────────────┬──────────┘
                │                       + bias → requant (M, SHIFT, round, clamp)
                │                                    │
                │                       ┌────────────▼──────────┐
                └──────── write addr ──►│ output BRAM (write)   │
                                        └───────────────────────┘
```

### The MAC unit (Verilog sketch)
```verilog
// activation is unsigned 8-bit (after ReLU); weight is signed 8-bit
wire signed [8:0]  a_s = {1'b0, act};
wire signed [16:0] prod = a_s * w;           // Vivado infers a DSP48
always @(posedge clk) begin
    if (clear)       acc <= bias;            // start from bias (int32)
    else if (en)     acc <= acc + prod;
end
```

### Requantization (turn the 32-bit accumulator back into 8 bits)
```
y = (acc * M + (1 << (SHIFT-1))) >>> SHIFT      // arithmetic shift, round to nearest
y = clamp(y, lo, hi)                             // ReLU layers: lo = 0, hi = 255
```
`acc * M` is 32×16 bits, which does not fit one DSP48 (25×18). **Trick:** you only need it once per output pixel, so use
**one shared requant unit** and process the P channels one after another (P cycles, negligible next to ~196). It saves DSPs.

### Borders
In this milestone you may **zero-pad** or use "valid" convolution (output shrinks by 2 px). M5 uses valid convolution on
tiles that include a halo. Choose now and make the Python reference do the same thing.

### Memory estimate
Tile of 70×70 pixels × 16 B = 78 KB per buffer; ≈ 20 BRAM36 each (my estimate; **measured: 32 for a 70×70×128-bit buffer**, see section 4b); two buffers ≈ 40 of 140 (measured ≈ 64). Weights: ~2.6 KB
(tiny). Fits comfortably.

---

## 4. Step-by-step

### Step 1 — Fix the interface and the golden vectors
Write on paper: bit widths, memory layout (pixel-major, channel order), weight layout `[co][ci][ky][kx]`,
M/SHIFT/bias per layer. They must match the exported files from M3.

### Step 2 — Build the pieces, each with its own testbench
1. `mac_unit.v` — test with random and extreme values (−128×255, etc.).
2. `requant.v` — compare with Python for random accumulators, including rounding ties and saturation.
3. `tile_ram.v` — simple dual-port RAM (write one address, read another). Vivado infers BRAM from the standard coding style.
4. `weight_rom.v` — `initial $readmemh("weights_L1.mem", mem);`

### Step 3 — Build the conv FSM
Loops: `for y { for x { clear acc ← bias; for tap/ci { read, MAC }; requant each channel; write } }`.
Start with the **smallest case**: a 3→16 layer on a 8×8 tile. Parameterize: `C_IN`, `C_OUT`, `KSIZE` (1 or 3), `DEPTHWISE`.

### Step 4 — Verify against Python with cocotb (done with self-checking Verilog testbenches + Icarus instead, see section 4b)
```python
# pseudo-test
z    = np.load("data/golden/small12.npz")   # made by software/ai/quantization/export_rtl.py (keys: tile, L1..L4, out)
inp  = z["tile"]                            # uint8 (h+6, w+6, 3), halo included; same data as small12_in.hex
exp  = z["L1"]                              # (16, h+4, w+4) from integer_reference.py; small12_L1.hex is the same, [y][x][c]
dut_out = await run_dut(inp)
assert (dut_out == exp).all()               # bit-exact
```
Test: random input, all zeros, all 255, a single bright pixel, saturation cases, weights at ±127/−128.

### Step 5 — Synthesize the engine alone
In Vivado: Run Synthesis on the engine as top. Read the utilization report and check:
DSP usage ≈ P, BRAM as expected, no inferred latches, timing at 100 MHz.

---

## 4b. Results achieved (2026-10-04)

What was built:

| File | Purpose |
|---|---|
| `hardware/rtl/common/mac_unit.v` | One MAC lane: `acc <= (first ? bias : acc) + a*w`, 2 pipeline stages, forced onto a DSP48 |
| `hardware/rtl/common/requant.v` | `(acc*M + 2^(SHIFT-1)) >>> SHIFT`, clamp 0..255, 3 stages, tag passthrough |
| `hardware/rtl/common/tile_ram.v` | Simple dual-port RAM, 1-cycle read (infers block RAM) |
| `hardware/rtl/common/weight_rom.v` | Step-major weight ROM, loaded with `$readmemh` from `wrom_Ln.mem` |
| `hardware/rtl/conv_engine/conv_engine.v` | The engine: parameters `C_IN, C_OUT, K, DEPTHWISE, IN_W, IN_H, SHIFT` + 3 files; VALID convolution |
| `hardware/verification/tb/*.v`, `run_tests.sh` | Self-checking testbenches and the regression runner |
| `hardware/vivado/scripts/synth_conv_engine.tcl` | Out-of-context synthesis (+ `impl` place&route, `small` post-synthesis netlist) of one layer |
| `hardware/verification/run_postsynth.sh` | Simulates the synthesized netlists with xsim |
| `software/ai/quantization/gen_unit_vectors.py` | Requant vectors + randomized layer tests from the Python golden model |

Design decisions (differences from the sketch above):
* **One engine instance per layer** (compile-time parameters), not one runtime-reconfigurable engine. The M5 sequencer just starts them in
  order. Cost: 68 DSPs for all four instead of 18; the DSP budget is 220, so this was chosen for simplicity.
* **Overlapped requantizer.** The shared requantizer works on pixel n while the MAC lanes already accumulate pixel n+1, so a new pixel starts
  every `PERIOD = max(steps, C_OUT)` cycles. Consequence: the depthwise layer takes 16 cycles/pixel, not 9.
* **Plain Verilog testbenches with Icarus, not cocotb** (cocotb is not installed and adds nothing here: the golden data are hex files).
* **Each layer is tested independently** against the golden hex dump of that layer (layer n reads the golden output of layer n-1).
  Not yet tested: the layers chained together (that is M5).
* The activation RAMs are outside the engine (in_addr/in_data read port, out_we/out_addr/out_data write port), so M5 can ping-pong them.

Verification (`hardware/verification/run_tests.sh [quick|full]`, `run_postsynth.sh`):
* Unit: requant against 5,000-13,000 Python vectors for each of 7 shifts (random, dense in-range sweeps, exact rounding ties, saturation, extremes);
  mac_unit 300 random sequences + 144-step extremes (+-4.7 M, no overflow) + back-to-back pixels; RAM; weight ROM vs the canonical file.
* Layers: all four layers on all 10 golden tiles (zeros, full255, noise, single pixel, ramp, 3 real tiles, border tile, 12x12 tile),
  bit-exact. `full` = 57 runs (about 5 minutes), `quick` = 25 runs (about 30 seconds).
* Randomized layers with a DIFFERENT M per output channel, extreme weights, large biases and a NON-square tile: these catch bugs that the
  real parameters cannot (the real network has the same M in all channels of a layer, and all golden tiles are square).
* Robustness (every small and randomized run): the output RAM is poisoned first; the engine is run a second time right after the first
  (identical result and identical cycle count); then it is aborted by a ONE-cycle reset at PERIOD+6 different moments (every pipeline stage
  holds live data at some moment) and must stay completely quiet (no busy, no write, no done); then a fresh run must be exact again.
* **Post-synthesis simulation:** Vivado writes a functional netlist of each layer and the same testbench runs on it in xsim (small tile): 4 of 4 exact.
* RTL breakage checks: deliberate breakages of rounding, clamp, shift, signedness, bias/first handling, address maths, pipeline alignment,
  requantizer overrun, channel mapping, per-channel M, output-counter restart, base-address restart and each reset gate were run against
  `quick` on the final RTL: 32 breakages, all caught (plus the two equivalent mutants below). Two breakages (single M for all channels, wrong row stride for a non-square tile) are caught
  ONLY by the randomized tests; the reset gates are caught ONLY by the abort sweep (a single fixed abort moment missed most of them).
  Known equivalent mutants (cannot change behaviour): `> 254` instead of `> 255` in the clamp; the reset gate on the MAC lane's valid flag
  (removed as dead logic). ROM packing is protected by `test_export.py` (a ky/kx-swapped packing was checked to be caught).

Synthesis and implementation findings (`results/utilization/m4_conv_engine.md`):
* **Pitfall found and fixed:** the first weight ROM rebuilt its layout in an `initial` loop. Simulation passed, but Vivado printed
  `Synth 8-311 ignoring non-constant assignment in initial block` and optimized the engine away (2 DSPs, 200 LUTs). The exporter now writes
  `wrom_Ln.mem` (step-major) and the RTL loads it with a plain `$readmemh`. Always read the synthesis warnings, not only the simulation result.
* **Pitfall 2:** small 9x8 multipliers go to LUTs by default; `(* use_dsp = "yes" *)` on `mac_unit` forces one DSP per lane.
* **Pitfall 3:** a netlist simulation needs the testbench to wait for the Xilinx global reset (`glbl.GSR`, first 100 ns), otherwise `start` is ignored.
* Per layer after place and route: 347-397 LUT, 692-952 FF, 14-18 DSP, 0-2 BRAM; all four instances 68 DSP (31 %), 3.5 BRAM tiles.
  Routed slack at 100 MHz: +0.135 (L1), +0.261, +0.582, +0.698 ns; hold >= +0.10 ns; no failing endpoints (out-of-context, no I/O timing).
  Critical path: `rq_i` -> result mux -> requantizer DSP; L1 margin is small, so 125-150 MHz needs another pipeline stage.
* One 70x70x128-bit activation buffer infers **32 RAMB36** (23 % of the chip), not the ~20 estimated above: plan for it in M5.
* Cycles per 64x64 tile (simulated): L1 124,871 / L2 69,712 / L3 69,719 / L4 589,843 = 854,145; x135 tiles = about 1.15 s per 960x540 frame
  at 100 MHz, compute only (simulation arithmetic, not a board measurement).

## 5. Output of this milestone

1. Verilog: `mac_unit.v`, `requant.v`, `tile_ram.v`, `weight_rom.v`, `conv_engine.v` (table above).
2. Self-checking testbenches that print **PASS** against the golden vectors (`run_tests.sh`; Verilog + Icarus instead of cocotb).
3. Utilization and timing reports: `results/utilization/m4_conv_*`.
4. Measured cycles per output pixel: 27 / 16 / 16 / 144 (section 4b).

## 6. Exit checklist

- [x] MAC and requant units match Python on random + boundary tests (requant: Python vectors; mac_unit: independent 64-bit model).
- [x] Conv engine output equals the integer model **exactly** for layer 1 on random and boundary inputs (and layers 2-4).
- [x] Depthwise (`DEPTHWISE=1`) and pointwise (`K=1`) modes also match.
- [x] Synthesizes AND routes at the target clock (100 MHz, routed slack +0.135 ns or better, out-of-context) with the expected DSP/BRAM numbers (one DSP per MAC lane + 2), and the synthesized netlist simulates bit-exact.

## 7. Common problems

| Symptom | Cause |
|---|---|
| Off by exactly 1 on some outputs | Rounding differs from Python (floor vs round, sign handling of `>>>`) |
| Output looks transposed/flipped | Kernel index order (ky/kx) or weight layout mismatch |
| Works for small values, wrong for big ones | Accumulator or product width too small; signed/unsigned mix-up |
| Simulation passes, hardware fails later | Using non-synthesizable constructs; check synthesis warnings |
| BRAM read gives data one cycle late | Synchronous BRAM has 1-cycle read latency; delay your control signals to match |

## 8. Later speed-ups (only after exit checklist is done)

- Compute several input channels per cycle (SIMD) in the 144-cycle layer 4 — the biggest saving.
- Run two output pixels in parallel.
- Pack two INT8 multiplies into one DSP48.
With about 128 MACs busy, estimated time falls to roughly 0.1–0.2 s per 960×540 frame.
