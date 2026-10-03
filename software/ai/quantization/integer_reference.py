"""Bit-accurate INTEGER model of SRNet x2 (the golden reference for the RTL, M4/M5).

Pure NumPy, integer dtypes only. No torch, no float in the inference path (the float scales stored in the parameter file are
documentation only and are never read here).

Arithmetic, identical for every layer (this is exactly what the hardware must do):
    acc = bias[co] + sum(x[ci, y+ky, x+kx] * w[co, ci, ky, kx])         x: uint8 value, w: int8, acc: exact (int64 here)
    y   = (acc * M[co] + 2**(SHIFT-1)) >> SHIFT                          arithmetic shift = floor = round half UP
    out = clip(y, 0, 255)                                                ReLU (hidden layers) / pixel clamp (last layer)
M[co] is a per-output-channel unsigned 16-bit multiplier, SHIFT is one value per layer.

Network (all convolutions VALID):
    replicate-pad 3 -> conv1 3x3 (3->16) -> dw 3x3 (16) -> pw 1x1 (16->16) -> conv4 3x3 (16->12) -> pixel shuffle
Pixel shuffle: out[c, 2y+dy, 2x+dx] = conv4[4c + 2dy + dx, y, x].
Weight layout everywhere: [co][ci][ky][kx] (depthwise: [c][0][ky][kx]).
"""

import numpy as np

HALO = 3
LAYER_NAMES = ("L1", "L2", "L3", "L4")
# (name, in_ch, out_ch, kernel, depthwise)
LAYER_SPEC = (("L1", 3, 16, 3, False), ("L2", 16, 16, 3, True), ("L3", 16, 16, 1, False), ("L4", 16, 12, 3, False))
ACC_BITS = 32  # the accumulator must fit signed 32 bit (checked in tests); the product acc*M needs ~40 bits in hardware


class QNet:
    """Integer parameters of the network: per layer int8 weights, int32 bias, uint16 M (per out channel), SHIFT."""

    def __init__(self, layers):
        self.layers = layers  # list of dicts: name, w (int8), b (int32), m (int64 array), shift (int), depthwise (bool)
        for L in layers:
            assert L["w"].dtype == np.int8 and L["b"].dtype == np.int32
            assert (L["m"] >= 0).all() and (L["m"] < 1 << 16).all(), "M must fit unsigned 16 bit"
            assert 1 <= L["shift"] <= 40

    @classmethod
    def load(cls, path):
        z = np.load(path)
        layers = []
        for name, cin, cout, k, dw in LAYER_SPEC:
            layers.append(dict(name=name, w=z[f"{name}_w"], b=z[f"{name}_b"], m=z[f"{name}_m"].astype(np.int64),
                               shift=int(z[f"{name}_shift"]), depthwise=dw))
            assert layers[-1]["w"].shape == ((cout, 1, k, k) if dw else (cout, cin, k, k)), name
        return cls(layers)


def conv_requant(x, w, b, m, shift, depthwise=False):
    """VALID convolution + requantize + clamp [0,255].  x: (C_in,H,W) integer array -> (C_out,H-k+1,W-k+1) int32."""
    k = w.shape[2]
    c_out = w.shape[0]
    h, wd = x.shape[1] - k + 1, x.shape[2] - k + 1
    x = x.astype(np.int64)
    acc = np.zeros((c_out, h, wd), dtype=np.int64) + b.astype(np.int64)[:, None, None]
    for ky in range(k):
        for kx in range(k):
            win = x[:, ky:ky + h, kx:kx + wd]
            tap = w[:, :, ky, kx].astype(np.int64)
            if depthwise:
                acc += win * tap[:, 0][:, None, None]
            else:
                acc += np.einsum("oc,chw->ohw", tap, win)
    return requant(acc, m, shift)


def requant(acc, m, shift):
    """acc: int64 (C,H,W) -> uint8-range int32.  Round half up, arithmetic shift, clamp [0,255]."""
    y = (acc * m.astype(np.int64)[:, None, None] + (1 << (shift - 1))) >> shift
    return np.clip(y, 0, 255).astype(np.int32)


def pixel_shuffle(x):
    """(12,H,W) -> (3,2H,2W), PyTorch order k = 4c + 2dy + dx."""
    c4, h, w = x.shape
    assert c4 % 4 == 0
    c = c4 // 4
    return x.reshape(c, 2, 2, h, w).transpose(0, 3, 1, 4, 2).reshape(c, 2 * h, 2 * w)


def forward_layers(net: QNet, x_chw):
    """x_chw: (3,H+6,W+6) uint8 (halo already attached).  Returns [L1, L2, L3, L4 outputs, shuffled] as int32 arrays."""
    assert x_chw.ndim == 3 and x_chw.shape[0] == 3 and x_chw.dtype == np.uint8
    outs, cur = [], x_chw
    for L in net.layers:
        cur = conv_requant(cur, L["w"], L["b"], L["m"], L["shift"], L["depthwise"])
        outs.append(cur)
    outs.append(pixel_shuffle(cur))
    return outs


def run_tile(net: QNet, tile_hwc):
    """Tile WITH halo: uint8 (h+6, w+6, 3) -> uint8 (2h, 2w, 3).  The 70x70 -> 128x128 hardware case is h = w = 64."""
    x = np.ascontiguousarray(tile_hwc.transpose(2, 0, 1))
    y = forward_layers(net, x)[-1]
    return y.astype(np.uint8).transpose(1, 2, 0)


def pad_replicate(img_hwc, halo=HALO):
    return np.pad(img_hwc, ((halo, halo), (halo, halo), (0, 0)), mode="edge")


def upscale(net: QNet, lr_hwc):
    """Whole image: uint8 RGB (H,W,3) -> uint8 RGB (2H,2W,3).  Replicate-pad by 3, then valid convolutions."""
    return run_tile(net, pad_replicate(lr_hwc))


def upscale_tiled(net: QNet, lr_hwc, core=64):
    """Same result as upscale() but cut into core x core tiles with a 3 px halo (what the FPGA does).
    H and W need not be multiples of core: the padded input is extended with replicated pixels and the output cropped."""
    h, w = lr_hwc.shape[:2]
    ph, pw = -h % core, -w % core
    padded = np.pad(lr_hwc, ((HALO, HALO + ph), (HALO, HALO + pw), (0, 0)), mode="edge")
    out = np.zeros(((h + ph) * 2, (w + pw) * 2, 3), dtype=np.uint8)
    for ty in range(0, h + ph, core):
        for tx in range(0, w + pw, core):
            tile = padded[ty:ty + core + 2 * HALO, tx:tx + core + 2 * HALO]
            out[2 * ty:2 * (ty + core), 2 * tx:2 * (tx + core)] = run_tile(net, tile)
    return out[:2 * h, :2 * w]
