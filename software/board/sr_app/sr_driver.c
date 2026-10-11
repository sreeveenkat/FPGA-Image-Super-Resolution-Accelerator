#include "sr_driver.h"
#include "xil_cache.h"
#include "xil_io.h"
#include "xil_printf.h"
#include "xstatus.h"
#if defined(SDT)
#include "xiltimer.h"
#else
#include "xtime_l.h"
#endif

/* NOTE: in this BSP COUNTS_PER_SECOND expands to "XPAR_CPU_CORE_CLOCK_FREQ_HZ/2" WITHOUT outer parentheses, so wrap it before dividing by it. */
#define SR_TICKS_PER_SEC     ((XTime)(COUNTS_PER_SECOND))
#define SR_TIMEOUT_TICKS     SR_TICKS_PER_SEC            /* about 1 second */

static inline uint32_t reg_rd(const sr_dev_t *d, uint32_t off) { return Xil_In32(d->base + off); }
static inline void reg_wr(const sr_dev_t *d, uint32_t off, uint32_t v) { Xil_Out32(d->base + off, v); }
uint32_t sr_reg_read(const sr_dev_t *d, uint32_t off) { return reg_rd(d, off); }

static uint32_t dma_sr(const sr_dev_t *d, int dir)       /* dir: XAXIDMA_DMA_TO_DEVICE (MM2S) or XAXIDMA_DEVICE_TO_DMA (S2MM) */
{
    const uint32_t ch = (dir == XAXIDMA_DMA_TO_DEVICE) ? XAXIDMA_TX_OFFSET : XAXIDMA_RX_OFFSET;
    return XAxiDma_ReadReg(d->dma.RegBase, ch + XAXIDMA_SR_OFFSET);
}

void sr_dump(const sr_dev_t *d, const char *why)
{
    xil_printf("SR DUMP (%s): STATUS=0x%08x ERROR_CODE=%u CYCLES=%u MM2S_SR=0x%08x S2MM_SR=0x%08x\r\n", why,
               reg_rd(d, SR_REG_STATUS), reg_rd(d, SR_REG_ERROR_CODE), reg_rd(d, SR_REG_CYCLES),
               dma_sr(d, XAXIDMA_DMA_TO_DEVICE), dma_sr(d, XAXIDMA_DEVICE_TO_DMA));
}

/* wait until (STATUS & mask) == value, at most about 1 s */
static int wait_status(const sr_dev_t *d, uint32_t mask, uint32_t value)
{
    XTime t0, t;
    XTime_GetTime(&t0);
    do {
        if ((reg_rd(d, SR_REG_STATUS) & mask) == value) return 0;
        XTime_GetTime(&t);
    } while (t - t0 < SR_TIMEOUT_TICKS);
    return -1;
}

int sr_soft_reset(sr_dev_t *d)
{
    reg_wr(d, SR_REG_CONTROL, SR_CTRL_SRESET);
    /* the reset is a registered one-cycle pulse: STATUS is idle (busy = done = error = 0) a few cycles later */
    if (wait_status(d, SR_STATUS_BUSY | SR_STATUS_DONE | SR_STATUS_ERROR, 0) != 0) {
        sr_dump(d, "soft reset did not give idle STATUS");
        return SR_RC_RESET;
    }
    return SR_RC_OK;
}

int sr_init(sr_dev_t *d)
{
    d->base = SR_BASE;
    d->last_cycles = 0;
    XAxiDma_Config *cfg = XAxiDma_LookupConfig(SR_DMA_BASE);       /* SDT flow: takes the BASE ADDRESS, not a device id */
    if (cfg == NULL) { xil_printf("SR: DMA config for 0x%08x not found\r\n", (unsigned)SR_DMA_BASE); return SR_RC_DMA_INIT; }
    if (XAxiDma_CfgInitialize(&d->dma, cfg) != XST_SUCCESS) { xil_printf("SR: DMA init failed\r\n"); return SR_RC_DMA_INIT; }
    if (XAxiDma_HasSg(&d->dma)) { xil_printf("SR: DMA is in scatter-gather mode, simple mode expected\r\n"); return SR_RC_DMA_INIT; }
    XAxiDma_IntrDisable(&d->dma, XAXIDMA_IRQ_ALL_MASK, XAXIDMA_DEVICE_TO_DMA);     /* polling only */
    XAxiDma_IntrDisable(&d->dma, XAXIDMA_IRQ_ALL_MASK, XAXIDMA_DMA_TO_DEVICE);

    const uint32_t ver = reg_rd(d, SR_REG_VERSION);
    if (ver != SR_VERSION) {
        xil_printf("SR: VERSION 0x%08x, expected 0x%08x (wrong SR_BASE 0x%08x or wrong bitstream)\r\n", ver, (unsigned)SR_VERSION, (unsigned)SR_BASE);
        return SR_RC_VERSION;
    }
    const uint32_t hc = reg_rd(d, SR_REG_TILE_SIZE);
    if (hc != SR_HC) { xil_printf("SR: TILE_SIZE %u, expected %u\r\n", hc, (unsigned)SR_HC); return SR_RC_TILE_SIZE; }
    return sr_soft_reset(d);
}

/* After a timeout or an error: reset the core and the DMA so that the next tile can start from a clean state. */
static void recover(sr_dev_t *d)
{
    XTime t0, t;
    (void)sr_soft_reset(d);
    XAxiDma_Reset(&d->dma);
    XTime_GetTime(&t0);
    do { XTime_GetTime(&t); } while (!XAxiDma_ResetIsDone(&d->dma) && t - t0 < SR_TIMEOUT_TICKS);
    XAxiDma_IntrDisable(&d->dma, XAXIDMA_IRQ_ALL_MASK, XAXIDMA_DEVICE_TO_DMA);
    XAxiDma_IntrDisable(&d->dma, XAXIDMA_IRQ_ALL_MASK, XAXIDMA_DMA_TO_DEVICE);
}

int sr_run_tile(sr_dev_t *d, const uint8_t *in, uint8_t *out)
{
    int rc;
    if (reg_rd(d, SR_REG_STATUS) & SR_STATUS_BUSY) { sr_dump(d, "core busy before start"); return SR_RC_BUSY; }

    /* Caches: the DMA reads/writes DDR directly.  FLUSH (clean + invalidate) the input so the DMA sees the ARM's bytes, and flush the OUTPUT buffer too, so no
     * dirty line of it can be evicted later on top of the DMA's data; invalidate it again after the DMA is done so the ARM reads DDR, not stale cache lines. */
    Xil_DCacheFlushRange((UINTPTR)in, SR_TILE_IN_BYTES);
    Xil_DCacheFlushRange((UINTPTR)out, SR_TILE_OUT_BYTES);

    /* arm the receiver first, then the sender; the core takes no data before CONTROL.START, so the order of these three steps is free except that START comes last */
    if (XAxiDma_SimpleTransfer(&d->dma, (UINTPTR)out, SR_TILE_OUT_BYTES, XAXIDMA_DEVICE_TO_DMA) != XST_SUCCESS) { sr_dump(d, "S2MM start refused"); recover(d); return SR_RC_DMA_START; }
    if (XAxiDma_SimpleTransfer(&d->dma, (UINTPTR)in, SR_TILE_IN_BYTES, XAXIDMA_DMA_TO_DEVICE) != XST_SUCCESS) { sr_dump(d, "MM2S start refused"); recover(d); return SR_RC_DMA_START; }
    reg_wr(d, SR_REG_CONTROL, SR_CTRL_START);

    /* wait: core DONE (or ERROR) and both DMA channels idle, one shared timeout of about 1 s */
    XTime t0, t;
    XTime_GetTime(&t0);
    for (;;) {
        const uint32_t st = reg_rd(d, SR_REG_STATUS);
        const int dma_busy = XAxiDma_Busy(&d->dma, XAXIDMA_DMA_TO_DEVICE) || XAxiDma_Busy(&d->dma, XAXIDMA_DEVICE_TO_DMA);
        if ((st & SR_STATUS_ERROR) || ((st & SR_STATUS_DONE) && !dma_busy)) break;
        XTime_GetTime(&t);
        if (t - t0 > SR_TIMEOUT_TICKS) { sr_dump(d, "TIMEOUT"); recover(d); return SR_RC_TIMEOUT; }
    }

    const uint32_t st = reg_rd(d, SR_REG_STATUS);
    if (st & SR_STATUS_ERROR) { sr_dump(d, "core reported an error"); recover(d); return SR_RC_HW_ERROR; }
    if ((dma_sr(d, XAXIDMA_DMA_TO_DEVICE) | dma_sr(d, XAXIDMA_DEVICE_TO_DMA)) & XAXIDMA_ERR_ALL_MASK) { sr_dump(d, "DMA error bits"); recover(d); return SR_RC_DMA_ERROR; }

    Xil_DCacheInvalidateRange((UINTPTR)out, SR_TILE_OUT_BYTES);
    d->last_cycles = reg_rd(d, SR_REG_CYCLES);
    rc = SR_RC_OK;
    return rc;
}
