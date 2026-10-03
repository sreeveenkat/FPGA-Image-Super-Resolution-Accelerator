# FPGA Sparse Ray Tracing + AI 4K Reconstruction — Working Plan

Board: ZedBoard (XC7Z020-CLG484), Vivado 2024.x WebPACK
Prior experience: Verilog RISC-V core (PL-only, mem-file init), no PS/PL AXI yet

---

## Milestone 0.5 — PS/PL AXI Integration Literacy

### What you actually don't know yet
Your RISC-V project proved you can write correct Verilog and get it through synthesis to a bitstream. It did **not** touch the ARM Cortex-A9 (PS) side, the AXI interconnect, DDR memory-mapped access, or the software toolchain (Vitis). Every later milestone that involves "ARM controls the accelerator" depends on this. Treat it as its own project, not a subtask.

### What you will build, in order

**Step 1: PS-only hello world**
- Create a Vivado project, add a Zynq Processing System IP block, run "Run Block Automation" (auto-configures DDR/clocks for ZedBoard).
- No custom RTL yet. Generate bitstream, export hardware, open Vitis, write bare-metal C that prints "hello" over UART (visible via serial terminal, e.g. `screen`/`putty` at 115200 baud on the USB-UART).
- **Tools:** Vivado Block Design, Vitis (bare-metal, no OS), USB-UART driver on your host PC.
- **Why:** Confirms PS boots, DDR is configured, and you can get output off the board without JTAG waveform debugging. This is your "print debugging" channel for everything after.

**Step 2: AXI GPIO round-trip**
- Add an AXI GPIO IP block connected to switches/LEDs on the ZedBoard, wire it into the PS via the AXI interconnect (Block Automation handles most of this — "Connect Automation").
- Bare-metal C on PS: read switch state via memory-mapped register read, write LED state via memory-mapped register write.
- **Why:** This is your CONTROL/STATUS register concept (section 12 of the original doc) in its smallest possible form — PS writing/reading a memory address that PL responds to. Once this works, your custom accelerator's register interface is the same pattern, just your own IP instead of AXI GPIO.

**Step 3: Your own trivial AXI-Lite peripheral**
- Write a minimal Verilog AXI-Lite slave yourself (a 4-register block: write two numbers, read their sum). Use Vivado's "Create and Package New IP → AXI4 Peripheral" template as scaffolding — don't write the AXI-Lite protocol state machine from scratch; the template generates the handshake logic, you just wire your registers into it.
- Package it as an IP, drop it into the block design next to the Zynq PS, connect via AXI interconnect.
- PS C code: writes two values to the peripheral's registers, reads back the sum.
- **Why:** This *is* your accelerator's control interface, proven end to end, before your ray tracer RTL exists. When Milestone 5 comes, you're extending this known-working peripheral, not building AXI-Lite for the first time under pressure.

**Step 4: AXI DMA basic transfer**
- Add an AXI DMA IP block. Configure a memory-to-memory or memory-to-stream transfer of a small known buffer (e.g., 256 bytes of test pattern) from DDR through the DMA and into a simple AXI-Stream FIFO, then back to a different DDR address.
- PS C code: fill source buffer, kick off DMA descriptor, poll or interrupt on completion, verify destination buffer matches source.
- **Why:** This is exactly the mechanism your ray-traced RGB/depth/normal buffers and your reconstructed 4K tiles will move through later (section 5/12 of the original doc — AXI DMA, DDR frame memory). Get it working on garbage test data first; debugging DMA descriptor setup is fiddly and you don't want to do it for the first time while also debugging your ray tracer.

### Exit criteria (do not proceed until all true)
- [ ] PS boots and prints over UART reliably, every power cycle.
- [ ] PS can write/read an AXI-Lite register in your own custom IP.
- [ ] A DMA transfer round-trips a known buffer through PL and back with byte-exact match.
- [ ] You understand, in your own words, the difference between AXI-Lite (control), AXI4 memory-mapped (bulk data), and AXI-Stream (pixel/data streaming) — because the original doc uses all three and conflating them will cost you time later.

### Time estimate
[Guessing, based on typical first-time PS/PL learning curve] 1–1.5 weeks at 5–6 hrs/day, assuming no board hardware failures. If Vitis/Vivado version mismatches or board-file issues appear, add 2–3 days.

---

## Milestone 1 — C++ Golden Ray Tracer

### What "golden" means here
This is the ground-truth software model everything else gets checked against. It runs on your laptop, not the FPGA. Its job is (a) to generate training data for the neural network, and (b) to give you a bit-for-bit comparison target once you write the fixed-point RTL version.

### What you build
- **Camera model:** origin, forward/right/up vectors, horizontal/vertical FOV → generates a ray direction per pixel. Keep it a simple pinhole camera, no depth of field or lens effects.
- **Sphere intersection:** solve the ray-sphere quadratic (`t² (d·d) + 2t(d·(o-c)) + (o-c)·(o-c) - r² = 0`), reject negative discriminant, take the nearest positive root.
- **One point light, Lambertian shading:** `color = albedo * max(0, dot(normal, light_dir)) * light_intensity`, plus a small ambient term so unlit faces aren't pure black.
- **Output buffers:** write RGB, depth (distance from camera to hit point), and normal (x,y,z) as separate raw binary files or a simple custom format — not PNG, you want raw floats/ints for later numeric comparison, not lossy/compressed images.
- **Deterministic test scenes:** hard-code 3–5 scenes (single sphere, two spheres, sphere behind camera / no hit, sphere at edge of frame) with fixed seeds — no randomness yet, randomness comes in Milestone 2.

### Tools
- C++17 or later, a simple math library (write your own `vec3` struct — don't pull in a large dependency for this).
- CMake for build (keeps it portable and is what Claude Code will scaffold cleanly).
- GoogleTest or Catch2 for unit tests on the intersection math specifically (this is the part most likely to have silent sign/edge-case bugs).

### Why this order matters
If your sphere-intersection math has a bug, it will silently corrupt your entire dataset, and you won't find out until your neural network trains on garbage or your RTL comparison fails mysteriously three milestones later. Unit-test the intersection math in isolation (known ray + known sphere → known hit point, by hand-calculated values) before trusting any rendered image.

### Exit criteria
- [ ] Renders at 320×180 without crashing, for all test scenes.
- [ ] Unit tests pass for intersection math against hand-calculated expected values.
- [ ] RGB/depth/normal outputs visually inspectable (write a tiny Python script to load the raw buffers and display with matplotlib — sanity check, not final tooling).

### Time estimate
1.5–2 weeks. [Likely] Claude Code genuinely helps here — this is conventional OOP C++ with well-known math, low ambiguity, good test coverage possible.

---

## Milestone 2 — Dataset Generation

### What you build
- Extend Milestone 1's scene setup to randomize: sphere positions/radii/colors (within bounds that keep them in frame), camera position/angle, light position/intensity. Generate at two resolutions per scene: low-res input (320×180) and high-res ground truth (1280×720, a 4× ratio — matching your eventual FPGA input/output ratio at smaller scale before you commit to full 960×540→3840×2160).
- Generate a few hundred to low-thousands of scene variants. Each variant produces: low-res RGB, low-res depth, low-res normal, high-res RGB (ground truth).
- **Split by scene, not by frame** — if scene #47 appears in training data, none of its frames should appear in test data. This matters because splitting randomly by frame lets the network memorize scene-specific geometry and inflates your reported accuracy — the original doc calls this out explicitly and it's a real, common mistake.
- Store a manifest file (JSON/CSV) recording every generation parameter per scene, so results are reproducible.

### Tools
- Your C++ tracer (Milestone 1) called in a loop, or wrapped with a small Python script that generates randomized scene-description files and invokes the C++ binary per scene.
- NumPy for loading/inspecting raw buffers on the Python side.

### Why bother with a manifest
[Certain] If anyone (a professor, an interviewer, your future self) asks "how was this dataset generated," "I ran it a bunch of times" is not an acceptable answer for a project whose entire value proposition is measurable, reproducible engineering. The manifest is 30 minutes of work that prevents that failure.

### Exit criteria
- [ ] At least a few hundred scene variants generated, split into train/test by scene ID.
- [ ] Manifest file exists and can regenerate the exact same dataset if rerun.

### Time estimate
3–5 days (mostly scripting around Milestone 1's tracer, not new hard logic).

---

## Milestone 3 — FP32 Training + Baseline

### What you build
- **Bicubic/nearest-neighbor baseline first.** Upscale your low-res RGB with plain bicubic interpolation (`cv2.resize` or `torch.nn.functional.interpolate`), measure PSNR/SSIM against ground truth. This number is your floor — your neural network is worthless if it doesn't beat this.
- **The network** (from the original doc, section 9): small conv stack, 3×3 conv → depthwise → pointwise → final conv → pixel shuffle for 4× upscale. Input channels: RGB + depth + normal (5–6 channels total, not just 3).
- **Loss:** `L1 + 0.2*(1-SSIM) + 0.05*edge_loss`. Start with just L1 if you want faster first iteration, add SSIM/edge terms once L1-only trains successfully.
- **Metrics:** PSNR, SSIM at minimum. LPIPS is nice-to-have (needs a pretrained perceptual network as dependency — skip it if it becomes a dependency headache).

### Tools
- PyTorch, `torch.utils.data.Dataset` wrapping your manifest, standard training loop.
- `scikit-image` or `torchmetrics` for PSNR/SSIM (don't hand-roll these — subtle bugs in a hand-rolled SSIM are a classic trap).

### Why FP32 before quantization
[Certain] If the FP32 model doesn't clearly beat bicubic, quantizing it first only makes debugging harder — you won't know if a bad result is a model-design problem or a quantization-precision problem. Prove the model architecture works at full precision, then worry about precision loss separately.

### Exit criteria
- [ ] Bicubic baseline PSNR/SSIM numbers recorded.
- [ ] Trained FP32 model beats bicubic baseline on held-out (test-split) scenes by a clear margin, not a marginal 0.1 dB difference.
- [ ] Visual spot-check: no obvious garbage artifacts (checkerboard patterns, color shifts, complete blur) on test images.

### Time estimate
1.5–2 weeks, most of it spent on training iteration/debugging, not initial setup.

---

## Milestone 4 — INT8 Quantization + Integer Reference Model

### What you build
- **Quantization-aware training (QAT):** PyTorch has built-in QAT support (`torch.quantization` / `torch.ao.quantization`). Insert fake-quant nodes, fine-tune from your FP32 checkpoint for a shorter schedule (QAT usually needs far fewer epochs than training from scratch).
- **Export:** integer weights, per-layer scale factors, zero points.
- **Bit-accurate integer inference in Python:** this is the part people skip and shouldn't. Write a from-scratch Python function that does the *exact* integer arithmetic your RTL will do later — INT8 multiply, INT32 accumulate, requantize (multiply by scale, shift, clamp), no floating point anywhere in this path. This becomes your RTL's source of truth in Milestone 6, not the PyTorch QAT model itself (PyTorch's internal quantized ops don't necessarily match your RTL's exact rounding/shift behavior).

### Tools
- PyTorch QAT APIs for the training part.
- Plain NumPy (integer dtypes only — `int8`, `int32`) for the bit-accurate reference — no PyTorch here, you want full control over every operation's exact integer semantics.

### Why this is its own milestone and not a quick step
[Likely] This is one of the most commonly underestimated parts of quantized-accelerator projects. "INT8 quantization" sounds like a checkbox, but getting your Python integer model to match what you'll implement in RTL — same rounding mode, same overflow/saturation behavior, same shift amounts — requires care, and if you get it wrong here, you'll be debugging phantom RTL bugs in Milestone 6 that are actually reference-model bugs.

### Exit criteria
- [ ] INT8 QAT model's PSNR/SSIM loss vs FP32 measured and small (document the exact numbers — this is a real result you report, not something to hide).
- [ ] Bit-accurate Python integer inference produces output matching the QAT model's output within expected quantization tolerance (near-exact, not "close").

### Time estimate
1 week if QAT training is stable; add days if training instability shows up (quantized training can be finicky — loss spikes, accuracy collapse are common first-attempt issues).

---

## Milestone 5 — RTL: Ray Generator + Sphere Intersection

### What you build
- **Fixed-point conversion first, on paper/in Python, before writing Verilog.** Take your C++ tracer's floating-point ranges (camera position range, direction component range, depth range) and decide Q-format bit widths (e.g., Q8.16 signed for ray direction components). Write a small Python script that simulates your chosen fixed-point format's rounding/truncation and compare its output to the floating-point reference — this becomes Milestone 5's own "golden model," derived from Milestone 1's, not identical to it.
- **Camera-ray generator module:** takes pixel (x,y) + precomputed camera constants (computed in C++/Python, loaded as constants — don't compute camera basis vectors in hardware), outputs ray origin + direction in fixed point.
- **Sphere intersection module:** quadratic solve in fixed point. This needs a square root (for the discriminant) — start with a simple iterative approximation (Newton-Raphson on a lookup-table seed) rather than a full pipelined CORDIC; correctness first, throughput later.
- **Testbench:** cocotb (Python-based, works with your existing Python fixed-point reference model directly — no need to reimplement the reference in a second language for the testbench).

### Tools
- SystemVerilog or Verilog for the RTL (your existing background).
- cocotb + a free simulator (Icarus Verilog or Verilator) for verification — this lets you drive the same fixed-point Python model you already wrote as the testbench oracle, which is exactly the "three reference levels" structure the original doc describes (float → fixed-point Python → RTL).
- Vivado simulator only when you need to check synthesis-specific behavior; use the free open simulators for day-to-day iteration since they're faster to invoke.

### Why this is the highest-real-risk milestone so far
[Likely] This is genuinely new difficulty compared to your RISC-V project — you're not just implementing a known ISA spec, you're deriving your own fixed-point number formats and verifying numerical correctness against a floating-point reference, which involves real judgment calls (how much precision is "enough," where rounding error accumulates). Budget real debugging time here, and don't be surprised if your first fixed-point format choice needs revision after you see actual error accumulation.

### Exit criteria
- [ ] RTL sphere-intersection output matches your bit-accurate fixed-point Python reference exactly (or within one LSB, documented and justified) across all deterministic test scenes from Milestone 1.
- [ ] Runs in simulation at 320×180 producing a full correct frame, pixel by pixel.

### Time estimate
2–3 weeks. This is the first milestone where "I thought this would take 3 days and it took 10" is genuinely likely — treat the original 2–3 week estimate as a floor, not a ceiling.

---

## Milestone 6 (was 5 in the earlier summary) — AXI Wrapper + ARM Driver for the Ray Tracer

### What you build
- Wrap the sphere-intersection core from Milestone 5 with the AXI-Lite control interface pattern you already proved out in Milestone 0.5 Step 3 (CONTROL/STATUS/WIDTH/HEIGHT/OUTPUT_BASE registers — see section 12 of the original doc for the register map to mirror).
- Output pixels via AXI-Stream into the DMA path you proved out in Milestone 0.5 Step 4, landing the frame in DDR.
- ARM bare-metal (or minimal Linux, your choice — bare-metal is simpler and sufficient here) C driver: configure registers, start core, wait for done (poll or interrupt — start with polling, it's simpler to debug, add interrupts once polling works), read frame back from DDR to host over UART/SD card/Ethernet for inspection.

### Tools
Same as Milestone 0.5: Vivado Block Design, Vitis, your own AXI-Lite peripheral extended with real register logic instead of the toy adder.

### Why this should be faster than Milestone 0.5 was
Because Milestone 0.5 already worked out the unknowns (block design connections, DMA descriptor setup, PS-side C patterns). This milestone is applying that known pattern to real RTL, not learning the pattern itself. If it's taking as long as Milestone 0.5 did, something about the RTL interface (not the AXI plumbing) is likely the actual problem.

### Exit criteria
- [ ] One command from ARM produces a complete, correct 320×180 rendered frame in DDR, retrievable and verifiably matching the software reference.
- [ ] Works reliably across multiple runs/power cycles, not "worked once."

### Time estimate
1.5–2 weeks — this is your **first natural stopping point** for a complete, defensible project if time runs short. "FPGA sphere ray tracer, AXI-DMA integrated, ARM-controlled, cross-verified against golden C++/fixed-point models" is a whole, presentable result even with nothing past this point.

---

## Milestone 7 — CNN Accelerator RTL

### What you build, in strict sub-order
1. **One convolution layer only, first.** Line buffer + sliding-window generator (this is standard streaming-conv architecture — look at open-source examples of line-buffer-based conv engines for the pattern, don't design the windowing logic from first principles), INT8 MAC array (start with plain `*` operators targeting DSP48 inference, not custom multiplier logic yet), accumulate in INT32, requantize (multiply by scale constant, shift, clamp to INT8) matching your Milestone 4 integer reference exactly.
2. **Verify this one layer alone** against your Milestone 4 Python integer reference before adding any more layers. This isolation step is what prevents multi-layer debugging chaos.
3. Only after step 2 passes: chain the remaining layers (depthwise, pointwise, final conv), add pixel shuffle (this is pure data reordering / address logic, not arithmetic — implement it as a control/addressing block, not a math block).
4. **Tiling:** process the image in fixed-size tiles (e.g. 64×64) with halo pixels around each tile for the 3×3 convolution windows, and discard the overlapped halo region before writing tile output — get this right or you'll see visible seams in your final image.

### Tools
Same RTL/cocotb/simulator stack as Milestone 5. Reference model is your Milestone 4 bit-accurate integer Python.

### Why this is the single hardest milestone in the whole project
[Likely] Streaming convolution with correct tile-boundary/halo handling is where projects like this most commonly stall — it's not conceptually hard, but it has many easy-to-get-subtly-wrong details (off-by-one halo sizes, incorrect requantization rounding, weight-loading order bugs) that each individually produce a plausible-looking but wrong image, making root-causing slow. Budget the most slack of any milestone here, and do not skip the single-layer isolation test in step 2 no matter how tempting it is to wire everything at once.

### Exit criteria
- [ ] Single conv layer RTL output matches Python integer reference exactly on random and boundary-case inputs.
- [ ] Full network RTL output matches Python integer reference within documented tolerance on tiled real images, no visible seams at tile boundaries.

### Time estimate
3–4 weeks, realistically the widest uncertainty band in the whole plan — could run longer.

---

## Milestone 8 — End-to-End Integration

### What you build
Wire Milestone 6's ray-tracer-to-DDR path directly into Milestone 7's CNN-accelerator-from-DDR path: one ARM command triggers ray tracing → writes G-buffers to DDR → triggers CNN reconstruction reading those buffers tile-by-tile → writes final upscaled tiles back to DDR → transfers complete image to host for viewing.

### Why this is usually faster than it sounds
If Milestones 6 and 7 were each independently verified against DDR-based golden references, connecting them is mostly just chaining two already-correct DMA-based stages — the risk here is mainly buffer-format mismatches (does the CNN expect the exact same fixed-point/INT8 layout the ray tracer actually writes?), which is a data-format bookkeeping problem, not a new algorithmic one.

### Exit criteria
- [ ] One command produces a final reconstructed image from a scene description, with no manual intervention between stages.
- [ ] Benchmark numbers collected: cycles, DMA bandwidth, latency, resource utilization (LUTs/DSPs/BRAM from the Vivado implementation report).

### Time estimate
1–2 weeks if Milestones 6/7 were solid; longer if buffer-format mismatches surface.

---

## Milestone 9 (optional/parallel with 7–8) — Custom Multiplier

### What you build
Swap the standard `*` multiplier in the CNN MAC array (Milestone 7) for a custom design — [Likely] your posit/SZEM work from the IIT Dharwad internship is directly reusable here rather than starting a new multiplier design from scratch. Evaluate at three levels: unit (area/power/delay via Vivado synthesis/implementation reports), CNN-layer output error (compare against exact-multiplier RTL output), system-level (final image PSNR/SSIM degradation, resource savings, energy/frame if you can estimate power via Vivado's power estimator).

### Why parallel-able
This only touches the MAC array internals, not the surrounding control/tiling logic — you can develop and unit-test it independently while Milestones 7/8 are being finished, then swap it in as a drop-in replacement once both are stable.

### Time estimate
2–3 weeks, reduced if genuinely reusing existing posit-multiplier work rather than designing new.

---

## Running Time Total (brutal, not optimistic)

| Milestone | Estimate |
|---|---|
| 0.5 — PS/PL literacy | 1–1.5 wk |
| 1 — C++ tracer | 1.5–2 wk |
| 2 — Dataset | 0.5–1 wk |
| 3 — FP32 training | 1.5–2 wk |
| 4 — Quantization | 1 wk |
| 5 — Ray tracer RTL | 2–3 wk |
| 6 — AXI/DMA/ARM for tracer | 1.5–2 wk |
| **Stopping point 1** | **≈9–12 wk total** |
| 7 — CNN RTL | 3–4 wk |
| 8 — Integration | 1–2 wk |
| **Stopping point 2** | **≈13–18 wk total** |
| 9 — Custom multiplier | 2–3 wk (partly parallel) |

[Likely] At 5–6 hrs/day continuous, Stopping Point 1 is realistic in ~2.5–3 months, Stopping Point 2 in ~4–4.5 months. Milestone 9 adds relatively little wall-clock time if run in parallel and if you genuinely reuse existing multiplier work.

Do not skip exit criteria to "save time" — every skipped verification step becomes a multi-day debugging session two milestones later when it resurfaces as an unexplained downstream bug.
