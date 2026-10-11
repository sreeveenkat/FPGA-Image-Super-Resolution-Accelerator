/* Super-resolution accelerator test program (bare metal, ZedBoard).  NOT RUN ON A BOARD YET - compiled against the zed_platform BSP only.
 *
 * Select the test at build time (-DSR_TEST=n) or leave SR_TEST = 0 for a menu over the UART (115200 baud, /dev/ttyACM0):
 *   T1 golden tile   : the real0 tile from golden_tile.h goes through DMA + core; all 49,152 output bytes are compared; CYCLES is printed; then the same tile
 *                      is run 20 times and every result must be identical (and equal to the golden output).
 *   T2 full image    : the SRIM image at SR_IN_ADDR (put there by the host with xsdb, see run_board.tcl) is padded, cut into tiles, every tile is run on the
 *                      core, the result is written as SRIM to SR_OUT_ADDR.  Then the ready marker is written at SR_MARK_ADDR and printed.
 *   T3 timing        : like T2, SR_T3_FRAMES times; per frame the time is split into padding / ARM tile copies (cut + place) / DMA + compute wait,
 *                      then mean / min / max per frame and CYCLES per tile.
 * Memory map: sr_memmap.h.  Register map: ../sr_regs.h and docs/REGISTER_MAP.md.  Output is plain xil_printf (no floating point, no 64-bit formats). */
#include <stdint.h>
#include <string.h>
#include "xil_cache.h"
#include "xil_io.h"
#include "xil_printf.h"
#if defined(SDT)
#include "xiltimer.h"
#else
#include "xtime_l.h"
#endif
#include "sr_driver.h"
#include "sr_memmap.h"
#include "sr_tiling.h"
#include "golden_tile.h"      /* generated: software/host_tools/golden_tile_h.py */

#ifndef SR_TEST
#define SR_TEST 0             /* 0 = UART menu, 1, 2 or 3 = run that test and stop */
#endif
#ifndef SR_T3_FRAMES
#define SR_T3_FRAMES 5
#endif

#define SR_MAYBE_UNUSED __attribute__((unused))   /* a build with -DSR_TEST=n uses only one of the three tests */
char inbyte(void);            /* from the BSP (blocking UART read) */
extern char _stack __attribute__((weak)); /* top of the stack = highest address of the program image in lscript.ld (this script has no _end symbol) */

#define TICKS_PER_SEC ((XTime)(COUNTS_PER_SECOND))   /* the BSP macro has no outer parentheses */
static uint32_t ticks_to_us(uint64_t t) { return (uint32_t)((t * 1000000ull) / TICKS_PER_SEC); }
static uint64_t now_ticks(void) { XTime t; XTime_GetTime(&t); return t; }

static sr_dev_t dev;

/* ------------------------------------------------------------------ memory map sanity (run time part)
 * The program is linked at 0x00100000 (lscript.ld): code, rodata, data, bss, heap and finally the stack.  _stack is the top of the stack = the highest address the
 * program uses; it must stay below the first data buffer (SR_IN_ADDR).  (Measured when linked against zed_platform: program ends at 0x00120870.) */
static int check_memory_map(void)
{
    const uintptr_t prog_end = (uintptr_t)&_stack;
    xil_printf("memory: program 0x%08x - 0x%08x (top of stack), in 0x%08x, out 0x%08x, mark 0x%08x, pad 0x%08x, tile in/out 0x%08x/0x%08x\r\n",
               (unsigned)SR_PROGRAM_START, (unsigned)prog_end, (unsigned)SR_IN_ADDR, (unsigned)SR_OUT_ADDR, (unsigned)SR_MARK_ADDR, (unsigned)SR_PAD_ADDR,
               (unsigned)SR_TILE_IN_ADDR, (unsigned)SR_TILE_OUT_ADDR);
    if (prog_end == 0) xil_printf("WARNING: symbol _stack not found, the program-overlap check is skipped\r\n");
    if (prog_end != 0 && prog_end >= SR_IN_ADDR) { xil_printf("ERROR: the program (end 0x%08x) overlaps the input buffer\r\n", (unsigned)prog_end); return -1; }
    return 0;
}

/* ------------------------------------------------------------------ T1 */
static int compare_tile(const uint8_t *got, const uint8_t *exp, uint32_t n, const char *what)
{
    uint32_t bad = 0;
    for (uint32_t i = 0; i < n; i++) {
        if (got[i] != exp[i]) {
            if (bad < 10) xil_printf("  %s mismatch at byte %u (pixel %u, c %u): got %u expected %u\r\n", what, i, i / 3, i % 3, got[i], exp[i]);
            bad++;
        }
    }
    return (int)bad;
}

SR_MAYBE_UNUSED static int test1(void)
{
    uint8_t *out = (uint8_t *)SR_TILE_OUT_ADDR;
    uint8_t *first = (uint8_t *)SR_PAD_ADDR;      /* work area: copy of the first result (the padded-image buffer is not used in this test) */
    int rc;
    xil_printf("T1: golden tile (real0), %u bytes in, %u bytes out\r\n", (unsigned)SR_TILE_IN_BYTES, (unsigned)SR_TILE_OUT_BYTES);
    memset(out, 0xA5, SR_TILE_OUT_BYTES);
    uint64_t t0 = now_ticks();
    rc = sr_run_tile(&dev, sr_golden_in, out);
    uint64_t t1 = now_ticks();
    if (rc != SR_RC_OK) { xil_printf("T1 FAIL: sr_run_tile returned %d\r\n", rc); return rc; }
    const int bad = compare_tile(out, sr_golden_out, SR_TILE_OUT_BYTES, "golden");
    xil_printf("T1: CYCLES = %u (expected 926202 in simulation), tile time %u us (DMA + compute)\r\n", dev.last_cycles, ticks_to_us(t1 - t0));
    if (bad) { xil_printf("T1 FAIL: %d of %u bytes differ from the golden output\r\n", bad, (unsigned)SR_TILE_OUT_BYTES); return -1; }
    xil_printf("T1: first run: all %u bytes identical to the golden output\r\n", (unsigned)SR_TILE_OUT_BYTES);
    memcpy(first, out, SR_TILE_OUT_BYTES);

    int identical = 0, cyc_changed = 0;
    const uint32_t cyc0 = dev.last_cycles;
    for (int run = 1; run <= 20; run++) {
        memset(out, 0xA5, SR_TILE_OUT_BYTES);
        rc = sr_run_tile(&dev, sr_golden_in, out);
        if (rc != SR_RC_OK) { xil_printf("T1 FAIL: run %d returned %d\r\n", run, rc); return rc; }
        if (compare_tile(out, first, SR_TILE_OUT_BYTES, "repeat") == 0) identical++;
        if (dev.last_cycles != cyc0) cyc_changed++;
    }
    xil_printf("T1: %d of 20 repeated runs identical to the first (CYCLES changed in %d runs)\r\n", identical, cyc_changed);
    if (identical != 20) { xil_printf("T1 FAIL\r\n"); return -1; }
    xil_printf("T1 PASS\r\n");
    return 0;
}

/* ------------------------------------------------------------------ T2 / T3 helpers */
typedef struct { sr_dev_t *d; uint32_t cyc_min, cyc_max; uint64_t cyc_sum; uint32_t n; } tile_ctx_t;
static int tile_cb(void *ctx, const uint8_t *in, uint8_t *out)
{
    tile_ctx_t *c = ctx;
    int rc = sr_run_tile(c->d, in, out);
    if (rc == SR_RC_OK) {
        const uint32_t cy = c->d->last_cycles;
        if (c->n == 0 || cy < c->cyc_min) c->cyc_min = cy;
        if (c->n == 0 || cy > c->cyc_max) c->cyc_max = cy;
        c->cyc_sum += cy;
        c->n++;
    }
    return rc;
}

static int image_fits(uint32_t w, uint32_t h, sr_geom_t *g)
{
    if (w == 0 || h == 0 || w > 8192 || h > 8192) return 0;
    sr_geom(w, h, g);
    return (16u + 3u * (uint64_t)w * h <= SR_IN_SIZE) && (16u + (uint64_t)sr_out_bytes(g) <= SR_OUT_SIZE) && (sr_padded_bytes(g) <= SR_PAD_SIZE);
}

static int read_input_header(sr_geom_t *g)
{
    const uint32_t *hd = (const uint32_t *)SR_IN_ADDR;
    Xil_DCacheInvalidateRange((UINTPTR)SR_IN_ADDR, 64);          /* the host wrote it over JTAG, never through our cache */
    if (memcmp((const void *)SR_IN_ADDR, "SRIM", 4) != 0) { xil_printf("ERROR: no SRIM image at 0x%08x (magic 0x%08x)\r\n", (unsigned)SR_IN_ADDR, hd[0]); return SR_RC_IMAGE; }
    const uint32_t w = hd[1], h = hd[2];
    if (!image_fits(w, h, g)) { xil_printf("ERROR: image %ux%u does not fit the memory map\r\n", w, h); return SR_RC_IMAGE; }
    /* the pixel data may be partly cached from an earlier run: drop it so the ARM reads what the host put into DDR */
    Xil_DCacheInvalidateRange((UINTPTR)SR_IN_ADDR, 16u + 3u * w * h);
    return SR_RC_OK;
}

static void write_marker(uint32_t result, uint32_t bytes, uint32_t fnv, uint32_t tiles, uint32_t test)
{
    volatile uint32_t *m = (volatile uint32_t *)SR_MARK_ADDR;
    m[SR_MARK_W_MAGIC] = 0;
    m[SR_MARK_W_RESULT] = result; m[SR_MARK_W_BYTES] = bytes; m[SR_MARK_W_FNV] = fnv; m[SR_MARK_W_TILES] = tiles; m[SR_MARK_W_TEST] = test;
    Xil_DCacheFlushRange((UINTPTR)SR_MARK_ADDR, SR_MARK_SIZE);
    m[SR_MARK_W_MAGIC] = SR_MARK_MAGIC;                          /* last: the host polls this word */
    Xil_DCacheFlushRange((UINTPTR)SR_MARK_ADDR, SR_MARK_SIZE);
}

/* one frame; fills the timing split.  Returns 0 or an error code. */
static int process_frame(const sr_geom_t *g, tile_ctx_t *tc, uint64_t *t_pad, sr_timing_t *tm, uint64_t *t_total)
{
    const uint8_t *lr = (const uint8_t *)(SR_IN_ADDR + 16);
    uint8_t *padded = (uint8_t *)SR_PAD_ADDR;
    uint8_t *out = (uint8_t *)(SR_OUT_ADDR + 16);
    const uint64_t t0 = now_ticks();
    sr_pad_image(lr, g, padded);
    const uint64_t t1 = now_ticks();
    const int rc = sr_upscale_padded(padded, g, out, (uint8_t *)SR_TILE_IN_ADDR, (uint8_t *)SR_TILE_OUT_ADDR, tile_cb, tc, now_ticks, tm);
    const uint64_t t2 = now_ticks();
    *t_pad = t1 - t0;
    *t_total = t2 - t0;
    return rc;
}

static void write_output_header(const sr_geom_t *g)
{
    uint32_t *o = (uint32_t *)SR_OUT_ADDR;
    memcpy(o, "SRIM", 4);
    o[1] = 2u * g->w; o[2] = 2u * g->h; o[3] = 0;
}

static int finish_output(const sr_geom_t *g, uint32_t tiles, uint32_t test)
{
    const uint32_t bytes = 16u + (uint32_t)sr_out_bytes(g);
    Xil_DCacheFlushRange((UINTPTR)SR_OUT_ADDR, bytes);            /* the host reads DDR over JTAG: write the cache back first */
    const uint32_t fnv = sr_fnv1a32((const uint8_t *)(SR_OUT_ADDR + 16), sr_out_bytes(g));
    write_marker(0, bytes, fnv, tiles, test);
    xil_printf("SR_READY test=%u out=0x%08x bytes=%u tiles=%u fnv1a32=0x%08x\r\n", test, (unsigned)SR_OUT_ADDR, bytes, tiles, fnv);
    return 0;
}

/* ------------------------------------------------------------------ T2 */
SR_MAYBE_UNUSED static int test2(void)
{
    sr_geom_t g;
    xil_printf("T2: full image from 0x%08x\r\n", (unsigned)SR_IN_ADDR);
    write_marker(0, 0, 0, 0, 0); ((volatile uint32_t *)SR_MARK_ADDR)[SR_MARK_W_MAGIC] = 0; Xil_DCacheFlushRange((UINTPTR)SR_MARK_ADDR, SR_MARK_SIZE);   /* clear the marker */
    int rc = read_input_header(&g);
    if (rc) { write_marker((uint32_t)rc, 0, 0, 0, 2); return rc; }
    xil_printf("T2: %ux%u -> %ux%u, %u x %u = %u tiles\r\n", g.w, g.h, 2 * g.w, 2 * g.h, g.tiles_x, g.tiles_y, g.tiles_x * g.tiles_y);
    tile_ctx_t tc = { &dev, 0, 0, 0, 0 };
    sr_timing_t tm; uint64_t tp, tt;
    write_output_header(&g);
    rc = process_frame(&g, &tc, &tp, &tm, &tt);
    if (rc) { xil_printf("T2 FAIL: tile %u returned %d\r\n", tm.tiles, rc); write_marker((uint32_t)rc, 0, 0, tm.tiles, 2); return rc; }
    xil_printf("T2: %u tiles done in %u ms, CYCLES per tile min/max %u/%u\r\n", tm.tiles, ticks_to_us(tt) / 1000u, tc.cyc_min, tc.cyc_max);
    return finish_output(&g, tm.tiles, 2);
}

/* ------------------------------------------------------------------ T3 */
SR_MAYBE_UNUSED static int test3(void)
{
    sr_geom_t g;
    xil_printf("T3: timing, %d frames of the image at 0x%08x\r\n", SR_T3_FRAMES, (unsigned)SR_IN_ADDR);
    int rc = read_input_header(&g);
    if (rc) { write_marker((uint32_t)rc, 0, 0, 0, 3); return rc; }
    write_output_header(&g);
    uint32_t tot_min = 0xFFFFFFFFu, tot_max = 0, run_min = 0xFFFFFFFFu, run_max = 0;
    uint64_t tot_sum = 0, pad_sum = 0, copy_sum = 0, run_sum = 0, cyc_sum = 0;
    uint32_t cyc_min = 0xFFFFFFFFu, cyc_max = 0, cyc_n = 0, fnv0 = 0, tiles = 0;
    int same = 1;
    for (int f = 0; f < SR_T3_FRAMES; f++) {
        tile_ctx_t tc = { &dev, 0, 0, 0, 0 };
        sr_timing_t tm; uint64_t tp, tt;
        rc = process_frame(&g, &tc, &tp, &tm, &tt);
        if (rc) { xil_printf("T3 FAIL: frame %d, tile %u returned %d\r\n", f, tm.tiles, rc); write_marker((uint32_t)rc, 0, 0, tm.tiles, 3); return rc; }
        const uint32_t us_tot = ticks_to_us(tt), us_pad = ticks_to_us(tp), us_copy = ticks_to_us(tm.t_cut + tm.t_place), us_run = ticks_to_us(tm.t_run);
        xil_printf("  frame %d: total %u us = pad %u + ARM tile copy %u + DMA/compute wait %u (+ loop overhead %d)\r\n", f, us_tot, us_pad, us_copy, us_run,
                   (int)us_tot - (int)(us_pad + us_copy + us_run));
        tot_sum += us_tot; pad_sum += us_pad; copy_sum += us_copy; run_sum += us_run;
        if (us_tot < tot_min) tot_min = us_tot;
        if (us_tot > tot_max) tot_max = us_tot;
        if (us_run < run_min) run_min = us_run;
        if (us_run > run_max) run_max = us_run;
        if (tc.cyc_min < cyc_min) cyc_min = tc.cyc_min;
        if (tc.cyc_max > cyc_max) cyc_max = tc.cyc_max;
        cyc_sum += tc.cyc_sum; cyc_n += tc.n; tiles = tm.tiles;
        Xil_DCacheFlushRange((UINTPTR)SR_OUT_ADDR, 16u + (uint32_t)sr_out_bytes(&g));
        const uint32_t fnv = sr_fnv1a32((const uint8_t *)(SR_OUT_ADDR + 16), sr_out_bytes(&g));
        if (f == 0) fnv0 = fnv; else if (fnv != fnv0) same = 0;
    }
    const uint32_t mean_us = (uint32_t)(tot_sum / SR_T3_FRAMES);
    xil_printf("T3: per frame mean %u us (%u ms), min %u us, max %u us; mean split: pad %u us, ARM copy %u us, DMA+compute %u us\r\n", mean_us, mean_us / 1000u,
               tot_min, tot_max, (uint32_t)(pad_sum / SR_T3_FRAMES), (uint32_t)(copy_sum / SR_T3_FRAMES), (uint32_t)(run_sum / SR_T3_FRAMES));
    xil_printf("T3: DMA+compute per frame min/max %u/%u us; frames per second x1000 (mean): %u\r\n", run_min, run_max, mean_us ? (uint32_t)(1000000000ull / mean_us) : 0u);
    xil_printf("T3: CYCLES per tile min %u, max %u, mean %u (%u tiles x %d frames); all frames gave the same output: %s\r\n", cyc_min, cyc_max,
               cyc_n ? (uint32_t)(cyc_sum / cyc_n) : 0u, tiles, SR_T3_FRAMES, same ? "yes" : "NO");
    if (!same) { xil_printf("T3 FAIL: outputs differ between frames\r\n"); write_marker(100, 0, 0, tiles, 3); return -1; }
    return finish_output(&g, tiles, 3);
}

/* ------------------------------------------------------------------ main */
int main(void)
{
    xil_printf("\r\n--- SR accelerator test (SR_BASE 0x%08x, DMA 0x%08x) ---\r\n", (unsigned)SR_BASE, (unsigned)SR_DMA_BASE);
    if (check_memory_map() != 0) return 1;
    int rc = sr_init(&dev);
    if (rc != SR_RC_OK) { xil_printf("sr_init failed: %d\r\n", rc); write_marker((uint32_t)rc, 0, 0, 0, 0); return rc; }
    xil_printf("init ok: VERSION 0x%08x, TILE_SIZE %u\r\n", sr_reg_read(&dev, SR_REG_VERSION), sr_reg_read(&dev, SR_REG_TILE_SIZE));
#if SR_TEST == 1
    rc = test1();
#elif SR_TEST == 2
    rc = test2();
#elif SR_TEST == 3
    rc = test3();
#else
    for (;;) {
        xil_printf("\r\nMenu: 1 = golden tile, 2 = full image, 3 = timing  > ");
        const char c = inbyte();
        xil_printf("%c\r\n", c);
        if (c == '1') rc = test1();
        else if (c == '2') rc = test2();
        else if (c == '3') rc = test3();
        else xil_printf("?\r\n");
    }
#endif
    xil_printf("done, result %d\r\n", rc);
    for (;;) { }
    return rc;
}
