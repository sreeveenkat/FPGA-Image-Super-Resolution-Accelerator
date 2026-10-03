# M6 — AXI Wrapper, DMA and ARM Driver: Upscale a Real Image on the Board

**Time:** 1.5–2 weeks | **Where:** Vivado + Vitis + ZedBoard | **Depends on:** M0 (AXI/DMA skills) and M5 (tile core)

---

## 1. Why this milestone exists

So far your core works only in simulation. Now you make it a real hardware block that the ARM can control and feed with data.
After this milestone you can say: **"I give the board a low-res image, and it gives back a high-res image computed by my FPGA circuit."**

Because you proved AXI-Lite and DMA in M0 with toy designs, this should go faster than M0. If it does not, the problem is
probably in your core's interface, not in the AXI plumbing.

---

## 2. Concepts

### Data flow for one tile

```
ARM: cut tile (70×70×3) from input image in DDR → into a tile buffer in DDR
 │
 ├─ write registers (AXI-Lite): CONTROL.start
 ├─ DMA MM2S: tile buffer ──stream──► sr_tile_core
 │                                       … computes …
 ├─ DMA S2MM: sr_tile_core ──stream──► output tile buffer in DDR (128×128×3)
 └─ ARM: wait for DMA done + STATUS.done, copy output tile into the right place of the big output image
```
Repeat for all 135 tiles (960×540 image padded to 960×576, 64-pixel tiles).

The ARM-does-the-copying approach is simple and slow. It is fine for version 1 (see "improvements" below).

### Register map (AXI-Lite)

| Offset | Name | Bits / meaning |
|---|---|---|
| 0x00 | CONTROL | bit0 start (self-clearing), bit1 soft reset |
| 0x04 | STATUS | bit0 busy, bit1 done, bit2 error |
| 0x08 | TILE_SIZE | tile size / mode (for testing smaller tiles) |
| 0x0C | CYCLES | cycles spent computing the last tile (read-only counter) |
| 0x10 | ERROR_CODE | e.g. 1 = stream underflow, 2 = bad config |
| 0x14 | VERSION | fixed constant, to check the bitstream is the one you expect |

Keep **one** register-map document and use named constants in C (`#define REG_CONTROL 0x00`), never magic numbers.

### Stream protocol (AXI-Stream) — what you must get right
Signals: `TDATA`, `TVALID`, `TREADY`, `TLAST`.
- A transfer happens when `TVALID && TREADY`.
- `TLAST` must be asserted on the **last byte of each DMA packet**; the S2MM channel needs it to know the transfer ended.
- Your core must not drop or reorder data if `TREADY` goes low (**backpressure**).
Use 32-bit or 8-bit stream width consistently on both sides; pack bytes carefully (little-endian: first byte = bits 7:0).

### Cache rules (same as M0)
- Before DMA reads a buffer: `Xil_DCacheFlushRange(buf, len)`.
- After DMA wrote a buffer, before the ARM reads it: `Xil_DCacheInvalidateRange(buf, len)`.
- Align buffers to 64 bytes.

---

## 3. Step-by-step

### Step 1 — Wrap the core with AXI-Stream and AXI-Lite
- Slave stream in, master stream out (with `TLAST`).
- AXI-Lite register block: reuse the IP template from M0 step 3 and add the registers above.
- First version: **weights are baked into the bitstream** (`$readmemh` from the `.mem` files). To change weights you rebuild.
  Later (optional) add a way to load weights through a register or the DMA.

### Step 2 — Block design
Zynq PS + AXI DMA + your core (stream in/out) + AXI interconnect + processor system reset.
DMA memory ports → PS **HP0**. Your core's registers on the **GP0** AXI-Lite bus. Clock everything from `FCLK_CLK0` = 100 MHz.
Build bitstream, export hardware.

### Step 3 — First test: one tiny tile
Use a tile size small enough to inspect by eye (set `TILE_SIZE` to a small value if you parameterized it) or the full 70×70 tile.
In C: fill the input buffer with the golden tile, start the DMA transfers, start the core, wait, compare against the golden output.

```c
XAxiDma_SimpleTransfer(&dma, (UINTPTR)out_tile, OUT_BYTES, XAXIDMA_DEVICE_TO_DMA);   // arm receiver first
XAxiDma_SimpleTransfer(&dma, (UINTPTR)in_tile,  IN_BYTES,  XAXIDMA_DMA_TO_DEVICE);
Xil_Out32(CORE_BASE + REG_CONTROL, 1);                                                // start
while (!(Xil_In32(CORE_BASE + REG_STATUS) & 0x2)) {}                                  // wait done
while (XAxiDma_Busy(&dma, XAXIDMA_DEVICE_TO_DMA)) {}
Xil_DCacheInvalidateRange((UINTPTR)out_tile, OUT_BYTES);
```
(Arm the S2MM receive side before sending, so no output data is lost.)

### Step 4 — The whole-image loop
```
pad input image by 3 pixels (replicate edges) and by extra rows so that height is a multiple of 64
for ty in tile rows:
  for tx in tile columns:
      copy the 70×70×3 window at (ty*64, tx*64) → in_tile
      run tile (DMA + core)
      copy out_tile (128×128×3) → output image at (ty*128, tx*128)
crop output to 1920×1080
```
Polling first; interrupts later (they are an improvement, not a requirement).

### Step 5 — Getting images in and out of the board
Easy options (use the first one):
1. **JTAG with xsdb (Vitis debugger shell):** download a raw file into DDR, run, read the result back.
   `dow -data input.raw 0x10000000` … run … `mrd -bin -file out.raw 0x12000000 <count>`
2. SD card + FatFs library (more setup, but standalone).
3. Embed a small test image as a C array (`xxd -i`) — good for the first small tests.
UART at 115200 baud is too slow for megabytes (~11 KB/s).

On the PC: a script converts PNG → raw bytes, and raw bytes → PNG for viewing.

### Step 6 — Check correctness
- Board output **must equal** the Python integer model output for the same image — compare byte by byte.
- Run the same image 20 times and after power cycles; output must be identical every time.
- Test timeouts: if `STATUS.done` does not appear in, say, 1 second, print an error instead of hanging forever.

---

## 4. Output of this milestone

1. Bitstream + Vitis project that upscales an image on the ZedBoard.
2. C driver with named register constants and error handling.
3. A script to convert images to/from raw.
4. A result PNG from the board, verified **bit-exact** against the integer model.
5. First timing measurement (ARM timer or the CYCLES register).

## 5. Exit checklist

- [ ] One tile through DMA + core matches the golden tile exactly.
- [ ] A full image (start with 128×128 → 256×256, then 960×540 → 1920×1080) matches the integer model exactly.
- [ ] Repeated runs and power cycles give identical output.
- [ ] Timeout/error paths exist (no infinite loops).
- [ ] Register map document and C header agree.

## 6. Common problems

| Symptom | Cause |
|---|---|
| DMA S2MM never completes | Core's `TLAST` missing/misplaced, or output byte count differs from the DMA length |
| First tile OK, later ones garbage | Core not fully reset between tiles; counters not cleared |
| Data shifted by some bytes | Stream width/packing mismatch; wrong byte order |
| Random wrong pixels | Cache flush/invalidate missing |
| Hangs after start | Core waits for input that DMA has not started sending (arm DMA before pressing start) |
| Works in simulation, not on board | Clock/reset not connected; signal crossing clock domains; wrong base address |

## 7. Improvements (optional, after the checklist)

- Interrupt instead of polling.
- Double buffering: DMA tile N+1 while the core computes tile N.
- Use a 2-D DMA (AXI VDMA) instead of ARM copying tiles.
- Load weights at run time.
