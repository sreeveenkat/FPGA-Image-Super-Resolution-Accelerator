# M8 — Optional Extensions (only after M7 is finished)

Each item here is a separate mini-project. Pick **one**, not all. Do not start any of them while M0–M7 is incomplete.

---

## 1. Speed-ups for the same network (easiest, most useful)

| Idea | What it does | Expected effect (estimate) |
|---|---|---|
| More MACs in layer 4 (SIMD over input channels) | Layer 4 is 144 of ~196 cycles per pixel | Biggest win: ~2–3× overall |
| Two pixels in parallel | Duplicate the engine | ~2× if DSPs allow |
| Pack two INT8 multiplies per DSP48 | Fewer DSPs per MAC | Frees DSPs for more parallelism |
| Double-buffered DMA | Overlap data movement with compute | Hides DMA time |
| Interrupts | Free the ARM while waiting | Cleaner software |
| Raise the clock to 125–150 MHz | Needs timing work (pipeline the requant) | Proportional |

Target after these: roughly 0.1–0.2 s per 960×540 frame (5–10 fps) — an estimate; measure it.

## 2. Show the result on a monitor (HDMI, 1080p)

The ZedBoard has an HDMI transmitter (ADV7511). You need video IP: AXI VDMA (reads frame buffer from DDR) →
AXI4-Stream to Video Out → HDMI pins, plus I²C configuration of the ADV7511. Digilent publishes reference designs.
This is mostly Vivado/IP integration work, not new RTL. Because the output is 1080p, it fits the display.

## 3. ×4 super-resolution (480×270 → 1920×1080)

Retrain a network with 48 output channels (3·4·4) and PixelShuffle(4). Layer 4 becomes 16→48, which has 4× the MACs of the
×2 layer 4 (6,912 MACs/pixel there). Because input has 4× fewer pixels than 960×540, total work per frame is similar.
Changes: M2 (new net), M3 (re-quantize), M5 (shuffle ×4 addressing, halo still 3 → output tile 256×256 for a 64×64 core),
M6 (bigger output buffers).

## 4. Luma-only processing (Y channel)

Convert RGB → YCbCr on the ARM. Run the CNN only on Y (1 channel in, 4 channels out for ×2). Upscale Cb and Cr with simple
interpolation. This cuts layer 1 and layer 4 maths by roughly 3× and is what the QFSRCNN paper in your folder does.
Costs: extra colour conversion on the ARM; slightly lower colour accuracy.

## 5. Ray-traced input (the original idea)

Replace "downscaled photo" with "image made by your own ray tracer".
1. C++ golden ray tracer (camera rays, sphere intersection, Lambert shading) → RGB, depth, normal buffers.
2. Dataset of random scenes (split by scene, not by frame; save a manifest of all parameters).
3. Retrain the CNN with 3 + 1 + 3 = 7 input channels.
4. (Hard) Move ray generation + sphere intersection to RTL with a fixed-point model and cocotb tests, stream into DDR.
This is a **second project** of similar size to M0–M7. The earlier plan files describe it in detail.

## 6. Custom multiplier research

Replace the `*` in the MAC with a custom design (your posit or other low-cost multiplier work).
Evaluate at three levels: (1) multiplier alone (area, delay, power), (2) layer output error vs the exact multiplier,
(3) final image PSNR/SSIM and energy per frame. Report the trade-off honestly — a smaller multiplier is only a win if image
quality stays acceptable. Note: with only 220 DSPs available, a LUT-based multiplier can also *add* parallelism.

## 7. INT4 weights

Quantize weights to 4 bits (QAT required). Smaller memory, cheaper multiplies. Expect a larger quality drop; measure it.

## 8. Higher resolutions (stretch, not a promise)

1080p → 4K (×2) uses ~4× the pixels of 960×540 → 1080p, so even an optimized design would run at low fps (order of 1 fps,
estimate). It is a legitimate "it works, slowly" demo, but only worth doing after the speed-ups in section 1.
