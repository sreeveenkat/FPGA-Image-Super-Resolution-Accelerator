/* Register map of sr_accel_top, whole-frame PIPELINE version (branch `pipe`, hardware/rtl/top/sr_accel_top.v) - the ONE C view of it.
 * Pure constants, no Xilinx headers: usable on the ARM and on the PC.  Documented in docs/REGISTER_MAP.md.
 * software/board/test_regs.py FAILS if any value here disagrees with the Verilog (run by hardware/verification/run_tests.sh quick). */
#ifndef SR_REGS_H
#define SR_REGS_H

/* ---- register offsets (bytes from the base address of sr_accel_top on the AXI-Lite bus) */
#define SR_REG_CONTROL      0x00u   /* W : start / soft reset.  Reads 0 */
#define SR_REG_STATUS       0x04u   /* R : busy, done (sticky), error (sticky) */
#define SR_REG_FRAME_W      0x08u   /* RW: LR frame width W (1..MAX_W), sampled at start */
#define SR_REG_CYCLES       0x0Cu   /* R : clock cycles from the accepted start to the last output beat of the frame */
#define SR_REG_ERROR_CODE   0x10u   /* R : 0 none, 1..5 see below (first error of the frame) */
#define SR_REG_VERSION      0x14u   /* R : fixed constant */
#define SR_REG_FRAME_H      0x18u   /* RW: LR frame height H (1..SR_MAX_H), sampled at start */
#define SR_REG_MAX_W        0x1Cu   /* R : largest W the line buffers hold */
#define SR_REG_DBG_IN_BEATS  0x20u  /* R : input beats accepted in the current / last frame */
#define SR_REG_DBG_OUT_BEATS 0x24u  /* R : output beats sent in the current / last frame */

/* ---- CONTROL bits (write; only bits written with wstrb[0] set count; both are one-cycle pulses) */
#define SR_CTRL_START       (1u << 0)  /* start one frame; ignored while busy; refused (ERROR_CODE 4) if FRAME_W/H are out of range; an accepted start clears DONE and ERROR */
#define SR_CTRL_SRESET      (1u << 1)  /* soft reset of the core; clears DONE and ERROR; aborts a frame */

/* ---- STATUS bits */
#define SR_STATUS_BUSY      (1u << 0)
#define SR_STATUS_DONE      (1u << 1)  /* sticky: last output beat was accepted by the DMA; cleared by the next accepted start or a soft reset */
#define SR_STATUS_ERROR     (1u << 2)  /* sticky: ERROR_CODE != 0 */

/* ---- ERROR_CODE values */
#define SR_ERR_NONE            0u
#define SR_ERR_EARLY_TLAST     1u   /* s_axis_tlast on an input beat that is not the last of the frame */
#define SR_ERR_MISSING_TLAST   2u   /* last input beat arrived without tlast */
#define SR_ERR_BAD_TKEEP       3u   /* s_axis_tkeep != 4'hF on an accepted input beat */
#define SR_ERR_BAD_SIZE        4u   /* START with FRAME_W = 0, FRAME_W > MAX_W, FRAME_H = 0 or FRAME_H > SR_MAX_H: refused, nothing runs */
#define SR_ERR_INTERNAL        5u   /* an internal FIFO was misused (never expected; a design error) */

/* ---- constants */
#define SR_VERSION          0x53525301u   /* "SR" 53 01 = whole-frame pipeline, R3q weights + anchor, 125 MHz; this tree's driver accepts only VERSION & 0xFFFFFF00 == 0x53525300 */
#define SR_VERSION_MASK     0xFFFFFF00u   /* the driver checks VERSION & mask == SR_VERSION & mask */
#define SR_MAX_W            1018u         /* MAX_W register of the default build (MAXW - 6, MAXW = 1024) */
#define SR_MAX_H            4096u         /* MAXH of sr_accel_top.v (H + 6 must fit the core's 16-bit row counters) */
#define SR_HALO             3u
/* frame sizes: input = replicate-padded (W+6) x (H+6) x 3 bytes, sent as whole 32-bit beats (the last one may carry 1..3 unused bytes) */
#define SR_FRAME_IN_BYTES(w, h)   (3u * ((w) + 2u * SR_HALO) * ((h) + 2u * SR_HALO))
#define SR_FRAME_IN_BEATS(w, h)   ((SR_FRAME_IN_BYTES(w, h) + 3u) / 4u)
#define SR_FRAME_OUT_BYTES(w, h)  (12u * (w) * (h))                 /* 2W x 2H x 3, always a multiple of 4 */
/* the golden tile of T1 (golden_tile.h, real0) is a 64 x 64 frame: 70 x 70 padded input, 128 x 128 output; the tiling code (T7) uses SR_HC too */
#define SR_HC               64u
#define SR_TILE_IN_W        (SR_HC + 2u * SR_HALO)          /* 70 */
#define SR_TILE_OUT_W       (2u * SR_HC)                    /* 128 */
#define SR_TILE_IN_BYTES    (SR_TILE_IN_W * SR_TILE_IN_W * 3u)    /* 14,700 */
#define SR_TILE_OUT_BYTES   (SR_TILE_OUT_W * SR_TILE_OUT_W * 3u)  /* 49,152 */

#endif /* SR_REGS_H */
