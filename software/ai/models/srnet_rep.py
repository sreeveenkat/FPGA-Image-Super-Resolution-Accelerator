"""Re-parameterized training version of SRNet (ECBSR / RepVGG style).

Training uses multi-branch blocks; after training every block is merged EXACTLY into the single convolution the hardware has, so the
deployed network is the plain `SRNet` (same layer shapes, same 2,620 parameters, same RTL). All convolutions are VALID, so the merges
are exact (no padding corner cases); `merge()` is checked numerically in `software/ai/models/test_rep.py`.

Blocks
  ECB  (L1 3->16 and L4 16->12, merged to a 3x3 conv):
        branch 1  conv3x3
        branch 2  conv1x1 (cin->mid) -> conv3x3 (mid->cout)                      [mid = expand * cout]
        branch 3-5 conv1x1 (cin->cout) -> fixed depthwise Sobel-x / Sobel-y / Laplacian x learnable per-channel scale + bias
        (the fixed filters sum to 0, so the 1x1 bias would cancel; the 1x1 convs have no bias.)
  DWRep (L2 depthwise 3x3, merged to a depthwise 3x3):  dw3x3 + dw1x1 + identity   (RepVGG)
  PWRep (L3 1x1, merged to a 1x1):                      conv1x1 + identity
"""
import torch
import torch.nn as nn
import torch.nn.functional as F

from models.srnet import HALO, SRNet

_SOBEL_X = [[1.0, 0.0, -1.0], [2.0, 0.0, -2.0], [1.0, 0.0, -1.0]]
_SOBEL_Y = [[1.0, 2.0, 1.0], [0.0, 0.0, 0.0], [-1.0, -2.0, -1.0]]
_LAPLACE = [[0.0, 1.0, 0.0], [1.0, -4.0, 1.0], [0.0, 1.0, 0.0]]


class ECB(nn.Module):
    def __init__(self, cin, cout, expand=2.0, edge=True):
        super().__init__()
        self.cin, self.cout, self.edge = cin, cout, edge
        mid = max(1, int(round(cout * expand)))
        self.conv3 = nn.Conv2d(cin, cout, 3)
        self.exp = nn.Conv2d(cin, mid, 1)
        self.sq = nn.Conv2d(mid, cout, 3)
        if edge:
            self.edge_in = nn.ModuleList([nn.Conv2d(cin, cout, 1, bias=False) for _ in range(3)])
            self.scale = nn.ParameterList([nn.Parameter(torch.full((cout,), 1e-2)) for _ in range(3)])
            self.ebias = nn.ParameterList([nn.Parameter(torch.zeros(cout)) for _ in range(3)])
            filt = torch.tensor([_SOBEL_X, _SOBEL_Y, _LAPLACE])  # (3,3,3)
            self.register_buffer("filt", filt)

    def forward(self, x):
        y = self.conv3(x) + self.sq(self.exp(x))
        if self.edge:
            for i in range(3):
                t = self.edge_in[i](x)
                k = self.filt[i].expand(self.cout, 1, 3, 3).contiguous()
                y = y + F.conv2d(t, k, groups=self.cout) * self.scale[i].view(1, -1, 1, 1) + self.ebias[i].view(1, -1, 1, 1)
        return y

    def merged_t(self):
        """Differentiable merge (model dtype): the deployed 3x3 weight and bias as functions of the branch parameters."""
        w1 = self.exp.weight[:, :, 0, 0]
        w = self.conv3.weight + torch.einsum("omyx,mc->ocyx", self.sq.weight, w1)
        b = self.conv3.bias + self.sq.bias + torch.einsum("omyx,m->o", self.sq.weight, self.exp.bias)
        if self.edge:
            for i in range(3):
                w = w + torch.einsum("o,yx,oc->ocyx", self.scale[i], self.filt[i], self.edge_in[i].weight[:, :, 0, 0])
                b = b + self.ebias[i]
        return w, b

    @torch.no_grad()
    def merged(self):
        w = self.conv3.weight.clone().double()
        b = self.conv3.bias.clone().double()
        # branch 2: W[o,c,k] = sum_m W2[o,m,k] W1[m,c];  b += sum_{m,k} W2[o,m,k] b1[m] + b2[o]
        w1 = self.exp.weight.double()[:, :, 0, 0]  # (mid,cin)
        w2 = self.sq.weight.double()  # (cout,mid,3,3)
        w = w + torch.einsum("omyx,mc->ocyx", w2, w1)
        b = b + self.sq.bias.double() + torch.einsum("omyx,m->o", w2, self.exp.bias.double())
        if self.edge:
            for i in range(3):
                w1e = self.edge_in[i].weight.double()[:, :, 0, 0]  # (cout,cin)
                s = self.scale[i].double()
                w = w + torch.einsum("o,yx,oc->ocyx", s, self.filt[i].double(), w1e)
                b = b + self.ebias[i].double()
        return w.float(), b.float()


class DWRep(nn.Module):
    def __init__(self, ch):
        super().__init__()
        self.dw3 = nn.Conv2d(ch, ch, 3, groups=ch)
        self.dw1 = nn.Conv2d(ch, ch, 1, groups=ch, bias=False)

    def forward(self, x):
        c = x[:, :, 1:-1, 1:-1]  # centre of the 3x3 window (valid conv shrinks by 1 px on every side)
        return self.dw3(x) + self.dw1(c) + c

    def merged_t(self):
        w = self.dw3.weight + F.pad(self.dw1.weight + 1.0, (1, 1, 1, 1))  # 1x1 taps + identity land on the centre tap
        return w, self.dw3.bias

    @torch.no_grad()
    def merged(self):
        w, b = self.merged_t()
        return w.clone(), b.clone()


class PWRep(nn.Module):
    def __init__(self, ch):
        super().__init__()
        self.pw = nn.Conv2d(ch, ch, 1)

    def forward(self, x):
        return self.pw(x) + x

    def merged_t(self):
        return self.pw.weight + torch.eye(self.pw.weight.shape[0], device=self.pw.weight.device).view(*self.pw.weight.shape[:2], 1, 1), self.pw.bias

    @torch.no_grad()
    def merged(self):
        w, b = self.merged_t()
        return w.clone(), b.clone()


class SRNetRep(nn.Module):
    """Same data flow as SRNet. `rep` selects which layers use multi-branch blocks (subset of {"l1","l2","l3","l4"})."""

    def __init__(self, scale=2, ch=16, rep=("l1", "l2", "l3", "l4"), expand=2.0, edge=True, anchor=False):
        super().__init__()
        self.scale, self.ch, self.rep, self.anchor = scale, ch, tuple(rep), anchor
        out = 3 * scale * scale
        self.conv1 = ECB(3, ch, expand, edge) if "l1" in rep else nn.Conv2d(3, ch, 3)
        self.dw = DWRep(ch) if "l2" in rep else nn.Conv2d(ch, ch, 3, groups=ch)
        self.pw = PWRep(ch) if "l3" in rep else nn.Conv2d(ch, ch, 1)
        self.conv4 = ECB(ch, out, expand, edge) if "l4" in rep else nn.Conv2d(ch, out, 3)
        self.shuffle = nn.PixelShuffle(scale)

    def forward(self, x):
        inp = x
        x = F.relu(self.conv1(x))
        x = F.relu(self.dw(x))
        x = F.relu(self.pw(x))
        out = self.conv4(x)
        if self.anchor:
            out = out + inp[:, :, HALO:-HALO, HALO:-HALO].repeat_interleave(self.scale * self.scale, dim=1)
        return self.shuffle(out)

    def layer_wb(self):
        """[(weight, bias, groups)] of the four deployed layers; differentiable w.r.t. the branch parameters."""
        out = []
        for name, groups in (("conv1", 1), ("dw", self.ch), ("pw", 1), ("conv4", 1)):
            mod = getattr(self, name)
            w, b = mod.merged_t() if hasattr(mod, "merged_t") else (mod.weight, mod.bias)
            out.append((w, b, groups))
        return out

    def forward_merged(self, x):
        """Same function as forward(), computed with the merged weights (ONE convolution per layer: ~5x cheaper than the branches)."""
        (w1, b1, _), (w2, b2, g2), (w3, b3, _), (w4, b4, _) = self.layer_wb()
        h = F.relu(F.conv2d(x, w1, b1))
        h = F.relu(F.conv2d(h, w2, b2, groups=g2))
        h = F.relu(F.conv2d(h, w3, b3))
        out = F.conv2d(h, w4, b4)
        if self.anchor:
            out = out + x[:, :, HALO:-HALO, HALO:-HALO].repeat_interleave(self.scale * self.scale, dim=1)
        return self.shuffle(out)

    @torch.no_grad()
    def to_srnet(self) -> SRNet:
        """Merge every multi-branch block; returns the plain deployable SRNet (float32)."""
        net = SRNet(self.scale, self.ch, self.anchor)
        for name in ("conv1", "dw", "pw", "conv4"):
            mod = getattr(self, name)
            tgt = getattr(net, name)
            if hasattr(mod, "merged"):
                w, b = mod.merged()
            else:
                w, b = mod.weight.clone(), mod.bias.clone()
            assert w.shape == tgt.weight.shape, (name, w.shape, tgt.weight.shape)
            tgt.weight.copy_(w)
            tgt.bias.copy_(b)
        return net.eval()
