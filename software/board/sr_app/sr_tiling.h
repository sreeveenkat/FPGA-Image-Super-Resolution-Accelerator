/* Tiling of a whole image for the tile core - portable C (no Xilinx headers), tested on the PC against software/ai/quantization/integer_reference.py.
 *
 * Geometry: the LR image (w x h, RGB, row-major, 3 bytes per pixel) is replicate-padded by SR_HALO = 3 px on every side, and extended at the right / bottom
 * (also by replication) so that the core area is a multiple of SR_HC = 64 in both directions.  Tile (ty, tx) is the 70 x 70 window of the padded image whose
 * top-left corner is at padded pixel (64*tx, 64*ty); the core returns 128 x 128 pixels that are placed at output pixel (128*tx, 128*ty), cropped to 2w x 2h.
 * The result is identical to integer_reference.upscale() (whole image) - proven by software/board/test_tiling.py.
 */
#ifndef SR_TILING_H
#define SR_TILING_H

#include <stddef.h>
#include <stdint.h>
#include "sr_regs.h"

typedef struct {
    uint32_t w, h;                  /* LR image size */
    uint32_t tiles_x, tiles_y;      /* ceil(w / 64), ceil(h / 64)   (960x540 -> 15 x 9 = 135 tiles) */
    uint32_t padded_w, padded_h;    /* tiles * 64 + 6 */
} sr_geom_t;

void   sr_geom(uint32_t w, uint32_t h, sr_geom_t *g);
size_t sr_padded_bytes(const sr_geom_t *g);                 /* padded_w * padded_h * 3 */
size_t sr_out_bytes(const sr_geom_t *g);                    /* (2w) * (2h) * 3 */

/* padded must hold sr_padded_bytes() */
void sr_pad_image(const uint8_t *lr, const sr_geom_t *g, uint8_t *padded);
/* tile70: SR_TILE_IN_BYTES (14,700) bytes, RGB raster [y][x][c], ready to be streamed to the core */
void sr_cut_tile(const uint8_t *padded, const sr_geom_t *g, uint32_t ty, uint32_t tx, uint8_t *tile70);
/* tile128: SR_TILE_OUT_BYTES (49,152) bytes from the core; out is the (2w x 2h x 3) result image; parts outside it are dropped */
void sr_place_tile(const uint8_t *tile128, const sr_geom_t *g, uint32_t ty, uint32_t tx, uint8_t *out);

/* Tile loop.  run_tile(ctx, in70, out128) returns 0 on success.  now() (may be NULL) returns a tick counter; the time spent in cut / run / place is accumulated. */
typedef int (*sr_tile_fn)(void *ctx, const uint8_t *in70, uint8_t *out128);
typedef uint64_t (*sr_clock_fn)(void);
typedef struct { uint64_t t_cut, t_run, t_place; uint32_t tiles; } sr_timing_t;
int sr_upscale_padded(const uint8_t *padded, const sr_geom_t *g, uint8_t *out, uint8_t *tin, uint8_t *tout,
                      sr_tile_fn run_tile, void *ctx, sr_clock_fn now, sr_timing_t *tm);

/* FNV-1a 32 bit (the same function as srim.fnv1a32 in software/host_tools/srim.py) */
uint32_t sr_fnv1a32(const uint8_t *data, size_t n);

#endif
