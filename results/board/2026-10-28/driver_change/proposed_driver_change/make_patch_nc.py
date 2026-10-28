#!/usr/bin/env python3
"""PROPOSAL (not applied): non-cacheable DMA buffers for the pipeline tree, behind -DSR_NC_OUT / -DSR_NC_PAD.  make_patch_nc.py <copy-of-sandbox_pipe/software/board>"""
import sys
from pathlib import Path
app = Path(sys.argv[1]) / "sr_app"

def edit(path, pairs):
    s = path.read_text()
    for a, b in pairs:
        assert s.count(a) == 1, (path.name, s.count(a), a[:70])
        s = s.replace(a, b)
    path.write_text(s)

edit(app / "sr_driver.h", [("/* Base address of sr_accel_top/s_axi:",
"""/* Optional non-cacheable DMA buffers (compile-time flags, both OFF by default: the code is then the same as without this block).
 *   -DSR_NC_OUT : the output-image region [SR_OUT_ADDR, +SR_OUT_SIZE) = 0x12000000 + 16 MB = sections 0x120..0x12F (the DMA writes it)
 *   -DSR_NC_PAD : the padded-input region [SR_PAD_ADDR, +SR_PAD_SIZE) = 0x14000000 + 32 MB = sections 0x140..0x15F (the DMA reads it)
 * sr_nc_init() (main.c calls it once after sr_init) cleans + invalidates each region, then marks its 1 MB sections Normal Non-cacheable with Xil_SetTlbAttributes.
 * sr_run_frame_len() then skips the flush / invalidate of a buffer INSIDE such a region; for the padded input it drains the write buffers instead (DSB + PL310 cache
 * sync), so the DMA sees every byte the ARM wrote.  Buffers outside the regions (T1 / T5 tile buffers, test arrays) keep the cached path. */
#if defined(SR_NC_OUT) || defined(SR_NC_PAD)
void sr_nc_init(void);
void sr_write_drain(void);
#endif

/* Base address of sr_accel_top/s_axi:""")])

edit(app / "sr_driver.c", [
 ("#include \"xstatus.h\"\n", """#include "xstatus.h"
#if defined(SR_NC_OUT) || defined(SR_NC_PAD)
#include "xil_mmu.h"
#include "xpseudo_asm.h"
#include "xparameters_ps.h"
#include "xl2cc.h"
#include "sr_memmap.h"
_Static_assert((SR_OUT_ADDR & 0xFFFFFu) == 0 && (SR_OUT_SIZE & 0xFFFFFu) == 0 && (SR_PAD_ADDR & 0xFFFFFu) == 0 && (SR_PAD_SIZE & 0xFFFFFu) == 0,
               "non-cacheable regions must be whole 1 MB sections");

static inline int sr_inside(const void *p, uint32_t base, uint32_t size) { const uintptr_t a = (uintptr_t)p; return a >= base && a < (uintptr_t)base + size; }

/* every ARM write before this point is in DDR when it returns: DSB, then the PL310 cache-sync (drains its write buffers), then DSB */
void sr_write_drain(void)
{
    dsb();
    Xil_Out32(XPS_L2CC_BASEADDR + XPS_L2CC_CACHE_SYNC_OFFSET, 0u);
    while (Xil_In32(XPS_L2CC_BASEADDR + XPS_L2CC_CACHE_SYNC_OFFSET) & 1u) { }
    dsb();
}

static void nc_region(uint32_t base, uint32_t size)
{
    Xil_DCacheFlushRange((UINTPTR)base, size);                     /* nothing of the region may stay in L1 / L2 when its attributes change */
    for (uint32_t a = base; a < base + size; a += 0x100000u) Xil_SetTlbAttributes((INTPTR)a, NORM_NONCACHE);
}

void sr_nc_init(void)
{
#ifdef SR_NC_OUT
    nc_region(SR_OUT_ADDR, SR_OUT_SIZE);
#endif
#ifdef SR_NC_PAD
    nc_region(SR_PAD_ADDR, SR_PAD_SIZE);
#endif
    dsb();
}
#endif
"""),
 ("    Xil_DCacheFlushRange((UINTPTR)in, in_bytes > in_len ? in_bytes : in_len);\n    SR_TS(1);\n    Xil_DCacheFlushRange((UINTPTR)out, out_bytes);\n    SR_TS(2);\n",
  """#ifdef SR_NC_PAD
    if (sr_inside(in, SR_PAD_ADDR, SR_PAD_SIZE)) sr_write_drain(); else
#endif
    Xil_DCacheFlushRange((UINTPTR)in, in_bytes > in_len ? in_bytes : in_len);
    SR_TS(1);
#ifdef SR_NC_OUT
    if (!sr_inside(out, SR_OUT_ADDR, SR_OUT_SIZE))
#endif
    Xil_DCacheFlushRange((UINTPTR)out, out_bytes);
    SR_TS(2);
"""),
 ("    Xil_DCacheInvalidateRange((UINTPTR)out, out_bytes);\n    d->last_cycles", """#ifdef SR_NC_OUT
    if (!sr_inside(out, SR_OUT_ADDR, SR_OUT_SIZE))
#endif
    Xil_DCacheInvalidateRange((UINTPTR)out, out_bytes);
    d->last_cycles"""),
])

edit(app / "main.c", [
 ("""    const uint32_t bytes = 16u + (uint32_t)sr_out_bytes(g);
    Xil_DCacheFlushRange((UINTPTR)SR_OUT_ADDR, bytes);            /* the host reads DDR over JTAG: write the cache back first */
    const uint32_t fnv = sr_fnv1a32((const uint8_t *)(SR_OUT_ADDR + 16), sr_out_bytes(g));
""", """    const uint32_t bytes = 16u + (uint32_t)sr_out_bytes(g);
#ifdef SR_NC_OUT
    sr_write_drain();                                             /* non-cacheable output: only the ARM-written header can still be in a write buffer */
    const uint64_t tf0 = now_ticks();
#else
    Xil_DCacheFlushRange((UINTPTR)SR_OUT_ADDR, bytes);            /* the host reads DDR over JTAG: write the cache back first */
#endif
    const uint32_t fnv = sr_fnv1a32((const uint8_t *)(SR_OUT_ADDR + 16), sr_out_bytes(g));
#ifdef SR_NC_OUT
    xil_printf("NC: ARM read of the output buffer (FNV-1a over %u bytes, non-cacheable): %u us\\r\\n", (unsigned)sr_out_bytes(g), ticks_to_us(now_ticks() - tf0));
#endif
"""),
 ("""        Xil_DCacheFlushRange((UINTPTR)SR_OUT_ADDR, 16u + (uint32_t)sr_out_bytes(&g));
        const uint32_t fnv = sr_fnv1a32((const uint8_t *)(SR_OUT_ADDR + 16), sr_out_bytes(&g));
        if (f == 0) fnv0 = fnv; else if (fnv != fnv0) same = 0;
""", """#ifndef SR_NC_OUT
        Xil_DCacheFlushRange((UINTPTR)SR_OUT_ADDR, 16u + (uint32_t)sr_out_bytes(&g));
#endif
#ifdef SR_NC_OUT
        const uint64_t tf0 = now_ticks();
#endif
        const uint32_t fnv = sr_fnv1a32((const uint8_t *)(SR_OUT_ADDR + 16), sr_out_bytes(&g));
#ifdef SR_NC_OUT
        if (f == 0) xil_printf("  ARM read of the output buffer (FNV-1a over %u bytes, non-cacheable): %u us\\r\\n", (unsigned)sr_out_bytes(&g), ticks_to_us(now_ticks() - tf0));
#endif
        if (f == 0) fnv0 = fnv; else if (fnv != fnv0) same = 0;
"""),
 ("""    xil_printf("init ok: VERSION 0x%08x, MAX_W %u\\r\\n", sr_reg_read(&dev, SR_REG_VERSION), sr_reg_read(&dev, SR_REG_MAX_W));
""", """    xil_printf("init ok: VERSION 0x%08x, MAX_W %u\\r\\n", sr_reg_read(&dev, SR_REG_VERSION), sr_reg_read(&dev, SR_REG_MAX_W));
#if defined(SR_NC_OUT) || defined(SR_NC_PAD)
    { const uint64_t tn0 = now_ticks(); sr_nc_init();
      xil_printf("NC: output region %s, padded-input region %s non-cacheable (set-up %u us)\\r\\n",
#ifdef SR_NC_OUT
                 "0x12000000+16MB",
#else
                 "-",
#endif
#ifdef SR_NC_PAD
                 "0x14000000+32MB",
#else
                 "-",
#endif
                 ticks_to_us(now_ticks() - tn0)); }
#endif
"""),
])
print("patched", app)
