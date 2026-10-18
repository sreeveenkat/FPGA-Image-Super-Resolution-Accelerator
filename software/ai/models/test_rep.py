"""Tests: every re-parameterized block merges EXACTLY into the plain SRNet (valid convs). Run from the project root:
   .venv/bin/python software/ai/models/test_rep.py"""
import itertools
import sys
from pathlib import Path

import torch

ROOT = Path(__file__).resolve().parents[3]
sys.path.insert(0, str(ROOT / "software" / "ai"))
from models.srnet import SRNet, count_params  # noqa: E402
from models.srnet_rep import SRNetRep  # noqa: E402


def randomize(m):
    for p in m.parameters():  # every branch parameter non-trivial (scales/biases too), otherwise a broken merge could pass
        p.data = torch.randn_like(p) * 0.3


def main():
    torch.manual_seed(0)
    fails = 0
    for rep in [("l1", "l2", "l3", "l4"), ("l1",), ("l2",), ("l3",), ("l4",), ()]:
        for edge in (True, False):
            m = SRNetRep(rep=rep, edge=edge).double()
            randomize(m)
            x = torch.rand(2, 3, 23, 31, dtype=torch.double)
            ref = m(x)
            err_fast = (ref - m.forward_merged(x)).abs().max().item()
            net = m.float().to_srnet().double()
            out = net(x)
            err = max((ref - out).abs().max().item(), err_fast)
            ok = err < 1e-4 and count_params(net) == 2620 and ref.shape == out.shape
            fails += not ok
            print(f"rep={','.join(rep) or '-':<12} edge={edge!s:<5} max|diff|={err:.2e} params={count_params(net)} {'PASS' if ok else 'FAIL'}")
    # negative control: a wrong merge must be detected
    m = SRNetRep().double(); randomize(m)
    x = torch.rand(1, 3, 17, 17, dtype=torch.double)
    net = m.float().to_srnet().double()
    m = m.double()  # .float() above converted m in place
    net.dw.weight.data[:, 0, 1, 1] -= 1.0  # forget the identity branch
    bad = (m(x) - net(x)).abs().max().item()
    print(f"negative control (identity forgotten): diff {bad:.2e} -> {'detected' if bad > 1e-2 else 'NOT DETECTED'}")
    fails += bad <= 1e-2
    print("ALL PASS" if fails == 0 else f"{fails} FAILED")
    sys.exit(1 if fails else 0)


if __name__ == "__main__":
    main()
