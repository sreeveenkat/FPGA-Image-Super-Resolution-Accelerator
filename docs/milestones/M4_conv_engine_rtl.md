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
| **Total** | **≈ 196 cycles per input pixel** | |

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
Tile of 70×70 pixels × 16 B = 78 KB per buffer; ≈ 20 BRAM36 each (my estimate); two buffers ≈ 40 of 140. Weights: ~2.6 KB
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

### Step 4 — Verify against Python with cocotb
```python
# pseudo-test
inp  = load("golden/L1_in.npy")
exp  = load("golden/L1_out.npy")            # from integer_reference.py
dut_out = await run_dut(inp)
assert (dut_out == exp).all()               # bit-exact
```
Test: random input, all zeros, all 255, a single bright pixel, saturation cases, weights at ±127/−128.

### Step 5 — Synthesize the engine alone
In Vivado: Run Synthesis on the engine as top. Read the utilization report and check:
DSP usage ≈ P, BRAM as expected, no inferred latches, timing at 100 MHz.

---

## 5. Output of this milestone

1. Verilog: `mac_unit.v`, `requant.v`, `tile_ram.v`, `conv_engine.v` (+ weight ROM).
2. cocotb testbenches that print **PASS** against the golden vectors.
3. A utilization report for the engine.
4. Measured cycles per output pixel (compare with the table above).

## 6. Exit checklist

- [ ] MAC and requant units match Python on random + boundary tests.
- [ ] Conv engine output equals the integer model **exactly** for layer 1 on random and boundary inputs.
- [ ] Depthwise (`DEPTHWISE=1`) and pointwise (`KSIZE=1`) modes also match.
- [ ] Synthesizes at your target clock with the expected DSP/BRAM numbers.

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
