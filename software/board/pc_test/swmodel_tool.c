/* PC-only helper for software/board/test_swmodel.sh: runs the ARM-only baseline (sr_swmodel.c) through the REAL tile loop (sr_tiling.c) on a whole image.
 *   swmodel_tool in.raw out.raw      SRIM in -> SRIM out (2x), prints the FNV-1a 32 of the output payload and the PC time per frame */
#define _POSIX_C_SOURCE 199309L
#include <stdio.h>
#include <stdlib.h>
#include <string.h>
#include <time.h>
#include "sr_tiling.h"
#include "sr_swmodel.h"

int main(int argc, char **argv)
{
    if (argc != 3) { fprintf(stderr, "usage: swmodel_tool in.raw out.raw\n"); return 2; }
    FILE *f = fopen(argv[1], "rb");
    if (!f) { fprintf(stderr, "cannot open %s\n", argv[1]); return 2; }
    uint8_t hdr[16]; uint32_t w, h;
    if (fread(hdr, 1, 16, f) != 16 || memcmp(hdr, "SRIM", 4) != 0) { fprintf(stderr, "bad SRIM header\n"); return 2; }
    memcpy(&w, hdr + 4, 4); memcpy(&h, hdr + 8, 4);
    sr_geom_t g; sr_geom(w, h, &g);
    uint8_t *lr = malloc(3u * (size_t)w * h), *padded = malloc(sr_padded_bytes(&g)), *out = malloc(sr_out_bytes(&g));
    uint8_t *tin = malloc(SR_TILE_IN_BYTES), *tout = malloc(SR_TILE_OUT_BYTES);
    if (!lr || !padded || !out || !tin || !tout) return 2;
    if (fread(lr, 1, 3u * (size_t)w * h, f) != 3u * (size_t)w * h) { fprintf(stderr, "short file\n"); return 2; }
    fclose(f);
    struct timespec t0, t1;
    clock_gettime(CLOCK_MONOTONIC, &t0);
    sr_pad_image(lr, &g, padded);
    sr_timing_t tm;
    if (sr_upscale_padded(padded, &g, out, tin, tout, sr_sw_run_tile, NULL, NULL, &tm) != 0) return 1;
    clock_gettime(CLOCK_MONOTONIC, &t1);
    const double ms = (t1.tv_sec - t0.tv_sec) * 1e3 + (t1.tv_nsec - t0.tv_nsec) / 1e6;
    f = fopen(argv[2], "wb"); if (!f) return 2;
    uint32_t oh[3] = { 2 * w, 2 * h, 0 };
    fwrite("SRIM", 1, 4, f); fwrite(oh, 4, 3, f); fwrite(out, 1, sr_out_bytes(&g), f); fclose(f);
    printf("%ux%u -> %ux%u, %u tiles, fnv1a32=0x%08x, PC time %.1f ms\n", w, h, 2 * w, 2 * h, tm.tiles, sr_fnv1a32(out, sr_out_bytes(&g)), ms);
    free(lr); free(padded); free(out); free(tin); free(tout);
    return 0;
}
