# Golden test vectors (generated, NOT tracked except this file)

Regenerate with `.venv/bin/python software/ai/quantization/export_rtl.py` (deterministic; needs `data/train/HR` for the `real*` tiles).
Each tile `<name>` has `<name>.npz` (arrays `tile`, `L1`..`L4` as (C,H,W), `out` as (2h,2w,3)) and byte-per-line hex dumps
`<name>_in.hex`, `_L1.hex` ... `_L4.hex`, `_out.hex`, ordered `[y][x][c]` (channel fastest). Formats: see the docstring of
`software/ai/quantization/export_rtl.py`. Tiles: zeros, full255, noise, pixel, ramp, real0-2, real_corner (replicate halo), small12 (12x12 -> 12x12).
Full tile shapes: in 70x70x3, L1 68x68x16, L2 66x66x16, L3 66x66x16, L4 64x64x12, out 128x128x3.
