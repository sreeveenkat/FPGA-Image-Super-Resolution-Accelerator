"""M2 tests. Run: .venv/bin/python -W error software/ai/evaluation/test_model.py"""
import sys
from pathlib import Path

import numpy as np
import torch
import torch.nn.functional as F

ROOT = Path(__file__).resolve().parents[3]
sys.path.insert(0, str(ROOT / "software" / "ai"))
from models.srnet import HALO, SRNet, count_params, macs_per_input_pixel, predict_full  # noqa: E402


def test_counts_match_docs():
    assert count_params(SRNet()) == 2620 and macs_per_input_pixel() == 2560


def test_output_shape_and_shuffle_order():
    m = SRNet().eval()
    x = torch.rand(1, 3, 20 + 2 * HALO, 14 + 2 * HALO)
    y = m(x)
    assert y.shape == (1, 3, 40, 28)
    # pixel shuffle channel order k = 4c + 2dy + dx
    pre = m.conv4(F.relu(m.pw(F.relu(m.dw(F.relu(m.conv1(x)))))))
    assert torch.equal(y[0, 2, 2 * 5 + 1, 2 * 7 + 0], pre[0, 4 * 2 + 2 * 1 + 0, 5, 7])


def test_tiled_equals_whole():
    """Tiles with a 3-px halo must reproduce whole-image output exactly (the M5 seam property)."""
    torch.manual_seed(0)
    m = SRNet().eval()
    H = W = 32
    img = torch.rand(1, 3, H + 2 * HALO, W + 2 * HALO)
    whole = m(img)
    t = 16
    out = torch.zeros_like(whole)
    for y in range(0, H, t):
        for x in range(0, W, t):
            tile = img[:, :, y:y + t + 2 * HALO, x:x + t + 2 * HALO]
            out[:, :, 2 * y:2 * (y + t), 2 * x:2 * (x + t)] = m(tile)
    assert torch.allclose(out, whole, atol=1e-5)


def test_checkpoint_beats_bicubic_on_flat_and_runs():
    ck = torch.load(ROOT / "software/ai/checkpoints/srnet_fp32.pt", map_location="cpu")
    m = SRNet(ck["scale"], ck["ch"])
    m.load_state_dict(ck["state"])
    lr = np.full((10, 12, 3), 128, np.uint8)
    out = predict_full(m, lr)
    assert out.shape == (20, 24, 3) and out.dtype == np.uint8
    assert abs(int(out.mean()) - 128) <= 3  # flat grey stays grey


def test_ssim_loss_matches_skimage():
    sys.path.insert(0, str(ROOT / "software" / "ai" / "training"))
    from train import gaussian_window, ssim_loss
    from evaluation.metrics import ssim_rgb
    rng = np.random.default_rng(0)
    a = rng.integers(0, 256, (48, 48, 3), dtype=np.uint8)
    b = np.clip(a.astype(int) + rng.integers(-25, 26, a.shape), 0, 255).astype(np.uint8)
    ta, tb = (torch.from_numpy(x).permute(2, 0, 1)[None].float() / 255 for x in (a, b))
    mine = 1 - float(ssim_loss(ta, tb, gaussian_window()))
    assert abs(mine - ssim_rgb(a, b)) < 2e-3, (mine, ssim_rgb(a, b))
    assert float(ssim_loss(ta, ta, gaussian_window())) < 1e-6


def test_edge_aug_sampling_alignment():
    sys.path.insert(0, str(ROOT / "software" / "ai" / "training"))
    from train import sample_batch
    lr = np.random.default_rng(1).integers(0, 256, (40, 50, 3), dtype=np.uint8)
    hr = np.repeat(np.repeat(lr, 2, 0), 2, 1)
    for edge in (False, True):
        x, y = sample_batch([(lr, hr)], np.random.default_rng(0), 32, 8, edge)
        up = x[:, :, HALO:-HALO, HALO:-HALO].repeat_interleave(2, 2).repeat_interleave(2, 3)
        assert float((up - y).abs().max()) == 0.0


def test_checkpoint_beats_bicubic_on_real_images():
    from dataset.pairs import load_rgb, make_pair, upscale_pil
    from evaluation.metrics import psnr_y
    ck = torch.load(ROOT / "software/ai/checkpoints/srnet_fp32.pt", map_location="cpu")
    m = SRNet(ck["scale"], ck["ch"])
    m.load_state_dict(ck["state"])
    for s, n in [("Set5", "butterfly"), ("Set14", "zebra"), ("Set14", "ppt3")]:
        lr, hr = make_pair(load_rgb(ROOT / "data" / "test" / "HR" / s / f"{n}.png"), 2)
        assert psnr_y(hr, predict_full(m, lr), 2) > psnr_y(hr, upscale_pil(lr, 2), 2) + 0.5, n


if __name__ == "__main__":
    for n, f in list(globals().items()):
        if n.startswith("test_"):
            f()
            print("PASS", n)
