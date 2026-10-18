"""Tests for the ABPN-style anchor variant (software only).  Run from the project root: .venv/bin/python software/ai/quantization/test_anchor.py"""
import copy
import sys
from pathlib import Path

import numpy as np
import torch

ROOT = Path(__file__).resolve().parents[3]
sys.path.insert(0, str(ROOT / "software" / "ai"))
sys.path.insert(0, str(ROOT / "software" / "ai" / "training"))
from evaluation.eval_int8 import qnet_from_arrays  # noqa: E402
from models.srnet import SRNet, predict_full  # noqa: E402
from models.srnet_rep import SRNetRep  # noqa: E402
from quantization.integer_reference import upscale, upscale_tiled  # noqa: E402
from quantization.qat import QATNet, predict  # noqa: E402
from quantization.quantize import quantize  # noqa: E402

fails = 0


def check(name, ok):
    global fails
    fails += not ok
    print(("PASS " if ok else "FAIL ") + name)


def net_random(anchor, seed=0):
    torch.manual_seed(seed)
    n = SRNet(2, 16, anchor)
    for p in n.parameters():
        p.data = torch.randn_like(p) * 0.15
    return n.eval()


rng = np.random.default_rng(1)
img = rng.integers(0, 256, (37, 45, 3), dtype=np.uint8)
crops = [rng.integers(0, 256, (256, 256, 3), dtype=np.uint8) for _ in range(4)]

# 1. zero residual => exact nearest-neighbour upscaling (float model and integer model)
z = SRNet(2, 16, True).eval()
for p in z.parameters():
    p.data.zero_()
nn_up = np.repeat(np.repeat(img, 2, 0), 2, 1)
check("float anchor net with zero weights == nearest-neighbour x2", np.array_equal(predict_full(z, img), nn_up))
arrays, _ = quantize(net_random(True), crops, 99.99, False)
q = qnet_from_arrays(arrays)
for L in q.layers[3:]:
    L["w"][:] = 0; L["b"][:] = 0
check("integer anchor net with zero last layer == nearest-neighbour x2", np.array_equal(upscale(q, img), nn_up))

# 2. QAT simulation == integer model, bit for bit: anchor on/off x per-layer/per-channel scales x plain/re-parameterized network
torch.backends.cudnn.allow_tf32 = False
for anchor in (True, False):
    for per_channel in (False, True):
        for rep in (False, True):
            if rep:
                torch.manual_seed(3)
                repnet = SRNetRep(anchor=anchor)
                for p_ in repnet.parameters():
                    p_.data = torch.randn_like(p_) * 0.15
                net, sim_net = repnet.to_srnet(), repnet
            else:
                net = net_random(anchor, 3)
                sim_net = copy.deepcopy(net)
            arrays, _ = quantize(net, crops, 99.99, per_channel)
            qn = qnet_from_arrays(arrays)
            am = [float(arrays[f"L{i}_s_out"]) * 255.0 for i in (1, 2, 3)]
            sim = QATNet(sim_net, am, per_channel).eval()
            a, b = predict(sim, img, torch.device("cpu")), upscale(qn, img)
            check(f"QAT sim == integer model (anchor={anchor}, per_channel={per_channel}, rep={rep}), {int((a != b).sum())} of {a.size} differ", np.array_equal(a, b))

# 3. the anchor really matters: dropping the add changes the output of the integer model
arrays, _ = quantize(net_random(True, 5), crops, 99.99, False)
with_anchor = upscale(qnet_from_arrays(arrays), img)
arrays.pop("meta_anchor")
without = upscale(qnet_from_arrays(arrays), img)
check("negative control: integer model without the anchor add differs", not np.array_equal(with_anchor, without))

# 4. merge of the re-parameterized anchor net is exact too
m = SRNetRep(anchor=True).double()
for p in m.parameters():
    p.data = torch.randn_like(p) * 0.2
x = torch.rand(1, 3, 21, 25, dtype=torch.double)
ref = m(x)
merged = m.float().to_srnet().double()
check("SRNetRep(anchor) merges exactly into SRNet(anchor)", merged.anchor and (ref - merged(x)).abs().max().item() < 1e-4)
# 5. SEAM TEST of the anchor path: the tile engine adds the centre pixel of the halo-extended input tile, so tiled processing must equal whole-image
#    processing exactly, for tile sizes that do not divide the image, at the image borders, and for the anchor read being aligned to the tile's halo.
arrays, _ = quantize(net_random(True, 7), crops, 99.99, False)
qa = qnet_from_arrays(arrays)
whole = upscale(qa, img)
for core in (8, 16, 64):
    check(f"anchor: tiled (core {core}) == whole image on 37x45, {int((upscale_tiled(qa, img, core) != whole).sum())} bytes differ", np.array_equal(upscale_tiled(qa, img, core), whole))
big = rng.integers(0, 256, (100, 90, 3), dtype=np.uint8)
check("anchor: tiled (core 64, 4 tiles, 100x90) == whole image", np.array_equal(upscale_tiled(qa, big, 64), upscale(qa, big)))
# alignment: with a zero residual the tiled output must be exactly the nearest-neighbour image, tile by tile.  A read shifted by one pixel
# (a classic halo off-by-one) still gives tiled == whole, so this is the check that actually pins the alignment.
for L in qa.layers[3:]:
    L["w"][:] = 0; L["b"][:] = 0
check("anchor alignment: zero residual, tiled (core 8) == nearest-neighbour upscaling", np.array_equal(upscale_tiled(qa, img, 8), np.repeat(np.repeat(img, 2, 0), 2, 1)))
# negative control: a MUTANT of the integer model whose anchor reads the centre pixel one row/column off (halo offset 2 instead of 3)
import quantization.integer_reference as ir  # noqa: E402

orig = ir.forward_layers


def mutant(net, x_chw):
    outs = orig(net, x_chw)
    centre_wrong = x_chw[:, 2:-4, 2:-4].astype(np.int32)  # off by one
    res = outs[3]
    outs[-1] = ir.pixel_shuffle(np.clip(res + np.repeat(centre_wrong, 4, axis=0), 0, 255))
    return outs


ir.forward_layers = mutant
try:
    caught = not np.array_equal(upscale_tiled(qa, img, 8), np.repeat(np.repeat(img, 2, 0), 2, 1))
finally:
    ir.forward_layers = orig
check("negative control: a halo-misaligned anchor read (offset 2 instead of 3) is detected by the alignment test", caught)
# 6. exhaustive: the residual clamp the model uses ([-255,255]) and the natural 9-bit signed hardware clamp ([-256,255]) and NO residual clamp at all
#    give the same final pixel for every residual value and every centre pixel p in 0..255
res = np.arange(-70000, 70001)[:, None]
pix = np.arange(256)[None, :]
fin = lambda lo, hi: np.clip(np.clip(res, lo, hi) + pix, 0, 255)  # noqa: E731
check("exhaustive: residual clamp [-256,255] (9-bit signed) == [-255,255] == no clamp, for all residuals and all 256 pixel values",
      np.array_equal(fin(-256, 255), fin(-255, 255)) and np.array_equal(fin(-256, 255), fin(-10**9, 10**9)))
print("ALL PASS" if not fails else f"{fails} FAILED")
sys.exit(1 if fails else 0)
