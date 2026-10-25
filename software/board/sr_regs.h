/* Register map of sr_accel_top (hardware/rtl/top/sr_accel_top.v) - the ONE C view of it.
 * Pure constants, no Xilinx headers: usable on the ARM and on the PC.  Documented in docs/REGISTER_MAP.md.
 * software/board/test_regs.py FAILS if any value here disagrees with the Verilog (run by hardware/verification/run_tests.sh quick). */
#ifndef SR_REGS_H
#define SR_REGS_H

/* ---- register offsets (bytes from the base address of sr_accel_top on the AXI-Lite bus) */
#define SR_REG_CONTROL      0x00u   /* W : start / soft reset.  Reads 0 */
#define SR_REG_STATUS       0x04u   /* R : busy, done (sticky), error (sticky) */
#define SR_REG_TILE_SIZE    0x08u   /* R : HC = core tile edge in input pixels */
#define SR_REG_CYCLES       0x0Cu   /* R : core clock cycles of the last / current tile */
#define SR_REG_ERROR_CODE   0x10u   /* R : 0 none, 1..3 see below (first error of the tile) */
#define SR_REG_VERSION      0x14u   /* R : fixed constant */
/* debug registers (VERSION 0x53520602 and later; read 0 on the first board version 0x53520601) */
#define SR_REG_DBG_IN_BEATS    0x18u   /* R : input beats accepted since the last accepted start */
#define SR_REG_DBG_TLAST_AT    0x1Cu   /* R : 1 + index of the first input beat with tlast since start (0 = none) */
#define SR_REG_DBG_START2BEAT  0x20u   /* R : [30:0] cycles start -> first accepted input beat, [31] tvalid was high at start */
#define SR_REG_DBG_PRE_BEATS   0x24u   /* R : input beats accepted while no tile was running (must be 0) */
#define SR_REG_DBG_STARTS      0x28u   /* R : [15:0] accepted starts, [31:16] ignored starts, since the PL reset */
#define SR_REG_DBG_ERR_BEATS   0x2Cu   /* R : DBG_IN_BEATS when the first error of the tile was recorded */
#define SR_REG_DBG_ERR_CYCLES  0x30u   /* R : CYCLES when the first error of the tile was recorded */

/* ---- CONTROL bits (write; only bits written with wstrb[0] set count; both are one-cycle pulses) */
#define SR_CTRL_START       (1u << 0)  /* start one tile; ignored while busy; an accepted start clears DONE and ERROR */
#define SR_CTRL_SRESET      (1u << 1)  /* soft reset of the core + wrapper; clears DONE and ERROR */

/* ---- STATUS bits */
#define SR_STATUS_BUSY      (1u << 0)
#define SR_STATUS_DONE      (1u << 1)  /* sticky: last output beat was accepted by the DMA; cleared by the next accepted start or a soft reset */
#define SR_STATUS_ERROR     (1u << 2)  /* sticky: ERROR_CODE != 0 */

/* ---- ERROR_CODE values */
#define SR_ERR_NONE            0u
#define SR_ERR_EARLY_TLAST     1u   /* s_axis_tlast on an input beat that is not the last of the tile */
#define SR_ERR_MISSING_TLAST   2u   /* last input beat arrived without tlast */
#define SR_ERR_BAD_TKEEP       3u   /* s_axis_tkeep != 4'hF on an accepted input beat */

/* ---- constants */
#define SR_VERSION          0x53524201u   /* "SR" 42 01 = R0 at 125 MHz (fmax_plan.md); deployed R0 is 0x53520602; this tree's driver accepts only VERSION & 0xFFFFFF00 == 0x53524200 */
#define SR_VERSION_MASK     0xFFFFFF00u   /* the driver checks VERSION & mask == SR_VERSION & mask */
#define SR_HC               64u           /* TILE_SIZE the bitstream is built with (sr_accel_top parameter HC) */
#define SR_HALO             3u
#define SR_TILE_IN_W        (SR_HC + 2u * SR_HALO)          /* 70 : input tile edge incl. halo */
#define SR_TILE_OUT_W       (2u * SR_HC)                    /* 128 : output tile edge */
#define SR_TILE_IN_BYTES    (SR_TILE_IN_W * SR_TILE_IN_W * 3u)    /* 14,700 */
#define SR_TILE_OUT_BYTES   (SR_TILE_OUT_W * SR_TILE_OUT_W * 3u)  /* 49,152 */

#endif /* SR_REGS_H */
