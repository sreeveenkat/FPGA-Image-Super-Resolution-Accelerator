# Register map of `sr_accel_top` (AXI4-Lite), pipeline version - the one document

Source of truth: `hardware/rtl/top/sr_accel_top.v` (header comment + code). C view: `software/board/sr_regs.h`.
`software/board/test_regs.py` (part of `hardware/verification/run_tests.sh quick`) fails when the header, the Verilog and this table disagree.
**This is the whole-frame PIPELINE version (branch `pipe`, VERSION 0x53525301, `docs/ARCHITECTURE_PIPELINE.md`). It has NOT run on a board.**
The tiled designs (R0 0x53520602, R2q 0x53522201, R3q 0x53523201, r0_125 0x53524201, r3q_125 0x53524301) keep the old map (TILE_SIZE at 0x08, debug
registers 0x18-0x30). Each tree's driver accepts only its own VERSION family (`VERSION & 0xFFFFFF00`).

32-bit registers, 6-bit byte address (64-byte window). Reads of other addresses return 0; writes to read-only or unmapped addresses are accepted
(response OKAY) and ignored. AW and W may arrive in any order. A write needs the matching `wstrb`.

| Offset | Name | Access | Bits / meaning |
|---|---|---|---|
| 0x00 | CONTROL | W (reads 0) | bit0 **START**: start one frame (ignored while busy; refused with ERROR_CODE 4 if FRAME_W/FRAME_H are out of range; an accepted start clears sticky DONE and ERROR). bit1 **SRESET**: soft reset of the core, clears DONE and ERROR, aborts a frame. Only bits written with `wstrb[0]` = 1 take effect. |
| 0x04 | STATUS | R | bit0 **BUSY**, bit1 **DONE** (sticky), bit2 **ERROR** (sticky, = ERROR_CODE != 0) |
| 0x08 | FRAME_W | RW | LR frame width W, 1..MAX_W; bits 15:0 (byte lanes 0 and 1); sampled at START; 0 after reset |
| 0x0C | CYCLES | R | clock cycles from the accepted START to the last output beat of the frame (counts while busy, holds its value afterwards) |
| 0x10 | ERROR_CODE | R | 0 none, 1 early `tlast` (on an input beat that is not the last), 2 last input beat without `tlast`, 3 `tkeep` != 0xF on an accepted input beat, 4 frame size out of range (START refused, nothing runs, DONE unchanged), 5 internal FIFO error (never expected). The FIRST error is kept. |
| 0x14 | VERSION | R | `0x53525301` (pipeline, R3q weights + anchor, 125 MHz) |
| 0x18 | FRAME_H | RW | LR frame height H, 1..65535; bits 15:0; sampled at START; 0 after reset |
| 0x1C | MAX_W | R | largest W: MAXW - 6 = 1018 (line-buffer depth 1024) |
| 0x20 | DBG_IN_BEATS | R | input beats accepted in the current / last frame |
| 0x24 | DBG_OUT_BEATS | R | output beats sent in the current / last frame |

## Behaviour as implemented (read this before writing driver code)
* **One frame per START.** Input: the replicate-padded LR frame, (W+6) x (H+6) pixels, RGB raster `[y][x][c]`, little-endian 32-bit beats
  (byte 0 = `tdata[7:0]`), `ceil(3 (W+6)(H+6) / 4)` beats; the last beat may carry 1-3 unused bytes; `tlast` on the last beat.
  Output: the 2W x 2H x 3 HR frame in raster order, `3 W H` beats, `m_axis_tlast` on the last beat. 960 x 540: 395,577 beats in, 1,555,200 beats out.
* **busy** is high from one cycle after a START write until the last output beat has been taken by the DMA, and in the cycle of the done pulse
  (no cycle where busy = 0 and done = 0 during a frame).
* **done** means "the last output beat was accepted by the DMA S2MM channel". It stays set until the next ACCEPTED start or a soft reset.
* **error** codes 1-3 are only reported; the frame is still processed to the end. Recovery is a soft reset (CONTROL = 2), then a new frame.
* `s_axis_tready` stays low until a frame has started (a few cycles after START), so the DMA may be armed first (the driver arms S2MM, then MM2S, then
  writes START), and low again after the last input beat.
* A soft reset needs a few cycles; the driver reads STATUS back. The DMA itself is not reset by it (use `XAxiDma_Reset`).
* The golden tile of T1 (70 x 70 padded input of `real0`) is a valid 64 x 64 frame: 14,700 bytes in, 49,152 bytes out, the same bytes as the tiled design.
* Measured in simulation (not on a board): CYCLES = 1,337 for a 5 x 4 frame and 57,233 for 64 x 48 (`tb_sr_pipe_top.v`); about 16 cycles per output pixel of layer 1.

## Address map of the block design (Vivado project `/home/sreevenkat/Desktop/venkat/vitis/m6_sr`, from the Address Editor, as reported by the owner)
| Master | Slave | Base | Range |
|---|---|---|---|
| ARM (M_AXI_GP0) | `sr_accel_top_0/s_axi` | **0x4000_0000** (`SR_BASE`) | 4K (the registers use the first 0x34 bytes; the block decodes a 64-byte window) |
| ARM (M_AXI_GP0) | `axi_dma_0/S_AXI_LITE` | 0x4040_0000 (`SR_DMA_BASE`) | 64K |
| ARM (M_AXI_GP0), unchanged from M0 | `adder_ip_0` 0x43C0_0000, GPIO LEDs 0x4120_0000, GPIO switches 0x4121_0000 | | |
| `axi_dma_0` MM2S and S2MM | S_AXI_HP0 -> DDR | 0x0000_0000 - 0x1FFF_FFFF | 512 MB |

`sr_accel_top` has no address check of its own beyond `addr[5:2]`: within its 4K window the registers repeat every 64 bytes (addresses 0x34-0x3F read 0; 0x18-0x30 read 0 on the 0x53520601 bitstream).
The driver uses 0x00-0x14 and reads the debug registers 0x18-0x30 in its error dump (only when VERSION is 0x53520602).
