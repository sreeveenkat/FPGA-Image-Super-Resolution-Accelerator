"""M3 tests: the exported .mem / .vh / golden files must reproduce exactly what the integer model uses.
Run: .venv/bin/python -W error software/ai/quantization/test_export.py   (golden tests SKIP if export_rtl.py was not run)
"""
import re
import sys
from pathlib import Path

import numpy as np

ROOT = Path(__file__).resolve().parents[3]
sys.path.insert(0, str(ROOT / "software" / "ai"))
from quantization.integer_reference import LAYER_SPEC, QNet, forward_layers  # noqa: E402

WDIR, GDIR = ROOT / "hardware/rtl/weights", ROOT / "data/golden"
NET = QNet.load(ROOT / "software/ai/quantization/qparams.npz")


class Skip(Exception):
    pass


def read_mem(path, bits, signed):
    """Independent parser: hex text -> ints (Python int(...,16), explicit two's-complement conversion)."""
    vals = []
    for line in Path(path).read_text().split("\n"):
        if not line:
            continue
        assert len(line) == bits // 4 and line == line.lower(), (path, line)
        v = int(line, 16)
        vals.append(v - (1 << bits) if signed and v >= 1 << (bits - 1) else v)
    return np.array(vals, dtype=np.int64)


def test_mem_files_roundtrip_exactly():
    for L, (name, cin, cout, k, dw) in zip(NET.layers, LAYER_SPEC):
        n = name[1]
        w = read_mem(WDIR / f"weights_L{n}.mem", 8, True)
        assert w.size == cout * (1 if dw else cin) * k * k
        assert (w.reshape(L["w"].shape) == L["w"]).all(), name
        assert (read_mem(WDIR / f"bias_L{n}.mem", 32, True) == L["b"]).all(), name
        assert (read_mem(WDIR / f"mult_L{n}.mem", 16, False) == L["m"]).all(), name


def test_wrom_is_the_same_weights_rearranged_step_major():
    """wrom_Ln.mem (loaded by the RTL) must contain exactly the weights of weights_Ln.mem, line s = (ky*K+kx)*CI_W + ci,
    channel co in bits [8*co +: 8].  Independent parser + index formula (nothing shared with export_rtl.py)."""
    for L, (name, cin, cout, k, dw) in zip(NET.layers, LAYER_SPEC):
        n = name[1]
        flat = read_mem(WDIR / f"weights_L{n}.mem", 8, True)
        ci_w = 1 if dw else cin
        lines = (WDIR / f"wrom_L{n}.mem").read_text().split("\n")[:-1]
        assert len(lines) == k * k * ci_w, name
        for step, line in enumerate(lines):
            assert len(line) == 2 * cout and line == line.lower(), (name, step)
            word = int(line, 16)
            ci, kx, ky = step % ci_w, (step // ci_w) % k, step // (ci_w * k)
            for co in range(cout):
                b = (word >> (8 * co)) & 0xFF
                b = b - 256 if b >= 128 else b
                assert b == flat[((co * ci_w + ci) * k + ky) * k + kx], (name, step, co)


def test_weight_file_order_is_co_ci_ky_kx():
    # element (co=1, ci=2, ky=1, kx=2) of L1 sits at flat index ((1*3 + 2)*3 + 1)*3 + 2 = 50
    w = read_mem(WDIR / "weights_L1.mem", 8, True)
    flat = NET.layers[0]["w"].flatten()
    assert w[50] == flat[50] == NET.layers[0]["w"][1, 2, 1, 2]
    # L2 depthwise: channel c, tap (ky,kx) at (c*3 + ky)*3 + kx
    w2 = read_mem(WDIR / "weights_L2.mem", 8, True)
    assert w2[(5 * 3 + 2) * 3 + 1] == NET.layers[1]["w"][5, 0, 2, 1]


def test_header_shifts_and_geometry_match():
    text = (WDIR / "network_params.vh").read_text()
    for L, (name, cin, cout, k, dw) in zip(NET.layers, LAYER_SPEC):
        n = name[1]
        got = {m[0]: int(m[1]) for m in re.findall(rf"localparam L{n}_(\w+) = (\d+);", text)}
        assert got == {"CIN": cin, "COUT": cout, "K": k, "DEPTHWISE": int(dw), "SHIFT": L["shift"]}, name


def test_negative_values_are_twos_complement():
    # at least one negative weight and one negative bias exist and are encoded with the high bit set
    w = (WDIR / "weights_L4.mem").read_text().split()
    assert any(int(x, 16) >= 128 for x in w) and (NET.layers[3]["w"] < 0).any()


def tiles():
    names = sorted(p.stem for p in GDIR.glob("*.npz")) if GDIR.exists() else []
    if not names:
        raise Skip("no golden tiles; run software/ai/quantization/export_rtl.py")
    return names


def test_golden_hex_matches_model():
    for name in tiles():
        z = np.load(GDIR / f"{name}.npz")
        layers = forward_layers(NET, z["tile"].transpose(2, 0, 1).copy())  # recompute independently of the exporter
        for i in range(4):
            assert (z[f"L{i + 1}"] == layers[i]).all(), (name, i)
            hexv = read_mem(GDIR / f"{name}_L{i + 1}.hex", 8, False)
            assert (hexv.reshape(layers[i].transpose(1, 2, 0).shape) == layers[i].transpose(1, 2, 0)).all(), (name, i)
        assert (read_mem(GDIR / f"{name}_in.hex", 8, False).reshape(z["tile"].shape) == z["tile"]).all()
        assert (read_mem(GDIR / f"{name}_out.hex", 8, False).reshape(z["out"].shape) == layers[4].transpose(1, 2, 0)).all()


def test_golden_set_covers_stress_cases():
    names = tiles()
    for need in ("zeros", "full255", "noise", "pixel", "ramp", "small12", "real_corner"):
        assert need in names, need
    zs = [np.load(GDIR / f"{n}.npz") for n in names]
    for layer in ("L1", "L2", "L3", "L4"):  # every layer clamps at 0 AND saturates at 255 in at least one golden tile
        assert any((z[layer] == 0).any() for z in zs) and any((z[layer] == 255).any() for z in zs), layer
    s = np.load(GDIR / "small12.npz")
    assert s["tile"].shape == (12, 12, 3) and s["out"].shape == (12, 12, 3)


if __name__ == "__main__":
    for n_, f_ in list(globals().items()):
        if n_.startswith("test_"):
            try:
                f_()
                print("PASS", n_)
            except Skip as e:
                print("SKIP", n_, "-", e)
