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
#define SR_TICKS_PER_SEC     ((uint64_t)(COUNTS_PER_SECOND))
#define SR_TIMEOUT_TICKS     SR_TICKS_PER_SEC            /* about 1 second */

/* Cortex-A9 global timer, read directly.  XTime_GetTime() of this SDT BSP gave 0 on the board (first run: "tile time 0 us"); the cause was not isolated (most likely the timer
 * was never started).  Reading the global timer directly, after setting its enable bit, works (checked against CYCLES).  With a dead timer the 1 s timeouts
 * below would never have fired either.  The timer counts at CPU_CLK/2 = COUNTS_PER_SECOND. */
#define SR_GTMR_BASE   0xF8F00200u
#define SR_GTMR_LO     0x00u
#define SR_GTMR_HI     0x04u
#define SR_GTMR_CTRL   0x08u

void sr_timer_init(void)
{
    Xil_Out32(SR_GTMR_BASE + SR_GTMR_CTRL, Xil_In32(SR_GTMR_BASE + SR_GTMR_CTRL) | 1u);   /* bit 0 = timer enable */
}

uint64_t sr_now_ticks(void)
{
    uint32_t hi, lo;
    do {
        hi = Xil_In32(SR_GTMR_BASE + SR_GTMR_HI);
        lo = Xil_In32(SR_GTMR_BASE + SR_GTMR_LO);
    } while (Xil_In32(SR_GTMR_BASE + SR_GTMR_HI) != hi);
    return ((uint64_t)hi << 32) | lo;
}

uint64_t sr_ticks_per_sec(void) { return SR_TICKS_PER_SEC; }

/* Timing split of one transfer, compiled in only with -DSR_TIMING_SPLIT (see sr_driver.h); empty macros otherwise. */
#ifdef SR_TIMING_SPLIT
uint64_t sr_split[SR_SPLIT_N], sr_split_sum[SR_SPLIT_N];
uint32_t sr_split_calls;
#define SR_TS_BEGIN()  uint64_t sr_ts_prev = sr_now_ticks(); const uint64_t sr_ts_start = sr_ts_prev
#define SR_TS(i)       do { const uint64_t sr_ts_now = sr_now_ticks(); sr_split[i] = sr_ts_now - sr_ts_prev; sr_ts_prev = sr_ts_now; } while (0)
#define SR_TS_END()    do { sr_split[6] = sr_ts_prev - sr_ts_start; for (int sr_k = 0; sr_k < SR_SPLIT_N; sr_k++) sr_split_sum[sr_k] += sr_split[sr_k]; sr_split_calls++; } while (0)
#else
#define SR_TS_BEGIN()
#define SR_TS(i)
#define SR_TS_END()
#endif

static inline uint32_t reg_rd(const sr_dev_t *d, uint32_t off) { return Xil_In32(d->base + off); }
static inline void reg_wr(const sr_dev_t *d, uint32_t off, uint32_t v) { Xil_Out32(d->base + off, v); }
uint32_t sr_reg_read(const sr_dev_t *d, uint32_t off) { return reg_rd(d, off); }

static uint32_t dma_sr(const sr_dev_t *d, int dir)       /* dir: XAXIDMA_DMA_TO_DEVICE (MM2S) or XAXIDMA_DEVICE_TO_DMA (S2MM) */
{
    const uint32_t ch = (dir == XAXIDMA_DMA_TO_DEVICE) ? XAXIDMA_TX_OFFSET : XAXIDMA_RX_OFFSET;
    return XAxiDma_ReadReg(d->dma.RegBase, ch + XAXIDMA_SR_OFFSET);
}

uint32_t sr_dbg[SR_DBG_WORDS];   /* FIRST sr_dump() since start: STATUS, ERROR_CODE, CYCLES, MM2S_SR, S2MM_SR, number of dumps, then (VERSION >= 0x53520602) the
                                    debug registers IN_BEATS, TLAST_AT, START2BEAT, PRE_BEATS, STARTS, ERR_BEATS, ERR_CYCLES (main.c copies it into the DDR marker) */

void sr_dump(const sr_dev_t *d, const char *why)
{
    if (sr_dbg[5] == 0) {
        sr_dbg[0] = reg_rd(d, SR_REG_STATUS); sr_dbg[1] = reg_rd(d, SR_REG_ERROR_CODE); sr_dbg[2] = reg_rd(d, SR_REG_CYCLES);
        sr_dbg[3] = dma_sr(d, XAXIDMA_DMA_TO_DEVICE); sr_dbg[4] = dma_sr(d, XAXIDMA_DEVICE_TO_DMA);
        if (d->version >= 0x53520602u)
            for (uint32_t k = 0; k < 7; k++) sr_dbg[6 + k] = reg_rd(d, SR_REG_DBG_IN_BEATS + 4u * k);
    }
    sr_dbg[5]++;
    xil_printf("SR DUMP (%s): STATUS=0x%08x ERROR_CODE=%u CYCLES=%u MM2S_SR=0x%08x S2MM_SR=0x%08x\r\n", why,
               reg_rd(d, SR_REG_STATUS), reg_rd(d, SR_REG_ERROR_CODE), reg_rd(d, SR_REG_CYCLES),
               dma_sr(d, XAXIDMA_DMA_TO_DEVICE), dma_sr(d, XAXIDMA_DEVICE_TO_DMA));
}

/* wait until (STATUS & mask) == value, at most about 1 s */
static int wait_status(const sr_dev_t *d, uint32_t mask, uint32_t value)
{
    uint64_t t0, t;
    t0 = sr_now_ticks();
    do {
        if ((reg_rd(d, SR_REG_STATUS) & mask) == value) return 0;
        t = sr_now_ticks();
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
    if (reg_rd(d, SR_REG_ERROR_CODE) != SR_ERR_NONE) { sr_dump(d, "ERROR_CODE not 0 after soft reset"); return SR_RC_RESET; }
    return SR_RC_OK;
}

/* Reset the AXI DMA (both channels) and wait until the reset is done, about 1 s at most.  Aborts any transfer a previous program left behind
 * (on the board this also worked with the MM2S channel blocked half-way, see results/speed/m6_board.md). */
static int dma_reset(sr_dev_t *d)
{
    uint64_t t0, t;
    XAxiDma_Reset(&d->dma);
    t0 = sr_now_ticks();
    do {
        if (XAxiDma_ResetIsDone(&d->dma)) {
            XAxiDma_IntrDisable(&d->dma, XAXIDMA_IRQ_ALL_MASK, XAXIDMA_DEVICE_TO_DMA);     /* polling only */
            XAxiDma_IntrDisable(&d->dma, XAXIDMA_IRQ_ALL_MASK, XAXIDMA_DMA_TO_DEVICE);
            return SR_RC_OK;
        }
        t = sr_now_ticks();
    } while (t - t0 < SR_TIMEOUT_TICKS);
    sr_dump(d, "DMA reset did not finish");
    return SR_RC_DMA_INIT;
}

/* Clean start from ANY state (also a DMA or core left in the middle of a tile by an earlier, interrupted program):
 *   1. core soft reset: the core stops sending output words (otherwise the S2MM channel may take some of them into its FIFO during/after its reset; on the board
 *      a DMA-then-core order gave a WRONG next tile after a "S2MM buffer too short" error, see results/speed/m6_board.md),
 *   2. DMA reset, wait until done: aborts both channels (also an MM2S transfer that is blocked half-way),
 *   3. core soft reset again (anything the DMA pushed into the core before/while it was reset is dropped), then STATUS idle and ERROR_CODE 0 are checked. */
int sr_reset_all(sr_dev_t *d)
{
    (void)sr_soft_reset(d);
    const int rc = dma_reset(d);
    if (rc != SR_RC_OK) return rc;
    return sr_soft_reset(d);
}

int sr_init(sr_dev_t *d)
{
    sr_timer_init();
    d->base = SR_BASE;
    d->last_cycles = 0;
    d->last_error_code = 0;
    d->version = 0;
    /* VERSION first: a program built for another bitstream must stop here, before anything is written to the DMA (XAxiDma_CfgInitialize resets it) or to the core. */
    const uint32_t ver = reg_rd(d, SR_REG_VERSION);
    d->version = ver;
    if ((ver & SR_VERSION_MASK) != (SR_VERSION & SR_VERSION_MASK)) {
        xil_printf("SR: VERSION 0x%08x, expected 0x%08x (wrong SR_BASE 0x%08x or wrong bitstream)\r\n", ver, (unsigned)SR_VERSION, (unsigned)SR_BASE);
        return SR_RC_VERSION;
    }

    XAxiDma_Config *cfg = XAxiDma_LookupConfig(SR_DMA_BASE);       /* SDT flow: takes the BASE ADDRESS, not a device id */
    if (cfg == NULL) { xil_printf("SR: DMA config for 0x%08x not found\r\n", (unsigned)SR_DMA_BASE); return SR_RC_DMA_INIT; }
    if (XAxiDma_CfgInitialize(&d->dma, cfg) != XST_SUCCESS) { xil_printf("SR: DMA init failed\r\n"); return SR_RC_DMA_INIT; }
    if (XAxiDma_HasSg(&d->dma)) { xil_printf("SR: DMA is in scatter-gather mode, simple mode expected\r\n"); return SR_RC_DMA_INIT; }

    const uint32_t hc = reg_rd(d, SR_REG_TILE_SIZE);
    if (hc != SR_HC) { xil_printf("SR: TILE_SIZE %u, expected %u\r\n", hc, (unsigned)SR_HC); return SR_RC_TILE_SIZE; }
    return sr_reset_all(d);                                           /* (XAxiDma_CfgInitialize resets the DMA too, but with a loop-count timeout and before the core) */
}

/* After a timeout or an error: core, DMA, core reset (sr_reset_all), so that the next tile starts from a clean state.  Its result is kept for the caller (sr_last_recover). */
int sr_last_recover = SR_RC_OK;
int sr_start_order = 0;      /* 0: arm S2MM, arm MM2S, write START (normal);  1: arm S2MM, write START, arm MM2S (T6 experiment) */
static void recover(sr_dev_t *d) { sr_last_recover = sr_reset_all(d); }

int sr_run_tile(sr_dev_t *d, const uint8_t *in, uint8_t *out) { return sr_run_tile_len(d, in, out, SR_TILE_IN_BYTES, SR_TILE_OUT_BYTES); }

/* in_len / out_len other than the tile sizes only for the recovery test (main.c SR_TEST=5): they make the stream or the DMA fail on purpose */
int sr_run_tile_len(sr_dev_t *d, const uint8_t *in, uint8_t *out, uint32_t in_len, uint32_t out_len)
{
    int rc;
    SR_TS_BEGIN();
    if (reg_rd(d, SR_REG_STATUS) & SR_STATUS_BUSY) { sr_dump(d, "core busy before start"); recover(d); return SR_RC_BUSY; }
    SR_TS(0);

    /* Caches: the DMA reads/writes DDR directly.  FLUSH (clean + invalidate) the input so the DMA sees the ARM's bytes, and flush the OUTPUT buffer too, so no
     * dirty line of it can be evicted later on top of the DMA's data; invalidate it again after the DMA is done so the ARM reads DDR, not stale cache lines. */
    Xil_DCacheFlushRange((UINTPTR)in, SR_TILE_IN_BYTES);
    SR_TS(1);
    Xil_DCacheFlushRange((UINTPTR)out, SR_TILE_OUT_BYTES);
    SR_TS(2);

    /* arm the receiver first, then the sender; the core takes no data before CONTROL.START, so the order of these three steps is free except that START comes last */
    if (XAxiDma_SimpleTransfer(&d->dma, (UINTPTR)out, out_len, XAXIDMA_DEVICE_TO_DMA) != XST_SUCCESS) { sr_dump(d, "S2MM start refused"); recover(d); return SR_RC_DMA_START; }
    if (sr_start_order == 0) {
        if (XAxiDma_SimpleTransfer(&d->dma, (UINTPTR)in, in_len, XAXIDMA_DMA_TO_DEVICE) != XST_SUCCESS) { sr_dump(d, "MM2S start refused"); recover(d); return SR_RC_DMA_START; }
        reg_wr(d, SR_REG_CONTROL, SR_CTRL_START);
    } else {                                                        /* order 1 (T6 experiment): START before the input DMA is armed */
        reg_wr(d, SR_REG_CONTROL, SR_CTRL_START);
        if (XAxiDma_SimpleTransfer(&d->dma, (UINTPTR)in, in_len, XAXIDMA_DMA_TO_DEVICE) != XST_SUCCESS) { sr_dump(d, "MM2S start refused"); recover(d); return SR_RC_DMA_START; }
    }
    SR_TS(3);

    /* wait: core DONE (or ERROR) and both DMA channels idle, one shared timeout of about 1 s */
    uint64_t t0, t;
    t0 = sr_now_ticks();
    for (;;) {
        const uint32_t st = reg_rd(d, SR_REG_STATUS);
        const int dma_busy = XAxiDma_Busy(&d->dma, XAXIDMA_DMA_TO_DEVICE) || XAxiDma_Busy(&d->dma, XAXIDMA_DEVICE_TO_DMA);
        if ((st & SR_STATUS_ERROR) || ((st & SR_STATUS_DONE) && !dma_busy)) break;
        t = sr_now_ticks();
        if (t - t0 > SR_TIMEOUT_TICKS) { sr_dump(d, "TIMEOUT"); recover(d); return SR_RC_TIMEOUT; }
    }
    SR_TS(4);

    const uint32_t st = reg_rd(d, SR_REG_STATUS);
    if (st & SR_STATUS_ERROR) { d->last_error_code = reg_rd(d, SR_REG_ERROR_CODE); sr_dump(d, "core reported an error"); recover(d); return SR_RC_HW_ERROR; }
    if ((dma_sr(d, XAXIDMA_DMA_TO_DEVICE) | dma_sr(d, XAXIDMA_DEVICE_TO_DMA)) & XAXIDMA_ERR_ALL_MASK) { sr_dump(d, "DMA error bits"); recover(d); return SR_RC_DMA_ERROR; }

    Xil_DCacheInvalidateRange((UINTPTR)out, SR_TILE_OUT_BYTES);
    d->last_cycles = reg_rd(d, SR_REG_CYCLES);
    SR_TS(5);
    SR_TS_END();
    rc = SR_RC_OK;
    return rc;
}
