/* Super-resolution accelerator test program (bare metal, ZedBoard), whole-frame PIPELINE version (branch `pipe`, VERSION 0x53525301; NOT run on a board).
 * Differences to the tiled program: T2/T3 pad the frame to (W+6) x (H+6) and send it with ONE DMA transfer each way (no tile loop, no ARM tile copy; the
 * output lands directly in the output image); CYCLES is per frame.  T1/T5/T6 use the golden tile as a 64 x 64 frame.  T7 (ARM only) keeps the tile loop.
 *
 * Select the test at build time (-DSR_TEST=n) or leave SR_TEST = 0 for a menu over the UART (115200 baud, /dev/ttyACM0):
 *   T1 golden tile   : the real0 tile from golden_tile.h goes through DMA + core; all 49,152 output bytes are compared; CYCLES is printed; then the same tile
 *                      is run 20 times and every result must be identical (and equal to the golden output).
 *   T2 full image    : the SRIM image at SR_IN_ADDR (put there by the host with xsdb, see run_board.tcl) is padded, cut into tiles, every tile is run on the
 *                      core, the result is written as SRIM to SR_OUT_ADDR.  Then the ready marker is written at SR_MARK_ADDR and printed.
 *   T3 timing        : like T2, SR_T3_FRAMES times; per frame the time is split into padding / ARM tile copies (cut + place) / DMA + compute wait,
 *                      then mean / min / max per frame and CYCLES per tile.
 *   T7 ARM only      : (SR_TEST=11) like T3, but every tile is computed by the Cortex-A9 in C (sr_swmodel.c, integer model) instead of the FPGA; the
 *                      accelerator is not initialised.  SR_T7_FRAMES frames (default 1).  Baseline for "same chip with / without the accelerator".
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
#if SR_TEST == 11
#include "sr_swmodel.h"      /* needs sr_weights.h, generated: software/host_tools/weights_h.py */
#endif

#ifndef SR_TEST
#define SR_TEST 0             /* 0 = UART menu; 1, 2, 3, 5, 10 (T6) = run that test and stop; 6-9 = stale-state programs for stale_test.sh (never finish) */
#endif
#ifndef SR_T7_FRAMES
#define SR_T7_FRAMES 1
#endif
#ifndef SR_T3_FRAMES
#define SR_T3_FRAMES 5
#endif
#ifndef SR_T1_SIM_CYCLES
#define SR_T1_SIM_CYCLES 74641u   /* CYCLES of the golden tile as a 64 x 64 frame in tb_sr_pipe_top.v (+F0=gtile, no stalls), 2026-10-26 */
#endif

#define SR_MAYBE_UNUSED __attribute__((unused))   /* a build with -DSR_TEST=n uses only one of the three tests */
char inbyte(void);            /* from the BSP (blocking UART read) */
extern char _stack __attribute__((weak)); /* top of the stack = highest address of the program image in lscript.ld (this script has no _end symbol) */

#define TICKS_PER_SEC sr_ticks_per_sec()
static uint32_t ticks_to_us(uint64_t t) { return (uint32_t)((t * 1000000ull) / TICKS_PER_SEC); }
static uint64_t now_ticks(void) { return sr_now_ticks(); }

static sr_dev_t dev;

#ifdef SR_TIMING_SPLIT
/* prints and clears the driver's summed split (sr_driver.h); only in -DSR_TIMING_SPLIT builds */
static void print_split(const char *tag)
{
    xil_printf("%s split over %u call(s), us: busy+regs %u, flush in %u, flush out %u, DMA set-up+START %u, wait %u, check+invalidate+CYCLES %u, sum %u\r\n", tag, sr_split_calls,
               ticks_to_us(sr_split_sum[0]), ticks_to_us(sr_split_sum[1]), ticks_to_us(sr_split_sum[2]), ticks_to_us(sr_split_sum[3]), ticks_to_us(sr_split_sum[4]),
               ticks_to_us(sr_split_sum[5]), ticks_to_us(sr_split_sum[6]));
    for (int k = 0; k < SR_SPLIT_N; k++) sr_split_sum[k] = 0;
    sr_split_calls = 0;
}
#endif

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

static void write_marker(uint32_t result, uint32_t bytes, uint32_t fnv, uint32_t tiles, uint32_t test);
static uint32_t g_stats[SR_MARK_NSTATS];

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
    xil_printf("T1: CYCLES = %u (expected %u in simulation), tile time %u us (DMA + compute)\r\n", dev.last_cycles, (unsigned)SR_T1_SIM_CYCLES, ticks_to_us(t1 - t0));
    if (bad) {
        xil_printf("T1 FAIL: %d of %u bytes differ from the golden output\r\n", bad, (unsigned)SR_TILE_OUT_BYTES);
        g_stats[20] = (uint32_t)bad; g_stats[0] = dev.last_cycles;
        sr_dump(&dev, "T1 first tile: output wrong although no error was reported");   /* records STATUS / DMA / debug registers for the marker */
        write_marker(100, 0, 0, 1, 1);
        return -1;
    }
    xil_printf("T1: first run: all %u bytes identical to the golden output\r\n", (unsigned)SR_TILE_OUT_BYTES);
    memcpy(first, out, SR_TILE_OUT_BYTES);

    int identical = 0;
    uint32_t cmin = dev.last_cycles, cmax = dev.last_cycles;
    uint64_t csum = dev.last_cycles, tmin = t1 - t0, tmax = t1 - t0, tsum = t1 - t0;
    for (int run = 1; run <= 20; run++) {
        memset(out, 0xA5, SR_TILE_OUT_BYTES);
        const uint64_t r0 = now_ticks();
        rc = sr_run_tile(&dev, sr_golden_in, out);
        const uint64_t r1 = now_ticks();
        if (rc != SR_RC_OK) { xil_printf("T1 FAIL: run %d returned %d\r\n", run, rc); return rc; }
        if (compare_tile(out, first, SR_TILE_OUT_BYTES, "repeat") == 0) identical++;
        const uint32_t c = dev.last_cycles;
        if (c < cmin) cmin = c;
        if (c > cmax) cmax = c;
        csum += c;
        if (r1 - r0 < tmin) tmin = r1 - r0;
        if (r1 - r0 > tmax) tmax = r1 - r0;
        tsum += r1 - r0;
    }
    xil_printf("T1: %d of 20 repeated runs identical to the first\r\n", identical);
    xil_printf("T1: CYCLES over 21 runs: min %u, max %u, mean %u (simulation: %u)\r\n", cmin, cmax, (uint32_t)(csum / 21u), (unsigned)SR_T1_SIM_CYCLES);
    xil_printf("T1: tile time over 21 runs (DMA + compute + cache ops): min %u us, max %u us, mean %u us\r\n",
               ticks_to_us(tmin), ticks_to_us(tmax), ticks_to_us(tsum / 21u));
    g_stats[0] = cmin; g_stats[1] = cmax; g_stats[2] = (uint32_t)(csum / 21u);
    g_stats[3] = ticks_to_us(tmin); g_stats[4] = ticks_to_us(tmax); g_stats[5] = ticks_to_us(tsum / 21u); g_stats[6] = (uint32_t)identical;
    if (identical != 20) { xil_printf("T1 FAIL\r\n"); write_marker(100, 0, 0, 1, 1); return -1; }
    xil_printf("T1 PASS\r\n");
    write_marker(0, 0, 0, 1, 1);
    return 0;
}

/* ------------------------------------------------------------------ T2 / T3 helpers */
static int image_fits(uint32_t w, uint32_t h, sr_geom_t *g)
{
    if (w == 0 || h == 0 || w > 8192 || h > 8192) return 0;
#if SR_TEST != 11
    if (w > SR_MAX_W || h > SR_MAX_H) return 0;                   /* the pipeline's line buffers (MAX_W register) and row counters (SR_MAX_H) */
#endif
    sr_geom(w, h, g);                                             /* tiled geometry (T7); the pipeline's padded frame is smaller in both directions */
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

/* g_stats: result numbers for the host (xsdb reads them from DDR, the UART may be busy) at SR_MARK_W_STATS + i; meaning per test: software/board/README.md */

static int g_marker_written;
static void write_marker(uint32_t result, uint32_t bytes, uint32_t fnv, uint32_t tiles, uint32_t test)
{
    g_marker_written = 1;
    volatile uint32_t *m = (volatile uint32_t *)SR_MARK_ADDR;
    m[SR_MARK_W_MAGIC] = 0;
    m[SR_MARK_W_RESULT] = result; m[SR_MARK_W_BYTES] = bytes; m[SR_MARK_W_FNV] = fnv; m[SR_MARK_W_TILES] = tiles; m[SR_MARK_W_TEST] = test;
    for (int i = 0; i < SR_MARK_NSTATS; i++) m[SR_MARK_W_STATS + i] = g_stats[i];
    for (int i = 0; i < 6; i++) m[SR_MARK_W_STATS + 24 + i] = sr_dbg[i];   /* first register dump at stat24..29 (all 0 = no dump) */
    for (int i = 0; i < 7; i++) m[SR_MARK_W_STATS + 32 + i] = sr_dbg[6 + i]; /* and its debug registers at stat32..38 (VERSION 0x53520602 only) */
    Xil_DCacheFlushRange((UINTPTR)SR_MARK_ADDR, SR_MARK_SIZE);
    m[SR_MARK_W_MAGIC] = SR_MARK_MAGIC;                          /* last: the host polls this word */
    Xil_DCacheFlushRange((UINTPTR)SR_MARK_ADDR, SR_MARK_SIZE);
}

/* one frame; fills the timing split.  Returns 0 or an error code.
 * fn == NULL: the pipeline (pad to (W+6) x (H+6), one sr_run_frame: DMA in, compute, DMA out directly into the output image; tm->t_run = that wait, cut/place 0).
 * fn != NULL: the tile loop with fn as the tile runner (T7, ARM only). */
static int process_frame(const sr_geom_t *g, sr_tile_fn fn, void *ctx, uint64_t *t_pad, sr_timing_t *tm, uint64_t *t_total)
{
    const uint8_t *lr = (const uint8_t *)(SR_IN_ADDR + 16);
    uint8_t *padded = (uint8_t *)SR_PAD_ADDR;
    uint8_t *out = (uint8_t *)(SR_OUT_ADDR + 16);
    int rc;
    const uint64_t t0 = now_ticks();
    uint64_t t1, t2;
    if (fn == NULL) {
        sr_geom_t gf;
        sr_geom_frame(g->w, g->h, &gf);
        sr_pad_image(lr, &gf, padded);
        t1 = now_ticks();
        rc = sr_run_frame(&dev, padded, out, g->w, g->h);
        t2 = now_ticks();
        tm->t_cut = 0; tm->t_place = 0; tm->t_run = t2 - t1; tm->tiles = rc ? 0u : 1u;
        (void)ctx;
    } else {
        sr_pad_image(lr, g, padded);
        t1 = now_ticks();
        rc = sr_upscale_padded(padded, g, out, (uint8_t *)SR_TILE_IN_ADDR, (uint8_t *)SR_TILE_OUT_ADDR, fn, ctx, now_ticks, tm);
        t2 = now_ticks();
    }
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
    write_marker(0, 0, 0, 0, 0); ((volatile uint32_t *)SR_MARK_ADDR)[SR_MARK_W_MAGIC] = 0; Xil_DCacheFlushRange((UINTPTR)SR_MARK_ADDR, SR_MARK_SIZE); g_marker_written = 0;   /* clear the marker */
    int rc = read_input_header(&g);
    if (rc) { write_marker((uint32_t)rc, 0, 0, 0, 2); return rc; }
    xil_printf("T2: %ux%u -> %ux%u, one frame (pipeline)\r\n", g.w, g.h, 2 * g.w, 2 * g.h);
    sr_timing_t tm; uint64_t tp, tt;
    write_output_header(&g);
    rc = process_frame(&g, NULL, NULL, &tp, &tm, &tt);
    if (rc) { xil_printf("T2 FAIL: frame returned %d\r\n", rc); write_marker((uint32_t)rc, 0, 0, 0, 2); return rc; }
    xil_printf("T2: frame done in %u ms (pad %u us, DMA + compute %u us), CYCLES %u\r\n", ticks_to_us(tt) / 1000u, ticks_to_us(tp), ticks_to_us(tm.t_run), dev.last_cycles);
#ifdef SR_TIMING_SPLIT
    print_split("T2");
#endif
    g_stats[0] = ticks_to_us(tt); g_stats[1] = ticks_to_us(tp); g_stats[2] = 0u; g_stats[3] = ticks_to_us(tm.t_run);
    g_stats[4] = dev.last_cycles; g_stats[5] = dev.last_cycles; g_stats[6] = dev.last_cycles;   /* frame CYCLES (min = max = mean: one frame) */
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
        sr_timing_t tm; uint64_t tp, tt;
        rc = process_frame(&g, NULL, NULL, &tp, &tm, &tt);
        if (rc) { xil_printf("T3 FAIL: frame %d returned %d\r\n", f, rc); write_marker((uint32_t)rc, 0, 0, 0, 3); return rc; }
        const uint32_t cy = dev.last_cycles;
        const uint32_t us_tot = ticks_to_us(tt), us_pad = ticks_to_us(tp), us_copy = ticks_to_us(tm.t_cut + tm.t_place), us_run = ticks_to_us(tm.t_run);
        xil_printf("  frame %d: total %u us = pad %u + ARM tile copy %u + DMA/compute wait %u (+ loop overhead %d)\r\n", f, us_tot, us_pad, us_copy, us_run,
                   (int)us_tot - (int)(us_pad + us_copy + us_run));
#ifdef SR_TIMING_SPLIT
        print_split("  frame");
#endif
        tot_sum += us_tot; pad_sum += us_pad; copy_sum += us_copy; run_sum += us_run;
        if (us_tot < tot_min) tot_min = us_tot;
        if (us_tot > tot_max) tot_max = us_tot;
        if (us_run < run_min) run_min = us_run;
        if (us_run > run_max) run_max = us_run;
        if (cy < cyc_min) cyc_min = cy;
        if (cy > cyc_max) cyc_max = cy;
        cyc_sum += cy; cyc_n++; tiles = tm.tiles;
        Xil_DCacheFlushRange((UINTPTR)SR_OUT_ADDR, 16u + (uint32_t)sr_out_bytes(&g));
        const uint32_t fnv = sr_fnv1a32((const uint8_t *)(SR_OUT_ADDR + 16), sr_out_bytes(&g));
        if (f == 0) fnv0 = fnv; else if (fnv != fnv0) same = 0;
    }
    const uint32_t mean_us = (uint32_t)(tot_sum / SR_T3_FRAMES);
    xil_printf("T3: per frame mean %u us (%u ms), min %u us, max %u us; mean split: pad %u us, ARM copy %u us, DMA+compute %u us\r\n", mean_us, mean_us / 1000u,
               tot_min, tot_max, (uint32_t)(pad_sum / SR_T3_FRAMES), (uint32_t)(copy_sum / SR_T3_FRAMES), (uint32_t)(run_sum / SR_T3_FRAMES));
    xil_printf("T3: DMA+compute per frame min/max %u/%u us; frames per second x1000 (mean): %u\r\n", run_min, run_max, mean_us ? (uint32_t)(1000000000ull / mean_us) : 0u);
    xil_printf("T3: CYCLES per frame min %u, max %u, mean %u (%u frame x %d frames); all frames gave the same output: %s\r\n", cyc_min, cyc_max,
               cyc_n ? (uint32_t)(cyc_sum / cyc_n) : 0u, tiles, SR_T3_FRAMES, same ? "yes" : "NO");
    if (!same) { xil_printf("T3 FAIL: outputs differ between frames\r\n"); write_marker(100, 0, 0, tiles, 3); return -1; }
    g_stats[0] = SR_T3_FRAMES; g_stats[1] = mean_us; g_stats[2] = tot_min; g_stats[3] = tot_max;
    g_stats[4] = (uint32_t)(pad_sum / SR_T3_FRAMES); g_stats[5] = (uint32_t)(copy_sum / SR_T3_FRAMES); g_stats[6] = (uint32_t)(run_sum / SR_T3_FRAMES);
    g_stats[7] = run_min; g_stats[8] = run_max; g_stats[9] = cyc_min; g_stats[10] = cyc_max; g_stats[11] = cyc_n ? (uint32_t)(cyc_sum / cyc_n) : 0u;
    return finish_output(&g, tiles, 3);
}

/* ------------------------------------------------------------------ T5: error recovery (SR_TEST=5)
 * Each bad tile must fail with an error code, the driver's reset after it must work, and the NEXT normal tile must be byte-exact again.
 * stats: [0] number of cases, then per case i: [1+3i] rc of the bad tile, [2+3i] sr_last_recover, [3+3i] 1 if the following good tile was byte-exact */
SR_MAYBE_UNUSED static int test5(void)
{
    static uint8_t out[SR_TILE_OUT_BYTES] __attribute__((aligned(64)));
    static const struct { uint32_t in_len, out_len; const char *what; } bad[] = {
        { 4000u,  SR_TILE_OUT_BYTES, "input too short (TLAST early)" },
        { 16000u, SR_TILE_OUT_BYTES, "input too long (no TLAST on the last word)" },
        { SR_TILE_IN_BYTES, 20000u,  "S2MM buffer too short (core stuck in output)" },
        { 4000u,  20000u,            "both wrong" },
    };
    const int n = (int)(sizeof bad / sizeof bad[0]);
    int fails = 0;
    memset(out, 0xA5, SR_TILE_OUT_BYTES);
    int rc = sr_run_tile(&dev, sr_golden_in, out);
    if (rc != SR_RC_OK || memcmp(out, sr_golden_out, SR_TILE_OUT_BYTES) != 0) {
        uint32_t nd = 0, first = 0xFFFFFFFFu;
        for (uint32_t k = 0; k < SR_TILE_OUT_BYTES; k++) if (out[k] != sr_golden_out[k]) { nd++; if (first == 0xFFFFFFFFu) first = k; }
        g_stats[20] = (uint32_t)rc; g_stats[21] = nd; g_stats[22] = first; g_stats[23] = (uint32_t)(uintptr_t)out;
        xil_printf("T5 FAIL: first good tile (rc %d, %u bytes differ)\r\n", rc, nd); write_marker(100, 0, 0, 0, 5); return -1;
    }
    g_stats[0] = (uint32_t)n;
    for (int i = 0; i < n; i++) {
#ifdef SR_T5_ONLY
        if (i != SR_T5_ONLY) continue;                             /* debug builds: run only one of the bad cases */
#endif
        sr_last_recover = -1;
        const int rb = sr_run_tile_len(&dev, sr_golden_in, out, bad[i].in_len, bad[i].out_len);
        const int rr = sr_last_recover;
        memset(out, 0xA5, SR_TILE_OUT_BYTES);
        const int rg = sr_run_tile(&dev, sr_golden_in, out);
        const int good = (rg == SR_RC_OK) && memcmp(out, sr_golden_out, SR_TILE_OUT_BYTES) == 0;
        xil_printf("T5 case %d (%s): bad tile rc %d, reset after it rc %d, next good tile %s\r\n", i, bad[i].what, rb, rr, good ? "byte-exact" : "WRONG");
        g_stats[1 + 3 * i] = (uint32_t)rb; g_stats[2 + 3 * i] = (uint32_t)rr; g_stats[3 + 3 * i] = (uint32_t)good;
        if (rb == SR_RC_OK || rr != SR_RC_OK || !good) fails++;
    }
    xil_printf(fails ? "T5 FAIL\r\n" : "T5 PASS\r\n");
    write_marker(fails ? 100u : 0u, 0, 0, (uint32_t)n, 5);
    return fails ? -1 : 0;
}

/* ------------------------------------------------------------------ T6: "first tile of a fresh run", many times (SR_TEST=6 is taken: this is SR_TEST=10)
 * Per iteration: full init reset (sr_reset_all: core soft reset, DMA reset, core soft reset, STATUS idle + ERROR_CODE 0), then one golden tile, compared.
 * Iterations alternate between the two driver orders, so both see the same board conditions:  order 0 = arm S2MM, arm MM2S, START (normal);
 * order 1 = arm S2MM, START, arm MM2S.  EVERY failure is counted, nothing is retried.
 * stats: [0] iterations per order, then per order o at 1 + 10*o: [+0] byte-exact, [+1] rc OK but output wrong, [+2] rc 7 (core error), [+3] rc 6 (timeout),
 *        [+4] other rc, [+5] ERROR_CODE 1, [+6] ERROR_CODE 2, [+7] ERROR_CODE 3, [+8] reset (sr_reset_all) failed, [+9] index of the first failing iteration + 1 (0 = none) */
#ifndef SR_T6_ITERS
#define SR_T6_ITERS 1000
#endif
SR_MAYBE_UNUSED static int test6(void)
{
    static uint8_t out[SR_TILE_OUT_BYTES] __attribute__((aligned(64)));
    uint32_t *st = g_stats;
    st[0] = SR_T6_ITERS;
    for (int i = 0; i < 2 * SR_T6_ITERS; i++) {
        const int o = i & 1;
        uint32_t *c = &st[1 + 10 * o];
        sr_start_order = o;
        if (sr_reset_all(&dev) != SR_RC_OK) { c[8]++; if (!c[9]) c[9] = (uint32_t)(i / 2 + 1); continue; }
        memset(out, 0xA5, SR_TILE_OUT_BYTES);
        dev.last_error_code = 0;
        const int rc = sr_run_tile(&dev, sr_golden_in, out);
        int fail = 1;
        if (rc == SR_RC_OK) { if (memcmp(out, sr_golden_out, SR_TILE_OUT_BYTES) == 0) { c[0]++; fail = 0; } else c[1]++; }
        else if (rc == SR_RC_HW_ERROR) { c[2]++; if (dev.last_error_code >= 1 && dev.last_error_code <= 3) c[4 + dev.last_error_code]++; }
        else if (rc == SR_RC_TIMEOUT) c[3]++;
        else c[4]++;
        if (fail && !c[9]) c[9] = (uint32_t)(i / 2 + 1);
    }
    sr_start_order = 0;
    for (int o = 0; o < 2; o++) {
        const uint32_t *c = &st[1 + 10 * o];
        xil_printf("T6 order %d: %u of %u byte-exact; wrong data %u, core error %u (ERROR_CODE 1/2/3: %u/%u/%u), timeout %u, other %u, reset failed %u\r\n",
                   o, c[0], (unsigned)SR_T6_ITERS, c[1], c[2], c[5], c[6], c[7], c[3], c[4], c[8]);
    }
    const int ok = (st[1] == SR_T6_ITERS) && (st[11] == SR_T6_ITERS);
    xil_printf(ok ? "T6 PASS\r\n" : "T6 FAIL\r\n");
    write_marker(ok ? 0u : 100u, 0, 0, 2u * SR_T6_ITERS, 10);
    return ok ? 0 : -1;
}

/* ------------------------------------------------------------------ T7: ARM-only baseline (SR_TEST=11)
 * stats: [0] frames, [1] mean us per frame, [2] min, [3] max, [4] mean pad us, [5] mean ARM tile copy us, [6] mean ARM compute us */
#if SR_TEST == 11
static int test7(void)
{
    sr_geom_t g;
    sr_timer_init();   /* T7 never calls sr_init(), which is where the A9 global timer is enabled: without this every T7 time read 0 (2026-10-27) */
    xil_printf("T7: ARM-only baseline (no FPGA), %d frame(s) of the image at 0x%08x\r\n", SR_T7_FRAMES, (unsigned)SR_IN_ADDR);
    int rc = read_input_header(&g);
    if (rc) { write_marker((uint32_t)rc, 0, 0, 0, 11); return rc; }
    write_output_header(&g);
    uint32_t tot_min = 0xFFFFFFFFu, tot_max = 0, fnv0 = 0, tiles = 0;
    uint64_t tot_sum = 0, pad_sum = 0, copy_sum = 0, run_sum = 0;
    int same = 1;
    for (int f = 0; f < SR_T7_FRAMES; f++) {
        sr_timing_t tm; uint64_t tp, tt;
        rc = process_frame(&g, sr_sw_run_tile, NULL, &tp, &tm, &tt);
        if (rc) { write_marker((uint32_t)rc, 0, 0, tm.tiles, 11); return rc; }
        const uint32_t us_tot = ticks_to_us(tt);
        xil_printf("  frame %d: total %u us = pad %u + ARM tile copy %u + ARM compute %u\r\n", f, us_tot, ticks_to_us(tp),
                   ticks_to_us(tm.t_cut + tm.t_place), ticks_to_us(tm.t_run));
        tot_sum += us_tot; pad_sum += ticks_to_us(tp); copy_sum += ticks_to_us(tm.t_cut + tm.t_place); run_sum += ticks_to_us(tm.t_run);
        if (us_tot < tot_min) tot_min = us_tot;
        if (us_tot > tot_max) tot_max = us_tot;
        tiles = tm.tiles;
        const uint32_t fnv = sr_fnv1a32((const uint8_t *)(SR_OUT_ADDR + 16), sr_out_bytes(&g));
        if (f == 0) fnv0 = fnv; else if (fnv != fnv0) same = 0;
    }
    if (!same) { xil_printf("T7 FAIL: outputs differ between frames\r\n"); write_marker(100, 0, 0, tiles, 11); return -1; }
    g_stats[0] = SR_T7_FRAMES; g_stats[1] = (uint32_t)(tot_sum / SR_T7_FRAMES); g_stats[2] = tot_min; g_stats[3] = tot_max;
    g_stats[4] = (uint32_t)(pad_sum / SR_T7_FRAMES); g_stats[5] = (uint32_t)(copy_sum / SR_T7_FRAMES); g_stats[6] = (uint32_t)(run_sum / SR_T7_FRAMES);
    xil_printf("T7: per frame mean %u us, min %u, max %u\r\n", g_stats[1], tot_min, tot_max);
    return finish_output(&g, tiles, 11);
}
#endif

/* ------------------------------------------------------------------ main */
int main(void)
{
#ifdef SR_NOCACHE
    Xil_DCacheDisable();                                          /* debug builds only: run with the data caches off */
#endif
    xil_printf("\r\n--- SR accelerator test (SR_BASE 0x%08x, DMA 0x%08x) ---\r\n", (unsigned)SR_BASE, (unsigned)SR_DMA_BASE);
    if (check_memory_map() != 0) return 1;
#if SR_TEST == 11
    int rc = test7();                                             /* ARM only: the accelerator is not touched */
#else
    int rc = sr_init(&dev);
    if (rc != SR_RC_OK) { xil_printf("sr_init failed: %d\r\n", rc); write_marker((uint32_t)rc, 0, 0, 0, 0); return rc; }
    xil_printf("init ok: VERSION 0x%08x, MAX_W %u\r\n", sr_reg_read(&dev, SR_REG_VERSION), sr_reg_read(&dev, SR_REG_MAX_W));
#if SR_TEST >= 6 && SR_TEST <= 9
    /* stale-state programs for software/board/stale_test.sh: leave the DMA / core in a half-finished state, then spin (they never finish).
     *   9 = MM2S started with the full tile, core NOT started: the DMA stays blocked in the middle of its transfer
     *   7 = MM2S with only 4,000 of 14,700 bytes, then START: the core is stuck in the middle of its LOAD phase
     *   6 = MM2S full, START, S2MM armed for only 20,000 of 49,152 bytes: the core is stuck in the middle of its OUTPUT phase
     *   8 = everything started normally, not waited for (the tile completes by itself) */
    Xil_DCacheFlushRange((UINTPTR)sr_golden_in, SR_TILE_IN_BYTES);
    Xil_DCacheFlushRange((UINTPTR)SR_TILE_OUT_ADDR, SR_TILE_OUT_BYTES);
    if (SR_TEST == 8) XAxiDma_SimpleTransfer(&dev.dma, (UINTPTR)SR_TILE_OUT_ADDR, SR_TILE_OUT_BYTES, XAXIDMA_DEVICE_TO_DMA);
    if (SR_TEST == 6) XAxiDma_SimpleTransfer(&dev.dma, (UINTPTR)SR_TILE_OUT_ADDR, 20000u, XAXIDMA_DEVICE_TO_DMA);
    XAxiDma_SimpleTransfer(&dev.dma, (UINTPTR)sr_golden_in, SR_TEST == 7 ? 4000u : SR_TILE_IN_BYTES, XAXIDMA_DMA_TO_DEVICE);
    Xil_Out32(SR_BASE + SR_REG_FRAME_W, SR_HC); Xil_Out32(SR_BASE + SR_REG_FRAME_H, SR_HC);   /* the golden tile = a 64 x 64 frame */
    if (SR_TEST != 9) Xil_Out32(SR_BASE + SR_REG_CONTROL, SR_CTRL_START);
    xil_printf("stale-state program %d: transfers started, not waiting\r\n", SR_TEST);
    for (;;) { }
#elif SR_TEST == 5
    rc = test5();
#elif SR_TEST == 10
    rc = test6();
#elif SR_TEST == 1
    rc = test1();
#elif SR_TEST == 2
    rc = test2();
#elif SR_TEST == 3
    rc = test3();
#else
    for (;;) {
        xil_printf("\r\nMenu: 1 = golden tile, 2 = full image, 3 = timing, 5 = error recovery  > ");
        const char c = inbyte();
        xil_printf("%c\r\n", c);
        if (c == '1') rc = test1();
        else if (c == '2') rc = test2();
        else if (c == '3') rc = test3();
        else if (c == '5') rc = test5();
        else xil_printf("?\r\n");
    }
#endif
#endif   /* SR_TEST == 11 */
    if (!g_marker_written) write_marker(rc ? (uint32_t)(rc < 0 ? 100 : rc) : 0u, 0, 0, 0, SR_TEST);   /* every exit path tells the host */
    xil_printf("done, result %d\r\n", rc);
    for (;;) { }
    return rc;
}
