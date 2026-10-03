"""M3 tests for the integer model and the exported parameters.
Run: .venv/bin/python -W error software/ai/quantization/test_integer.py
"""
import sys
from pathlib import Path

import numpy as np
import torch
import torch.nn.functional as F

ROOT = Path(__file__).resolve().parents[3]
sys.path.insert(0, str(ROOT / "software" / "ai"))
from quantization.integer_reference import (LAYER_SPEC, QNet, conv_requant, forward_layers, pad_replicate, pixel_shuffle,  # noqa: E402
                                            requant, run_tile, upscale, upscale_tiled)

QPARAMS = ROOT / "software/ai/quantization/qparams.npz"


class Skip(Exception):
    pass


def need(path):
    if not Path(path).exists():
        raise Skip(f"missing {Path(path).relative_to(ROOT)}")


def i8(*shape, rng, lo=-128, hi=127):
    return rng.integers(lo, hi + 1, size=shape).astype(np.int8)


def naive_conv(x, w, b, m, shift, depthwise):
    """Literal 6-nested-loop version of the arithmetic in the module docstring (Python ints, no numpy tricks)."""
    k = w.shape[2]
    c_out, h, wd = w.shape[0], x.shape[1] - k + 1, x.shape[2] - k + 1
    out = np.zeros((c_out, h, wd), dtype=np.int32)
    for co in range(c_out):
        cis = [co] if depthwise else range(x.shape[0])
        for y in range(h):
            for xx in range(wd):
                acc = int(b[co])
                for ci in cis:
                    for ky in range(k):
                        for kx in range(k):
                            acc += int(x[ci, y + ky, xx + kx]) * int(w[co, 0 if depthwise else ci, ky, kx])
                v = (acc * int(m[co]) + (1 << (shift - 1))) >> shift
                out[co, y, xx] = min(max(v, 0), 255)
    return out


# ------------------------------------------------------------------------------------------------ hand-computed cases
def test_requant_rounding_ties_and_clamp():
    # M=1, SHIFT=2 -> y = (acc + 2) >> 2 = round-half-up(acc / 4)
    acc = np.array([0, 1, 2, 3, 5, 6, 7, 10, -1, -2, -6, 1019, 1020, 1021, 100000]).reshape(1, 1, -1).astype(np.int64)
    got = requant(acc, np.array([1]), 2)[0, 0]
    assert got.tolist() == [0, 0, 1, 1, 1, 2, 2, 3, 0, 0, 0, 255, 255, 255, 255], got.tolist()
    # 2.5 -> 3 (half UP, not banker's rounding), 1.5 -> 2, 0.5 -> 1
    assert requant(np.array([[[2, 6, 10]]], dtype=np.int64), np.array([1]), 2)[0, 0].tolist() == [1, 2, 3]


def test_requant_multiplier_and_shift_arithmetic():
    # 1000 * 3 / 2**4 = 187.5 -> 188 ; 1001*3/16 = 187.69 -> 188 ; 999*3/16 = 187.31 -> 187
    got = requant(np.array([[[1000, 1001, 999]]], dtype=np.int64), np.array([3]), 4)[0, 0].tolist()
    assert got == [188, 188, 187], got
    # per-channel multipliers are applied to the right channel
    acc = np.full((2, 1, 1), 64, dtype=np.int64)
    assert requant(acc, np.array([1, 3]), 4)[:, 0, 0].tolist() == [4, 12]


def test_zero_input_gives_bias_only():
    w = np.zeros((2, 1, 3, 3), dtype=np.int8)
    b = np.array([40, -40], dtype=np.int32)
    out = conv_requant(np.zeros((2, 5, 5), dtype=np.uint8), w, b, np.array([1, 1]), 1, depthwise=True)
    assert (out[0] == 20).all() and (out[1] == 0).all()  # 40/2 = 20 ; -20 clamped by ReLU


def test_kernel_orientation_single_pixel():
    # one bright pixel at input (3,4); a weight of 1 at tap (ky,kx) sends it to output (3-ky, 4-kx)  (correlation, like PyTorch)
    for ky, kx in [(0, 0), (0, 2), (1, 1), (2, 0), (2, 1)]:
        x = np.zeros((1, 7, 7), dtype=np.uint8)
        x[0, 3, 4] = 100
        w = np.zeros((1, 1, 3, 3), dtype=np.int8)
        w[0, 0, ky, kx] = 1
        out = conv_requant(x, w, np.zeros(1, np.int32), np.array([1]), 1, depthwise=False)
        # M=1, SHIFT=1 halves: 100 -> 50
        assert out.shape == (1, 5, 5)
        ys, xs = np.nonzero(out[0])
        assert (ys.tolist(), xs.tolist()) == ([3 - ky], [4 - kx]) and out[0, 3 - ky, 4 - kx] == 50, (ky, kx)


def test_channel_mixing_pointwise_vs_depthwise():
    x = np.zeros((3, 4, 4), dtype=np.uint8)
    x[1] = 10
    w = np.zeros((3, 3, 1, 1), dtype=np.int8)
    w[2, 1, 0, 0] = 2  # output channel 2 reads input channel 1
    out = conv_requant(x, w, np.zeros(3, np.int32), np.array([1, 1, 1]), 0 + 1, depthwise=False)
    assert (out[2] == 10).all() and (out[0] == 0).all() and (out[1] == 0).all()
    # depthwise: channel c only sees its own input
    wd = np.zeros((3, 1, 3, 3), dtype=np.int8)
    wd[:, 0, 1, 1] = 2
    o = conv_requant(np.stack([np.full((5, 5), v, np.uint8) for v in (10, 20, 30)]), wd, np.zeros(3, np.int32), np.array([1] * 3), 1, True)
    assert [int(o[c, 0, 0]) for c in range(3)] == [10, 20, 30]


def test_extreme_values_no_overflow():
    # worst case of the largest layer: 144 products of 255 * 127 plus a big bias, then M = 65535
    x = np.full((16, 5, 5), 255, dtype=np.uint8)
    w = np.full((1, 16, 3, 3), 127, dtype=np.int8)
    acc = 144 * 255 * 127
    out = conv_requant(x, w, np.array([2 ** 31 - 1 - acc], np.int32), np.array([65535]), 38, False)
    assert out[0, 0, 0] == 255  # (2**31-1)*65535 >> 38 = 512 -> saturates
    wn = np.full((1, 16, 3, 3), -128, dtype=np.int8)
    assert conv_requant(x, wn, np.array([0], np.int32), np.array([65535]), 1, False)[0, 0, 0] == 0  # -4.7M * M -> clamp 0, no wrap
    # exact value at the top of the range: acc = 255*2**3 ... choose M=1, SHIFT=3 -> y = round(acc/8)
    x1 = np.full((1, 3, 3), 255, dtype=np.uint8)
    w1 = np.full((1, 1, 3, 3), -128, dtype=np.int8)
    out = conv_requant(x1, w1, np.array([9 * 255 * 128 + 1000], np.int32), np.array([1]), 3, False)
    assert out[0, 0, 0] == 125  # (1000 + 4) >> 3


def test_pixel_shuffle_exact_mapping():
    x = np.arange(12 * 3 * 5).reshape(12, 3, 5)
    y = pixel_shuffle(x)
    assert y.shape == (3, 6, 10)
    for c in range(3):
        for dy in range(2):
            for dx in range(2):
                for yy in range(3):
                    for xx in range(5):
                        assert y[c, 2 * yy + dy, 2 * xx + dx] == x[4 * c + 2 * dy + dx, yy, xx]


def test_pixel_shuffle_matches_torch():
    x = np.random.default_rng(1).integers(0, 256, (12, 4, 6))
    ref = torch.nn.PixelShuffle(2)(torch.from_numpy(x).unsqueeze(0))[0].numpy()
    assert (pixel_shuffle(x) == ref).all()


# ------------------------------------------------------------------------------------------------ fast vs literal
def test_fast_conv_equals_literal_loops_random():
    rng = np.random.default_rng(2)
    for cin, cout, k, dw in [(3, 4, 3, False), (4, 4, 3, True), (4, 5, 1, False)]:
        x = rng.integers(0, 256, (cin, 7, 8)).astype(np.uint8)
        w = i8(cout, 1 if dw else cin, k, k, rng=rng)
        b = rng.integers(-5000, 5000, cout).astype(np.int32)
        m = rng.integers(1, 65536, cout)
        for shift in (8, 15, 20):
            assert (conv_requant(x, w, b, m, shift, dw) == naive_conv(x, w, b, m, shift, dw)).all(), (cin, cout, k, dw, shift)


# ------------------------------------------------------------------------------------------------ exported parameters
def net():
    need(QPARAMS)
    return QNet.load(QPARAMS)


def test_params_shapes_dtypes_and_count():
    n = net()
    assert [L["name"] for L in n.layers] == ["L1", "L2", "L3", "L4"]
    total = 0
    for L, (name, cin, cout, k, dw) in zip(n.layers, LAYER_SPEC):
        assert L["w"].shape == (cout, 1 if dw else cin, k, k) and L["w"].dtype == np.int8
        assert L["b"].shape == (cout,) and L["b"].dtype == np.int32 and L["m"].shape == (cout,)
        assert int(L["w"].min()) >= -127 and int(L["w"].max()) <= 127  # symmetric range
        total += L["w"].size + L["b"].size
    assert total == 2620  # same parameter count as the FP32 model


def test_accumulator_and_product_bounds_fit_hardware():
    n = net()
    for L in n.layers:
        # worst case |acc| = 255 * sum|w| (per output channel) + |bias|
        worst = 255 * np.abs(L["w"].astype(np.int64)).reshape(L["w"].shape[0], -1).sum(axis=1) + np.abs(L["b"].astype(np.int64))
        assert worst.max() < 2 ** 31, (L["name"], int(worst.max()))
        assert int((worst * L["m"]).max()) < 2 ** 63  # python/int64 model is exact
        assert int((worst.max() * L["m"].max())).bit_length() <= 42, "product acc*M should fit ~40 bits"


def test_multiplier_approximates_real_scale():
    need(QPARAMS)
    z = np.load(QPARAMS)
    for name, *_ in LAYER_SPEC:
        real = z[f"{name}_s_in"] * z[f"{name}_s_w"] / z[f"{name}_s_out"]
        approx = z[f"{name}_m"].astype(np.float64) / 2.0 ** int(z[f"{name}_shift"])
        assert np.max(np.abs(approx - real) / real) < 1e-4, name
    assert float(z["L1_s_in"]) == 1.0 / 255 and float(z["L4_s_out"]) == 1.0 / 255  # exact input and output scales


# ------------------------------------------------------------------------------------------------ whole network
def synth_img(h, w, seed):
    rng = np.random.default_rng(seed)
    base = rng.integers(0, 256, (h // 4 + 1, w // 4 + 1, 3)).astype(np.uint8)
    return np.kron(base, np.ones((4, 4, 1), dtype=np.uint8))[:h, :w]


def test_output_shapes_dtypes_tile_70_to_128():
    n = net()
    tile = np.random.default_rng(3).integers(0, 256, (70, 70, 3)).astype(np.uint8)
    out = run_tile(n, tile)
    assert out.shape == (128, 128, 3) and out.dtype == np.uint8
    layers = forward_layers(n, tile.transpose(2, 0, 1).copy())
    assert [a.shape for a in layers] == [(16, 68, 68), (16, 66, 66), (16, 66, 66), (12, 64, 64), (3, 128, 128)]
    assert all(0 <= int(a.min()) and int(a.max()) <= 255 for a in layers)
    assert (layers[-1].astype(np.uint8).transpose(1, 2, 0) == out).all()


def test_tiled_equals_whole_exactly_synthetic():
    n = net()
    for h, w in [(64, 64), (100, 90), (129, 65)]:
        img = synth_img(h, w, h * w)
        assert (upscale(n, img) == upscale_tiled(n, img, 64)).all(), (h, w)
    assert (upscale(n, synth_img(40, 50, 9)) == upscale_tiled(n, synth_img(40, 50, 9), 16)).all()  # small core, many seams


def test_tiled_equals_whole_exactly_real_image():
    need(ROOT / "data/test/HR/Set14/zebra.png")
    from dataset.pairs import load_rgb, make_pair
    lr, _ = make_pair(load_rgb(ROOT / "data/test/HR/Set14/zebra.png"), 2)
    n = net()
    assert (upscale(n, lr) == upscale_tiled(n, lr, 64)).all()


def test_replicate_padding_is_used():
    n = net()
    img = synth_img(20, 24, 5)
    a = upscale(n, img)
    b = run_tile(n, np.pad(img, ((3, 3), (3, 3), (0, 0)), mode="edge"))
    z = run_tile(n, np.pad(img, ((3, 3), (3, 3), (0, 0)), mode="constant"))
    assert (a == b).all() and (a != z).any()
    assert (pad_replicate(img)[0, 3:-3] == img[0]).all()


def test_flat_image_gives_2x2_periodic_output():
    n = net()
    out = upscale(n, np.full((12, 12, 3), 90, dtype=np.uint8))
    for dy in range(2):
        for dx in range(2):
            assert (out[dy::2, dx::2] == out[dy, dx]).all()  # every low-res pixel is identical -> same 2x2 pattern everywhere


def test_layerwise_matches_independent_float64_torch_with_real_scales():
    """Independent implementation (torch conv2d in float64 on exact integers + exact real multiplier) must agree with the integer
    model layer by layer within +-1, and equal it almost everywhere (differences only where the 16-bit M approximation flips a tie)."""
    need(QPARAMS)
    n, z = net(), np.load(QPARAMS)
    x = pad_replicate(synth_img(60, 70, 11)).transpose(2, 0, 1).copy()
    cur = x
    total = diff = 0
    for L, (name, cin, cout, k, dw) in zip(n.layers, LAYER_SPEC):
        acc = F.conv2d(torch.from_numpy(cur.astype(np.float64)).unsqueeze(0), torch.from_numpy(L["w"].astype(np.float64)),
                       torch.from_numpy(L["b"].astype(np.float64)), groups=cout if dw else 1)[0].numpy()
        real = (z[f"{name}_s_in"] * z[f"{name}_s_w"] / z[f"{name}_s_out"])[:, None, None]
        ref = np.clip(np.floor(acc * real + 0.5), 0, 255).astype(np.int32)
        got = conv_requant(cur, L["w"], L["b"], L["m"], L["shift"], dw)
        d = np.abs(got - ref)
        assert d.max() <= 1, (name, int(d.max()))
        total, diff = total + d.size, diff + int((d > 0).sum())
        cur = got  # feed the integer model's own output forward so errors do not compound
    assert diff / total < 0.01, diff / total


def test_integer_model_close_to_fp32_on_real_image():
    need(ROOT / "data/test/HR/Set5/butterfly.png")
    from dataset.pairs import load_rgb, make_pair
    from evaluation.metrics import psnr_y
    from models.srnet import predict_full
    from quantization.quantize import load_fp32
    lr, hr = make_pair(load_rgb(ROOT / "data/test/HR/Set5/butterfly.png"), 2)
    q, f = upscale(net(), lr), predict_full(load_fp32(), lr)
    assert psnr_y(f, q, 2) > 42, psnr_y(f, q, 2)  # int8 output stays very close to FP32 output
    assert abs(psnr_y(hr, f, 2) - psnr_y(hr, q, 2)) < 0.6


def test_qparams_built_from_current_fp32_checkpoint():
    import hashlib
    ck = ROOT / "software/ai/checkpoints/srnet_fp32.pt"
    need(ck)
    assert str(np.load(QPARAMS)["meta_ckpt_sha256_prefix"]) == hashlib.sha256(ck.read_bytes()).hexdigest()[:16]  # re-run quantize.py if this fails


def test_deterministic():
    n = net()
    img = synth_img(30, 30, 1)
    assert (upscale(n, img) == upscale(QNet.load(QPARAMS), img)).all()


if __name__ == "__main__":
    for n_, f_ in list(globals().items()):
        if n_.startswith("test_"):
            try:
                f_()
                print("PASS", n_)
            except Skip as e:
                print("SKIP", n_, "-", e)
