/* Driver for sr_accel_top, whole-frame PIPELINE version (branch `pipe`; AXI4-Lite registers + AXI DMA) - bare metal, Vitis 2024.1 SDT flow.
 * Register layout: ../sr_regs.h, docs/REGISTER_MAP.md.  The tiled driver it is derived from runs on the board since 2026-10-11; THIS version has not. */
#ifndef SR_DRIVER_H
#define SR_DRIVER_H

#include <stdint.h>
#include "xaxidma.h"
#include "sr_regs.h"

/* A9 global timer (see sr_driver.c); sr_init() enables it */
#define SR_DBG_WORDS 13
extern uint32_t sr_dbg[SR_DBG_WORDS];
void     sr_timer_init(void);
uint64_t sr_now_ticks(void);
uint64_t sr_ticks_per_sec(void);

/* Optional split of the time inside one sr_run_tile / sr_run_frame call.  Built ONLY with -DSR_TIMING_SPLIT (software/board/build_elf.sh <N> -DSR_TIMING_SPLIT with
 * SR_ELF_SUFFIX=_split); without the flag every SR_TS* macro in sr_driver.c is empty, so the production code is the same source as before.
 * sr_split[]: global-timer ticks of the LAST call: 0 busy check + register writes, 1 flush input, 2 flush output, 3 arm S2MM + MM2S + START, 4 wait loop (core compute
 * + whatever the DMA and polling add), 5 status/error checks + invalidate output + CYCLES read, 6 sum of 0..5.  sr_split_sum[] / sr_split_calls: the same, summed over calls. */
#ifdef SR_TIMING_SPLIT
#define SR_SPLIT_N 7
extern uint64_t sr_split[SR_SPLIT_N];
extern uint64_t sr_split_sum[SR_SPLIT_N];
extern uint32_t sr_split_calls;
#endif

/* Optional non-cacheable DMA buffers (compile-time flags, both OFF by default: the code is then the same as without this block).
 *   -DSR_NC_OUT : the output-image region [SR_OUT_ADDR, +SR_OUT_SIZE) = 0x12000000 + 16 MB = sections 0x120..0x12F (the DMA writes it)
 *   -DSR_NC_PAD : the padded-input region [SR_PAD_ADDR, +SR_PAD_SIZE) = 0x14000000 + 32 MB = sections 0x140..0x15F (the DMA reads it)
 * sr_nc_init() (main.c calls it once after sr_init) cleans + invalidates each region, then marks its 1 MB sections Normal Non-cacheable with Xil_SetTlbAttributes.
 * sr_run_frame_len() then skips the flush / invalidate of a buffer INSIDE such a region; for the padded input it drains the write buffers instead (DSB + PL310 cache
 * sync), so the DMA sees every byte the ARM wrote.  Buffers outside the regions (T1 / T5 tile buffers, test arrays) keep the cached path. */
#if defined(SR_NC_OUT) || defined(SR_NC_PAD)
void sr_nc_init(void);
void sr_write_drain(void);
#endif

/* Base address of sr_accel_top/s_axi: from the Vivado Address Editor of the block design (project m6_sr), 4K range.  Override with -DSR_BASE=... if the design changes.
 * A wrong value is dangerous: reading an address nobody decodes can hang the AXI bus or raise a data abort on the Zynq; sr_init() reads VERSION first for that reason. */
#ifndef SR_BASE
#define SR_BASE        0x40000000u
#endif
/* AXI DMA S_AXI_LITE base (axi_dma_0, 64K): 0x40400000 in the block design m6_sr, as in M0. */
#ifndef SR_DMA_BASE
#define SR_DMA_BASE    0x40400000u
#endif

/* return codes (0 = ok) */
typedef enum {
    SR_RC_OK = 0,
    SR_RC_DMA_INIT = 1,      /* XAxiDma_LookupConfig / CfgInitialize failed, or the DMA is not in simple mode */
    SR_RC_VERSION = 2,       /* VERSION register differs from SR_VERSION: wrong SR_BASE or wrong bitstream */
    SR_RC_TILE_SIZE = 3,     /* MAX_W register differs from SR_MAX_W (name kept from the tiled driver) */
    SR_RC_BUSY = 4,          /* core busy before the tile was started */
    SR_RC_DMA_START = 5,     /* XAxiDma_SimpleTransfer refused the transfer */
    SR_RC_TIMEOUT = 6,       /* STATUS.done or the DMA did not finish within about 1 second */
    SR_RC_HW_ERROR = 7,      /* STATUS.error set (see ERROR_CODE) */
    SR_RC_DMA_ERROR = 8,     /* DMA status register shows an error bit */
    SR_RC_RESET = 9,         /* soft reset did not leave STATUS idle */
    SR_RC_IMAGE = 10         /* bad image header or image too large for the memory map */
} sr_rc_t;

typedef struct {
    XAxiDma  dma;
    uintptr_t base;          /* SR_BASE */
    uint32_t last_cycles;    /* CYCLES register after the last successful tile */
    uint32_t last_error_code; /* ERROR_CODE register of the last tile that failed with SR_RC_HW_ERROR */
    uint32_t version;        /* VERSION register read by sr_init */
} sr_dev_t;

int      sr_init(sr_dev_t *d);                                   /* DMA init, VERSION / MAX_W check, DMA reset, core soft reset, STATUS idle + ERROR_CODE 0 */
int      sr_soft_reset(sr_dev_t *d);                             /* CONTROL.SRESET and wait until STATUS is idle */
int      sr_run_frame(sr_dev_t *d, const uint8_t *in, uint8_t *out, uint32_t w, uint32_t h);  /* in: padded (w+6)x(h+6)x3, out: 2w x 2h x 3; resets DMA + core after any error */
int      sr_run_frame_len(sr_dev_t *d, const uint8_t *in, uint8_t *out, uint32_t w, uint32_t h, uint32_t in_len, uint32_t out_len);   /* test only: wrong lengths on purpose */
int      sr_run_tile(sr_dev_t *d, const uint8_t *in, uint8_t *out); /* the golden tile as a 64 x 64 frame: in 14,700 B, out 49,152 B */
int      sr_run_tile_len(sr_dev_t *d, const uint8_t *in, uint8_t *out, uint32_t in_len, uint32_t out_len);   /* test only: wrong lengths on purpose */
int      sr_reset_all(sr_dev_t *d);                              /* core soft reset, DMA reset (wait), core soft reset, STATUS idle + ERROR_CODE 0 */
extern int sr_start_order;                                       /* 0 normal (MM2S armed before START), 1 START first (T6 experiment) */
extern int sr_last_recover;                                      /* result of the reset after the last failed tile (SR_RC_OK = the reset worked) */
void     sr_dump(const sr_dev_t *d, const char *why);            /* prints STATUS, ERROR_CODE, CYCLES and both DMA status registers */
uint32_t sr_reg_read(const sr_dev_t *d, uint32_t off);

#endif
