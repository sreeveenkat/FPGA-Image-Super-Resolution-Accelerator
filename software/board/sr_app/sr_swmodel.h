/* ARM-only baseline: the integer model of the network in portable C (no Xilinx headers), one tile at a time.
 *
 * sr_sw_run_tile() does on the CPU exactly what the FPGA tile core does: 70x70x3 input (RGB raster [y][x][c], 3 px halo) -> 128x128x3 output.
 * Its signature matches sr_tile_fn (sr_tiling.h), so the same tile loop drives either the FPGA or this function.  Arithmetic = integer_reference.py:
 *   acc = bias + sum(x * w);  y = clamp((acc * M + 2^(SHIFT-1)) >> SHIFT, 0, 255)  (arithmetic shift, 64-bit product)
 * Proven byte-exact on the PC against the expected board output (software/board/test_swmodel.sh).  Plain scalar C, no NEON intrinsics. */
#ifndef SR_SWMODEL_H
#define SR_SWMODEL_H

#include <stdint.h>

int sr_sw_run_tile(void *ctx, const uint8_t *in70, uint8_t *out128);   /* ctx unused; returns 0 */

#endif
