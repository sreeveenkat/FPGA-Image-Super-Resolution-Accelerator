#include <string.h>
#include "sr_tiling.h"

void sr_geom(uint32_t w, uint32_t h, sr_geom_t *g)
{
    g->w = w;
    g->h = h;
    g->tiles_x = (w + SR_HC - 1u) / SR_HC;
    g->tiles_y = (h + SR_HC - 1u) / SR_HC;
    g->padded_w = g->tiles_x * SR_HC + 2u * SR_HALO;
    g->padded_h = g->tiles_y * SR_HC + 2u * SR_HALO;
}

void sr_geom_frame(uint32_t w, uint32_t h, sr_geom_t *g)
{
    g->w = w;
    g->h = h;
    g->tiles_x = 1u;
    g->tiles_y = 1u;
    g->padded_w = w + 2u * SR_HALO;
    g->padded_h = h + 2u * SR_HALO;
}

size_t sr_padded_bytes(const sr_geom_t *g) { return (size_t)g->padded_w * g->padded_h * 3u; }
size_t sr_out_bytes(const sr_geom_t *g)    { return (size_t)(2u * g->w) * (2u * g->h) * 3u; }

void sr_pad_image(const uint8_t *lr, const sr_geom_t *g, uint8_t *padded)
{
    const uint32_t right = g->padded_w - SR_HALO - g->w;          /* replicated pixels on the right (3 + extension) */
    for (uint32_t y = 0; y < g->padded_h; y++) {
        uint32_t sy = (y < SR_HALO) ? 0u : (y - SR_HALO);
        if (sy > g->h - 1u) sy = g->h - 1u;                       /* bottom border and extension: last row */
        const uint8_t *src = lr + (size_t)sy * g->w * 3u;
        uint8_t *dst = padded + (size_t)y * g->padded_w * 3u;
        for (uint32_t x = 0; x < SR_HALO; x++) { dst[3u * x] = src[0]; dst[3u * x + 1] = src[1]; dst[3u * x + 2] = src[2]; }
        memcpy(dst + 3u * SR_HALO, src, (size_t)g->w * 3u);
        const uint8_t *last = src + 3u * (g->w - 1u);
        uint8_t *r = dst + 3u * (SR_HALO + g->w);
        for (uint32_t x = 0; x < right; x++) { r[3u * x] = last[0]; r[3u * x + 1] = last[1]; r[3u * x + 2] = last[2]; }
    }
}

void sr_cut_tile(const uint8_t *padded, const sr_geom_t *g, uint32_t ty, uint32_t tx, uint8_t *tile70)
{
    for (uint32_t r = 0; r < SR_TILE_IN_W; r++)
        memcpy(tile70 + (size_t)r * SR_TILE_IN_W * 3u,
               padded + ((size_t)(ty * SR_HC + r) * g->padded_w + (size_t)tx * SR_HC) * 3u,
               (size_t)SR_TILE_IN_W * 3u);
}

void sr_place_tile(const uint8_t *tile128, const sr_geom_t *g, uint32_t ty, uint32_t tx, uint8_t *out)
{
    const uint32_t out_w = 2u * g->w, out_h = 2u * g->h;
    const uint32_t ox0 = tx * SR_TILE_OUT_W;
    if (ox0 >= out_w) return;
    uint32_t cols = out_w - ox0;
    if (cols > SR_TILE_OUT_W) cols = SR_TILE_OUT_W;
    for (uint32_t r = 0; r < SR_TILE_OUT_W; r++) {
        const uint32_t oy = ty * SR_TILE_OUT_W + r;
        if (oy >= out_h) break;
        memcpy(out + ((size_t)oy * out_w + ox0) * 3u, tile128 + (size_t)r * SR_TILE_OUT_W * 3u, (size_t)cols * 3u);
    }
}

int sr_upscale_padded(const uint8_t *padded, const sr_geom_t *g, uint8_t *out, uint8_t *tin, uint8_t *tout,
                      sr_tile_fn run_tile, void *ctx, sr_clock_fn now, sr_timing_t *tm)
{
    sr_timing_t t = {0, 0, 0, 0};
    for (uint32_t ty = 0; ty < g->tiles_y; ty++) {
        for (uint32_t tx = 0; tx < g->tiles_x; tx++) {
            uint64_t t0 = now ? now() : 0;
            sr_cut_tile(padded, g, ty, tx, tin);
            uint64_t t1 = now ? now() : 0;
            int rc = run_tile(ctx, tin, tout);
            uint64_t t2 = now ? now() : 0;
            if (rc != 0) {
                if (tm) *tm = t;
                return rc;
            }
            sr_place_tile(tout, g, ty, tx, out);
            uint64_t t3 = now ? now() : 0;
            t.t_cut += t1 - t0;
            t.t_run += t2 - t1;
            t.t_place += t3 - t2;
            t.tiles++;
        }
    }
    if (tm) *tm = t;
    return 0;
}

uint32_t sr_fnv1a32(const uint8_t *data, size_t n)
{
    uint32_t h = 0x811C9DC5u;
    for (size_t i = 0; i < n; i++) { h ^= data[i]; h *= 0x01000193u; }
    return h;
}
