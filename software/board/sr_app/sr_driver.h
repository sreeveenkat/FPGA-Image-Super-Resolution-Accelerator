/* Driver for sr_accel_top (AXI4-Lite registers + AXI DMA) - bare metal, Vitis 2024.1 SDT flow.  Register layout: ../sr_regs.h, docs/REGISTER_MAP.md.
 * NOT RUN ON A BOARD YET: it compiles against the zed_platform BSP, nothing more is verified. */
#ifndef SR_DRIVER_H
#define SR_DRIVER_H

#include <stdint.h>
#include "xaxidma.h"
#include "sr_regs.h"

/* A9 global timer (see sr_driver.c); sr_init() enables it */
extern uint32_t sr_dbg[6];
void     sr_timer_init(void);
uint64_t sr_now_ticks(void);
uint64_t sr_ticks_per_sec(void);

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
    SR_RC_TILE_SIZE = 3,     /* TILE_SIZE register differs from SR_HC */
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
} sr_dev_t;

int      sr_init(sr_dev_t *d);                                   /* DMA init, VERSION / TILE_SIZE check, soft reset */
int      sr_soft_reset(sr_dev_t *d);                             /* CONTROL.SRESET and wait until STATUS is idle */
int      sr_run_tile(sr_dev_t *d, const uint8_t *in, uint8_t *out); /* in: 14,700 B, out: 49,152 B, both 64-byte aligned, in DDR */
void     sr_dump(const sr_dev_t *d, const char *why);            /* prints STATUS, ERROR_CODE, CYCLES and both DMA status registers */
uint32_t sr_reg_read(const sr_dev_t *d, uint32_t off);

#endif
