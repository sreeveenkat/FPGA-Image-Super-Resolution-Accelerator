"""SRNet x2: the hardware-friendly network (see docs/milestones/M2).

Conv3x3(3->C)+ReLU -> Depthwise3x3(C)+ReLU -> Conv1x1(C->C)+ReLU -> Conv3x3(C->12) -> PixelShuffle(2)

All convolutions are VALID (padding=0): the input must carry a HALO = 3 pixel border on every side, and the output is
exactly 2x the un-padded size. This is how the FPGA tile engine works, so training matches hardware.
Input: float (N,3,H+6,W+6) in [0,1].  Output: (N,3,2H,2W), NOT clamped.
"""
import numpy as np
import torch
import torch.nn as nn
import torch.nn.functional as F

HALO = 3


class SRNet(nn.Module):
    def __init__(self, scale: int = 2, ch: int = 16):
        super().__init__()
        self.scale, self.ch = scale, ch
        self.conv1 = nn.Conv2d(3, ch, 3)
        self.dw = nn.Conv2d(ch, ch, 3, groups=ch)
        self.pw = nn.Conv2d(ch, ch, 1)
        self.conv4 = nn.Conv2d(ch, 3 * scale * scale, 3)
        self.shuffle = nn.PixelShuffle(scale)

    def forward(self, x):
        x = F.relu(self.conv1(x))
        x = F.relu(self.dw(x))
        x = F.relu(self.pw(x))
        return self.shuffle(self.conv4(x))


def count_params(model: nn.Module) -> int:
    return sum(p.numel() for p in model.parameters())


def macs_per_input_pixel(ch: int = 16, scale: int = 2) -> int:
    return 3 * ch * 9 + ch * 9 + ch * ch + ch * 3 * scale * scale * 9


@torch.no_grad()
def predict_full(model: SRNet, lr: np.ndarray) -> np.ndarray:
    """uint8 RGB (H,W,3) -> uint8 RGB (2H,2W,3). Replicate-pads by HALO, runs valid convs, clamps, rounds."""
    model.eval()
    x = torch.from_numpy(np.array(lr)).permute(2, 0, 1).float().div(255).unsqueeze(0)
    x = F.pad(x, (HALO,) * 4, mode="replicate")
    y = model(x).clamp(0, 1).mul(255).round().byte()
    return y[0].permute(1, 2, 0).numpy()
