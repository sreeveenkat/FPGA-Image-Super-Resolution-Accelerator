/* DDR memory map of the board program (ZedBoard: 512 MB DDR at 0x0000_0000 - 0x1FFF_FFFF).
 *
 *   0x0000_0000 - 0x000F_FFFF  reserved by the Xilinx standalone BSP (vectors, page tables, ...), never touched
 *   0x0010_0000 - ...          the program: code, data, bss, stack, heap (linker script lscript.ld, ORIGIN = 0x100000, heap/stack 8 KB each by default).
 *                              With golden_tile.h (64 KB) it is far below 1 MB.  Everything below SR_IN_ADDR is "program"; main() checks the linker symbol _end.
 *   0x1000_0000 - 0x11FF_FFFF  input image   (SRIM: 16-byte header + RGB), downloaded by the host (JTAG).   32 MB reserved, 1.5 MB used for 960x540
 *   0x1200_0000 - 0x12FF_FFFF  output image (SRIM)                                                          16 MB reserved, 6.2 MB used for 1920x1080
 *   0x1300_0000 - 0x1300_003F  status block (ready marker) the host polls
 *   0x1400_0000 - 0x15FF_FFFF  padded input image (work buffer)                                              32 MB reserved, 1.7 MB used for 960x540
 *   0x1600_0000 - 0x1600_FFFF  tile input buffer  (14,700 B, DMA reads it, 64-byte aligned)
 *   0x1610_0000 - 0x1610_FFFF  tile output buffer (49,152 B, DMA writes it, 64-byte aligned)
 *   0x1620_0000 - 0x1FFF_FFFF  free
 * All fixed regions are 64-byte (cache line) aligned.  Limits for an image of w x h pixels: 16 + 3wh <= 32 MB, 16 + 12wh <= 16 MB (=> w*h <= 1,398,100),
 * padded image <= 32 MB.  sr_image_fits() checks them at run time; the _Static_asserts below check the map itself at compile time. */
#ifndef SR_MEMMAP_H
#define SR_MEMMAP_H

#define SR_DDR_START        0x00000000u
#define SR_DDR_END          0x20000000u      /* exclusive */
#define SR_PROGRAM_START    0x00100000u      /* lscript.ld ORIGIN */

#define SR_IN_ADDR          0x10000000u
#define SR_IN_SIZE          0x02000000u
#define SR_OUT_ADDR         0x12000000u
#define SR_OUT_SIZE         0x01000000u
#define SR_MARK_ADDR        0x13000000u
#define SR_MARK_SIZE        0x00000040u
#define SR_PAD_ADDR         0x14000000u
#define SR_PAD_SIZE         0x02000000u
#define SR_TILE_IN_ADDR     0x16000000u
#define SR_TILE_IN_SIZE     0x00010000u
#define SR_TILE_OUT_ADDR    0x16100000u
#define SR_TILE_OUT_SIZE    0x00010000u

/* status block written by main.c at SR_MARK_ADDR (u32 words) */
#define SR_MARK_MAGIC       0x52454459u      /* "REDY": written LAST, when everything else in the block and the output image are in DDR */
#define SR_MARK_W_MAGIC     0
#define SR_MARK_W_RESULT    1                /* 0 = ok, otherwise an SR_RC_* error code (sr_driver.h) */
#define SR_MARK_W_BYTES     2                /* size of the output file in bytes (16 + 12wh) */
#define SR_MARK_W_FNV       3                /* FNV-1a 32 of the output payload */
#define SR_MARK_W_TILES     4
#define SR_MARK_W_TEST      5                /* which test wrote it (1, 2 or 3) */

#define SR_REGION_OK(base, size) ((base) >= SR_PROGRAM_START && (base) + (size) <= SR_DDR_END && ((base) & 63u) == 0u)
_Static_assert(SR_REGION_OK(SR_IN_ADDR, SR_IN_SIZE) && SR_REGION_OK(SR_OUT_ADDR, SR_OUT_SIZE) && SR_REGION_OK(SR_MARK_ADDR, SR_MARK_SIZE) &&
               SR_REGION_OK(SR_PAD_ADDR, SR_PAD_SIZE) && SR_REGION_OK(SR_TILE_IN_ADDR, SR_TILE_IN_SIZE) && SR_REGION_OK(SR_TILE_OUT_ADDR, SR_TILE_OUT_SIZE),
               "a region is outside DDR, below the program start or not 64-byte aligned");
_Static_assert(SR_IN_ADDR + SR_IN_SIZE <= SR_OUT_ADDR && SR_OUT_ADDR + SR_OUT_SIZE <= SR_MARK_ADDR && SR_MARK_ADDR + SR_MARK_SIZE <= SR_PAD_ADDR &&
               SR_PAD_ADDR + SR_PAD_SIZE <= SR_TILE_IN_ADDR && SR_TILE_IN_ADDR + SR_TILE_IN_SIZE <= SR_TILE_OUT_ADDR, "regions overlap or are out of order");
_Static_assert(SR_IN_ADDR >= 0x01000000u, "the program area (16 MB from 0x100000) must stay free of data buffers");

#endif
