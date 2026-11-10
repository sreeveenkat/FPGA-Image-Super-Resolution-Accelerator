"""Teacher network for knowledge distillation (2026-11-10). NOT deployable: it only produces training targets for the 2,620-parameter SRNet.

64 channels, 10 3x3 convolutions (head, 8 body, tail) with 'same' padding, global residual over the body, PixelShuffle x2 and the same
ABPN-style nearest-neighbour anchor as SRNet(anchor=True). Receptive-field radius = 10 LR pixels, so a training window with a halo of
TEACHER_HALO = 11 px around the core gives every core output pixel its full context (zero padding never reaches the core).
"""
import torch
import torch.nn as nn
import torch.nn.functional as F

TEACHER_HALO = 11


class Teacher(nn.Module):
    def __init__(self, scale: int = 2, ch: int = 64, body: int = 8):
        super().__init__()
        self.scale = scale
        self.head = nn.Conv2d(3, ch, 3, padding=1)
        layers = []
        for _ in range(body):
            layers += [nn.Conv2d(ch, ch, 3, padding=1), nn.ReLU(inplace=True)]
        self.body = nn.Sequential(*layers)
        self.tail = nn.Conv2d(ch, 3 * scale * scale, 3, padding=1)

    def forward(self, x: torch.Tensor) -> torch.Tensor:
        """x: (N, 3, H, W) in [0, 1] -> (N, 3, 2H, 2W) ('same' size, x2)."""
        f = F.relu(self.head(x))
        f = self.body(f) + f
        r = self.tail(f) + x.repeat_interleave(self.scale * self.scale, dim=1)   # nearest-neighbour anchor, channel k = 4c + 2dy + dx
        return F.pixel_shuffle(r, self.scale)

    def core(self, x: torch.Tensor, halo: int, p: int) -> torch.Tensor:
        """Output for the p x p LR core of a window with `halo` px on each side: the centre 2p x 2p of the x2 output."""
        y = self.forward(x)
        o = halo * self.scale
        return y[:, :, o:o + p * self.scale, o:o + p * self.scale]


def count_params(m: nn.Module) -> int:
    return sum(p.numel() for p in m.parameters())
