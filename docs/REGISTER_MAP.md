# Register map of `sr_accel_top` (AXI4-Lite) - the one document

Source of truth: `hardware/rtl/top/sr_accel_top.v` (header comment + code). C view: `software/board/sr_regs.h`.
`software/board/test_regs.py` (part of `hardware/verification/run_tests.sh quick`) fails when the header and the Verilog disagree.
Status: **simulated and synthesized only, not yet seen on a board.** The AXI base address of the block comes from the Vivado Address Editor (see "Address map of the block design" below; `SR_BASE` in `software/board/sr_app/sr_driver.h`).

32-bit registers, 6-bit byte address (64-byte window). Reads of other addresses return 0; writes to read-only or unmapped addresses are accepted
(response OKAY) and ignored. AW and W may arrive in any order. A write needs the matching `wstrb`.

| Offset | Name | Access | Bits / meaning |
|---|---|---|---|
| 0x00 | CONTROL | W (reads 0) | bit0 **START**: one-cycle pulse into the core (ignored while busy; an accepted start clears sticky DONE and ERROR). bit1 **SRESET**: one-cycle soft reset of core + wrapper, also clears DONE and ERROR. Only bits written with `wstrb[0]` = 1 take effect. |
| 0x04 | STATUS | R | bit0 **BUSY**, bit1 **DONE** (sticky), bit2 **ERROR** (sticky, = ERROR_CODE != 0) |
| 0x08 | TILE_SIZE | R | HC (64): core tile edge in input pixels. Input tile = HC+6 = 70, output tile = 2*HC = 128 |
| 0x0C | CYCLES | R | core clock cycles from start to the last output byte of the last / current tile (cleared by start and reset; holds its value afterwards) |
| 0x10 | ERROR_CODE | R | 0 none, 1 early `tlast` (on an input beat that is not the last), 2 last input beat without `tlast`, 3 `tkeep` != 0xF on an accepted input beat. The FIRST error of a tile is kept. |
| 0x14 | VERSION | R | `0x53520601` |

## Behaviour as implemented (read this before writing driver code)
* **busy** is high from one cycle after a START write until the last output beat has been taken by the DMA. It is high in the cycle of the done pulse too, so there
  is never a cycle where STATUS reads busy = 0 and done = 0 during a tile (checked by a monitor in `tb_sr_accel_top.v`).
* **done** means "the last output beat was accepted by the DMA S2MM channel" (not merely "the core finished computing"). It stays set until the next ACCEPTED start or a
  soft reset. A START written while busy is ignored completely (it does not clear DONE/ERROR and does not restart anything).
* **error** is only reported. The tile is still processed to the end (the DMA transfers still complete). Recovery is a soft reset (CONTROL = 2) and a new tile.
* The input stream is not accepted before START: `s_axis_tready` stays low until the core is in its load phase, so the DMA may be armed first (the driver arms
  S2MM, then MM2S, then writes START).
* A soft reset needs a few cycles to take effect; after writing it, wait (the driver reads STATUS back) before arming a new transfer. The DMA itself is not
  reset by this (use `XAxiDma_Reset` after a DMA error).
* Streams: 32-bit beats, little endian (byte 0 = `tdata[7:0]`). Input tile = 14,700 bytes = 3,675 beats (RGB raster `[y][x][c]`, 70 x 70 with halo),
  output tile = 49,152 bytes = 12,288 beats (RGB raster of the 128 x 128 tile). `m_axis_tlast` is on the last output beat; the DMA MM2S generates `tlast` on the last input beat.
* Measured in simulation (not on a board): CYCLES = 926,202 per tile at HC = 64 without stalls (`results/utilization/m6_top.md`).

## Address map of the block design (Vivado project `/home/sreevenkat/Desktop/venkat/vitis/m6_sr`, from the Address Editor, as reported by the owner)
| Master | Slave | Base | Range |
|---|---|---|---|
| ARM (M_AXI_GP0) | `sr_accel_top_0/s_axi` | **0x4000_0000** (`SR_BASE`) | 4K (the registers use the first 0x18 bytes; the block decodes a 64-byte window) |
| ARM (M_AXI_GP0) | `axi_dma_0/S_AXI_LITE` | 0x4040_0000 (`SR_DMA_BASE`) | 64K |
| ARM (M_AXI_GP0), unchanged from M0 | `adder_ip_0` 0x43C0_0000, GPIO LEDs 0x4120_0000, GPIO switches 0x4121_0000 | | |
| `axi_dma_0` MM2S and S2MM | S_AXI_HP0 -> DDR | 0x0000_0000 - 0x1FFF_FFFF | 512 MB |

`sr_accel_top` has no address check of its own beyond `addr[5:2]`: within its 4K window the six registers repeat every 64 bytes (addresses 0x18-0x3F read 0).
The driver only uses offsets 0x00-0x14.
