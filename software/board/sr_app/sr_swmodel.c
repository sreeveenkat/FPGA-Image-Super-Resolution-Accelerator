/* ARM-only baseline: integer model of one tile in C.  See sr_swmodel.h. */
#include "sr_swmodel.h"
#include "sr_weights.h"      /* generated: software/host_tools/weights_h.py */

#define T_IN  70             /* 64 + 2 * 3 halo */
#define S1    68             /* L1 output side (3x3 valid) */
#define S2    66             /* L2 (3x3 depthwise) */
#define S3    66             /* L3 (1x1) */
#define S4    64             /* L4 (3x3) */
#define C     16

/* activations, [y][x][c] (pixel-major, like the RTL words); static: the board program's stack is small */
static uint8_t a1[S1 * S1 * C], a2[S2 * S2 * C], a3[S3 * S3 * C];

static inline uint8_t requant(int32_t acc, uint32_t m, int shift)
{
    int64_t y = ((int64_t)acc * (int64_t)m + ((int64_t)1 << (shift - 1))) >> shift;   /* gcc: >> of a negative value is arithmetic */
    return (uint8_t)(y < 0 ? 0 : (y > 255 ? 255 : y));
}

int sr_sw_run_tile(void *ctx, const uint8_t *in, uint8_t *out)
{
    (void)ctx;
    /* L1: conv 3x3, 3 -> 16 */
    for (int y = 0; y < S1; y++)
        for (int x = 0; x < S1; x++)
            for (int co = 0; co < C; co++) {
                int32_t acc = sr_L1_b[co];
                const int8_t *w = &sr_L1_w[co * 27];
                for (int ci = 0; ci < 3; ci++)
                    for (int ky = 0; ky < 3; ky++)
                        for (int kx = 0; kx < 3; kx++)
                            acc += in[((y + ky) * T_IN + x + kx) * 3 + ci] * w[(ci * 3 + ky) * 3 + kx];
                a1[(y * S1 + x) * C + co] = requant(acc, sr_L1_m[co], SR_L1_SHIFT);
            }
    /* L2: depthwise 3x3 */
    for (int y = 0; y < S2; y++)
        for (int x = 0; x < S2; x++)
            for (int c = 0; c < C; c++) {
                int32_t acc = sr_L2_b[c];
                for (int ky = 0; ky < 3; ky++)
                    for (int kx = 0; kx < 3; kx++)
                        acc += a1[((y + ky) * S1 + x + kx) * C + c] * sr_L2_w[c * 9 + ky * 3 + kx];
                a2[(y * S2 + x) * C + c] = requant(acc, sr_L2_m[c], SR_L2_SHIFT);
            }
    /* L3: pointwise 1x1, 16 -> 16 */
    for (int p = 0; p < S3 * S3; p++)
        for (int co = 0; co < C; co++) {
            int32_t acc = sr_L3_b[co];
            for (int ci = 0; ci < C; ci++) acc += a2[p * C + ci] * sr_L3_w[co * C + ci];
            a3[p * C + co] = requant(acc, sr_L3_m[co], SR_L3_SHIFT);
        }
    /* L4: conv 3x3, 16 -> 12, then pixel shuffle k = 4c + 2dy + dx into the 128x128x3 output */
    for (int y = 0; y < S4; y++)
        for (int x = 0; x < S4; x++)
            for (int k = 0; k < 12; k++) {
                int32_t acc = sr_L4_b[k];
                const int8_t *w = &sr_L4_w[k * C * 9];
                for (int ky = 0; ky < 3; ky++)
                    for (int kx = 0; kx < 3; kx++) {
                        const uint8_t *px = &a3[((y + ky) * S3 + x + kx) * C];
                        for (int ci = 0; ci < C; ci++) acc += px[ci] * w[(ci * 3 + ky) * 3 + kx];
                    }
                const int c = k >> 2, dy = (k >> 1) & 1, dx = k & 1;
                out[((2 * y + dy) * (2 * S4) + 2 * x + dx) * 3 + c] = requant(acc, sr_L4_m[k], SR_L4_SHIFT);
            }
    return 0;
}
