/* PC-only helper for software/board/test_tiling.py: runs the REAL sr_tiling.c code (same tile loop as the board) with file-based mock tile runners.
 *   tiling_tool cut      in.raw dir            writes dir/in_<ty>_<tx>.bin (70x70x3 each); the tile "output" is zeros
 *   tiling_tool assemble in.raw dir out.raw    reads dir/out_<ty>_<tx>.bin (128x128x3 each) instead of running the core, writes the SRIM result
 *   tiling_tool fnv file                       prints the FNV-1a 32 of the PAYLOAD of an SRIM file (the checksum the board prints)
 * SRIM = 16-byte header (magic SRIM, u32 w, u32 h, u32 reserved, little endian) + RGB payload. */
#include <stdio.h>
#include <stdlib.h>
#include <string.h>
#include "sr_tiling.h"

static uint8_t *read_file(const char *path, size_t *n)
{
    FILE *f = fopen(path, "rb");
    if (!f) { fprintf(stderr, "cannot open %s\n", path); exit(2); }
    fseek(f, 0, SEEK_END); long len = ftell(f); fseek(f, 0, SEEK_SET);
    uint8_t *b = malloc((size_t)len);
    if (!b || fread(b, 1, (size_t)len, f) != (size_t)len) { fprintf(stderr, "read error %s\n", path); exit(2); }
    fclose(f); *n = (size_t)len;
    return b;
}
static uint8_t *read_srim(const char *path, uint32_t *w, uint32_t *h)
{
    size_t n; uint8_t *b = read_file(path, &n);
    if (n < 16 || memcmp(b, "SRIM", 4) != 0) { fprintf(stderr, "%s: bad SRIM header\n", path); exit(2); }
    memcpy(w, b + 4, 4); memcpy(h, b + 8, 4);                      /* little endian host (x86 / ARM) */
    if (n != 16u + 3u * (size_t)*w * *h) { fprintf(stderr, "%s: size mismatch\n", path); exit(2); }
    return b + 16;
}

typedef struct { const char *dir; int mode; uint32_t ty, tx, tiles_x; uint32_t counter; } mock_t;
static int mock_run(void *ctx, const uint8_t *in70, uint8_t *out128)
{
    mock_t *m = ctx;
    uint32_t ty = m->counter / m->tiles_x, tx = m->counter % m->tiles_x;   /* sr_upscale_padded visits tiles in raster order */
    char p[1024];
    m->counter++;
    if (m->mode == 0) {
        snprintf(p, sizeof p, "%s/in_%u_%u.bin", m->dir, ty, tx);
        FILE *f = fopen(p, "wb"); if (!f) return 1;
        fwrite(in70, 1, SR_TILE_IN_BYTES, f); fclose(f);
        memset(out128, 0, SR_TILE_OUT_BYTES);
    } else {
        snprintf(p, sizeof p, "%s/out_%u_%u.bin", m->dir, ty, tx);
        FILE *f = fopen(p, "rb"); if (!f) { fprintf(stderr, "missing %s\n", p); return 1; }
        size_t n = fread(out128, 1, SR_TILE_OUT_BYTES, f); fclose(f);
        if (n != SR_TILE_OUT_BYTES) { fprintf(stderr, "short %s\n", p); return 1; }
    }
    return 0;
}

int main(int argc, char **argv)
{
    if (argc == 3 && !strcmp(argv[1], "fnv")) {
        uint32_t w, h; uint8_t *px = read_srim(argv[2], &w, &h);
        printf("0x%08x\n", sr_fnv1a32(px, 3u * (size_t)w * h));
        free(px - 16);
        return 0;
    }
    if (!((argc == 4 && !strcmp(argv[1], "cut")) || (argc == 5 && !strcmp(argv[1], "assemble")))) {
        fprintf(stderr, "usage: tiling_tool cut in.raw dir | assemble in.raw dir out.raw | fnv file.raw\n");
        return 2;
    }
    uint32_t w, h; uint8_t *lr = read_srim(argv[2], &w, &h);
    sr_geom_t g; sr_geom(w, h, &g);
    uint8_t *padded = malloc(sr_padded_bytes(&g)), *out = malloc(sr_out_bytes(&g));
    uint8_t *tin = malloc(SR_TILE_IN_BYTES), *tout = malloc(SR_TILE_OUT_BYTES);
    if (!padded || !out || !tin || !tout) return 2;
    sr_pad_image(lr, &g, padded);
    mock_t m = { argv[3], !strcmp(argv[1], "assemble"), 0, 0, g.tiles_x, 0 };
    sr_timing_t tm;
    if (sr_upscale_padded(padded, &g, out, tin, tout, mock_run, &m, NULL, &tm) != 0) return 1;
    printf("%ux%u -> %ux%u, %u x %u tiles (%u), padded %ux%u\n", w, h, 2 * w, 2 * h, g.tiles_x, g.tiles_y, tm.tiles, g.padded_w, g.padded_h);
    if (m.mode) {
        FILE *f = fopen(argv[4], "wb"); if (!f) return 2;
        uint32_t hdr[3] = { 2 * w, 2 * h, 0 };
        fwrite("SRIM", 1, 4, f); fwrite(hdr, 4, 3, f); fwrite(out, 1, sr_out_bytes(&g), f); fclose(f);
    }
    free(lr - 16); free(padded); free(out); free(tin); free(tout);
    return 0;
}
