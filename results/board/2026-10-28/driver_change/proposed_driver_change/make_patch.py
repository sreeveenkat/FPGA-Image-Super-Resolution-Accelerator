#!/usr/bin/env python3
"""Apply the proposed driver change to a COPY of software/board (never to a repo tree): make_patch.py <copy-of-software-board-dir> <tiled|pipe>"""
import sys
from pathlib import Path
root = Path(sys.argv[1]); kind = sys.argv[2]
app = root / "sr_app"

def edit(path, pairs):
    s = path.read_text()
    for a, b in pairs:
        assert s.count(a) == 1, (path.name, s.count(a), a[:70])
        s = s.replace(a, b)
    path.write_text(s)

# ---------------------------------------------------------------- sr_driver.h
edit(app / "sr_driver.h", [(
"/* Base address of sr_accel_top/s_axi:",
"""/* Optional split of the time inside one sr_run_tile / sr_run_frame call.  Built ONLY with -DSR_TIMING_SPLIT (software/board/build_elf.sh <N> -DSR_TIMING_SPLIT with
 * SR_ELF_SUFFIX=_split); without the flag every SR_TS* macro in sr_driver.c is empty, so the production code is the same source as before.
 * sr_split[]: global-timer ticks of the LAST call: 0 busy check + register writes, 1 flush input, 2 flush output, 3 arm S2MM + MM2S + START, 4 wait loop (core compute
 * + whatever the DMA and polling add), 5 status/error checks + invalidate output + CYCLES read, 6 sum of 0..5.  sr_split_sum[] / sr_split_calls: the same, summed over calls. */
#ifdef SR_TIMING_SPLIT
#define SR_SPLIT_N 7
extern uint64_t sr_split[SR_SPLIT_N];
extern uint64_t sr_split_sum[SR_SPLIT_N];
extern uint32_t sr_split_calls;
#endif

/* Base address of sr_accel_top/s_axi:""")])

# ---------------------------------------------------------------- sr_driver.c
ver_block = """    const uint32_t ver = reg_rd(d, SR_REG_VERSION);
    d->version = ver;
    if ((ver & SR_VERSION_MASK) != (SR_VERSION & SR_VERSION_MASK)) {
        xil_printf("SR: VERSION 0x%08x, expected 0x%08x (wrong SR_BASE 0x%08x or wrong bitstream)\\r\\n", ver, (unsigned)SR_VERSION, (unsigned)SR_BASE);
        return SR_RC_VERSION;
    }
"""
new_ver_block = """    /* VERSION first: a program built for another bitstream must stop here, before anything is written to the DMA (XAxiDma_CfgInitialize resets it) or to the core. */
""" + ver_block + "\n"
if kind == "tiled":
    run_pairs = [
 ("    int rc;\n    if (reg_rd(d, SR_REG_STATUS) & SR_STATUS_BUSY) { sr_dump(d, \"core busy before start\"); recover(d); return SR_RC_BUSY; }\n",
  "    int rc;\n    SR_TS_BEGIN();\n    if (reg_rd(d, SR_REG_STATUS) & SR_STATUS_BUSY) { sr_dump(d, \"core busy before start\"); recover(d); return SR_RC_BUSY; }\n    SR_TS(0);\n"),
 ("    Xil_DCacheFlushRange((UINTPTR)in, SR_TILE_IN_BYTES);\n    Xil_DCacheFlushRange((UINTPTR)out, SR_TILE_OUT_BYTES);\n",
  "    Xil_DCacheFlushRange((UINTPTR)in, SR_TILE_IN_BYTES);\n    SR_TS(1);\n    Xil_DCacheFlushRange((UINTPTR)out, SR_TILE_OUT_BYTES);\n    SR_TS(2);\n"),
    ]
else:
    run_pairs = [
 ("    reg_wr(d, SR_REG_FRAME_W, w);\n    reg_wr(d, SR_REG_FRAME_H, h);\n",
  "    SR_TS_BEGIN();\n    reg_wr(d, SR_REG_FRAME_W, w);\n    reg_wr(d, SR_REG_FRAME_H, h);\n    SR_TS(0);\n"),
 ("    Xil_DCacheFlushRange((UINTPTR)in, in_bytes > in_len ? in_bytes : in_len);\n    Xil_DCacheFlushRange((UINTPTR)out, out_bytes);\n",
  "    Xil_DCacheFlushRange((UINTPTR)in, in_bytes > in_len ? in_bytes : in_len);\n    SR_TS(1);\n    Xil_DCacheFlushRange((UINTPTR)out, out_bytes);\n    SR_TS(2);\n"),
    ]
macros = """
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
"""
edit(app / "sr_driver.c", [
 ("uint64_t sr_ticks_per_sec(void) { return SR_TICKS_PER_SEC; }\n", "uint64_t sr_ticks_per_sec(void) { return SR_TICKS_PER_SEC; }\n" + macros),
 # (A) VERSION check before the DMA is touched
 ("    d->version = 0;\n    XAxiDma_Config *cfg = XAxiDma_LookupConfig(SR_DMA_BASE);", "    d->version = 0;\n" + new_ver_block + "    XAxiDma_Config *cfg = XAxiDma_LookupConfig(SR_DMA_BASE);"),
 ("    if (XAxiDma_HasSg(&d->dma)) { xil_printf(\"SR: DMA is in scatter-gather mode, simple mode expected\\r\\n\"); return SR_RC_DMA_INIT; }\n\n" + ver_block,
  "    if (XAxiDma_HasSg(&d->dma)) { xil_printf(\"SR: DMA is in scatter-gather mode, simple mode expected\\r\\n\"); return SR_RC_DMA_INIT; }\n\n"),
 # (C) timing split points
 ] + run_pairs + [
 ("    }\n\n    /* wait: core DONE (or ERROR) and both DMA channels idle,", "    }\n    SR_TS(3);\n\n    /* wait: core DONE (or ERROR) and both DMA channels idle,"),
 ("    }\n\n    const uint32_t st = reg_rd(d, SR_REG_STATUS);\n    if (st & SR_STATUS_ERROR)", "    }\n    SR_TS(4);\n\n    const uint32_t st = reg_rd(d, SR_REG_STATUS);\n    if (st & SR_STATUS_ERROR)"),
 ("    d->last_cycles = reg_rd(d, SR_REG_CYCLES);\n    rc = SR_RC_OK;\n", "    d->last_cycles = reg_rd(d, SR_REG_CYCLES);\n    SR_TS(5);\n    SR_TS_END();\n    rc = SR_RC_OK;\n"),
])

# ---------------------------------------------------------------- main.c
split_fn = """
#ifdef SR_TIMING_SPLIT
/* prints and clears the driver's summed split (sr_driver.h); only in -DSR_TIMING_SPLIT builds */
static void print_split(const char *tag)
{
    xil_printf("%s split over %u call(s), us: busy+regs %u, flush in %u, flush out %u, DMA set-up+START %u, wait %u, check+invalidate+CYCLES %u, sum %u\\r\\n", tag, sr_split_calls,
               ticks_to_us(sr_split_sum[0]), ticks_to_us(sr_split_sum[1]), ticks_to_us(sr_split_sum[2]), ticks_to_us(sr_split_sum[3]), ticks_to_us(sr_split_sum[4]),
               ticks_to_us(sr_split_sum[5]), ticks_to_us(sr_split_sum[6]));
    for (int k = 0; k < SR_SPLIT_N; k++) sr_split_sum[k] = 0;
    sr_split_calls = 0;
}
#endif
"""
if kind == "tiled":
    t2_anchor = "    xil_printf(\"T2: %u tiles done in %u ms, CYCLES per tile min/max %u/%u\\r\\n\", tm.tiles, ticks_to_us(tt) / 1000u, tc.cyc_min, tc.cyc_max);\n"
else:
    t2_anchor = "    xil_printf(\"T2: frame done in %u ms (pad %u us, DMA + compute %u us), CYCLES %u\\r\\n\", ticks_to_us(tt) / 1000u, ticks_to_us(tp), ticks_to_us(tm.t_run), dev.last_cycles);\n"
t3_anchor = "                   (int)us_tot - (int)(us_pad + us_copy + us_run));\n"
edit(app / "main.c", [
 ("static sr_dev_t dev;\n", "static sr_dev_t dev;\n" + split_fn),
 (t2_anchor, t2_anchor + "#ifdef SR_TIMING_SPLIT\n    print_split(\"T2\");\n#endif\n"),
 (t3_anchor, t3_anchor + "#ifdef SR_TIMING_SPLIT\n        print_split(\"  frame\");\n#endif\n"),
 # (B) T7 never calls sr_init(), so the A9 global timer was never enabled: every T7 time printed 0
 ("    xil_printf(\"T7: ARM-only baseline (no FPGA), %d frame(s) of the image at 0x%08x\\r\\n\", SR_T7_FRAMES, (unsigned)SR_IN_ADDR);\n",
  "    sr_timer_init();   /* T7 never calls sr_init(), which is where the A9 global timer is enabled: without this every T7 time read 0 (2026-10-27) */\n    xil_printf(\"T7: ARM-only baseline (no FPGA), %d frame(s) of the image at 0x%08x\\r\\n\", SR_T7_FRAMES, (unsigned)SR_IN_ADDR);\n"),
])

# ---------------------------------------------------------------- build_elf.sh: output name suffix for the flagged build (default unchanged)
b = root / "build_elf.sh"
s = b.read_text()
assert s.count("software/board/build/sr_app_t$N.elf") == 2 and s.count("software/board/build/link_t$N.log") == 2
s = s.replace("software/board/build/sr_app_t$N.elf", "software/board/build/sr_app_t$N${SR_ELF_SUFFIX:-}.elf").replace("software/board/build/link_t$N.log", "software/board/build/link_t$N${SR_ELF_SUFFIX:-}.log")
s = s.replace("# Env overrides (for a fresh checkout / new platform):", "# SR_ELF_SUFFIX=_split (with -DSR_TIMING_SPLIT) names the output sr_app_t<N>_split.elf so the production ELF is not overwritten.\n# Env overrides (for a fresh checkout / new platform):")
b.write_text(s)
print("patched", root, kind)
