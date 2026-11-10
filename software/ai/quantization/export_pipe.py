#!/usr/bin/env python3
"""Slot-major weight ROMs for the whole-frame pipeline (docs/ARCHITECTURE_PIPELINE.md, hardware/rtl/pipe/pipe_stage.v).

Reads the canonical weights_Ln.mem ([co][ci][ky][kx], int8) of a weight directory and writes wpipe_Ln.mem next to it:
NS lines (one per slot s), each = the lane weights of that slot, lane 0 = rightmost byte.  P = 16 / NS channels per slot
(branch pipe2: NS = 16 -> wpipe_Ln.mem, the original 16-slot layout, unchanged; NS = 8 -> wpipe8_Ln.mem).  NT = lanes per tree.
    L1 (MODE 0, conv3x3 3->16):    lane r*NT + tap*3 + ci  = w[s*P+r][ci][tap]       (tree r = output channel s*P+r)
    L2 (MODE 1, depthwise3x3 16):  lane r*NT + tap         = w[s*P+r][0][tap]
    L3 (MODE 0, conv1x1 16->16):   lane r*NT + ci          = w[s*P+r][ci][0]
    L4 (MODE 2, conv3x3 16->12):   lane g*NT + q*9 + tap   = w[g][s*P+q][tap]        (tree g = output channel g, input channel s*P+q)
    tap = ky*K + kx.  With NS = 16 (P = 1) this is exactly the original layout.

Run from the project root:  .venv/bin/python software/ai/quantization/export_pipe.py [weight_dir] [--check] [--slots 16|8|all]
(default: all = both layouts).  --check only verifies that the existing wpipe files match (exit 1 otherwise).
"""
from __future__ import annotations

import sys
from pathlib import Path

import numpy as np

# (name, C_in, C_out, K, mode)
LAYERS = [("L1", 3, 16, 3, 0), ("L2", 16, 16, 3, 1), ("L3", 16, 16, 1, 0), ("L4", 16, 12, 3, 2)]
SLOTS = 16                     # channels handled per pixel (16 = C_OUT of L1..L3 = C_IN of L4)


def wpipe_name(name: str, slots: int) -> str:
    return f"wpipe_{name}.mem" if slots == 16 else f"wpipe{slots}_{name}.mem"


def read_weights(path: Path, cin: int, cout: int, k: int, mode: int) -> np.ndarray:
    vals = [int(t, 16) for t in path.read_text().split()]
    vals = [v - 256 if v >= 128 else v for v in vals]
    ci_w = 1 if mode == 1 else cin
    w = np.array(vals, dtype=np.int64).reshape(cout, ci_w, k * k)
    return w


def slot_lanes(w: np.ndarray, mode: int, slots: int = SLOTS) -> list[list[int]]:
    """lanes[s][l] for `slots` slots (16 or 8; P = 16 / slots channels per slot)."""
    assert SLOTS % slots == 0, slots
    p = SLOTS // slots
    cout, ci_w, kk = w.shape
    out = []
    for s in range(slots):
        if mode == 0:
            lanes = [int(w[s * p + r, ci, tap]) for r in range(p) for tap in range(kk) for ci in range(ci_w)]
        elif mode == 1:
            lanes = [int(w[s * p + r, 0, tap]) for r in range(p) for tap in range(kk)]
        else:
            lanes = [int(w[g, s * p + q, tap]) for g in range(cout) for q in range(p) for tap in range(kk)]
        out.append(lanes)
    return out


def lines_for(lanes: list[list[int]]) -> list[str]:
    return ["".join(f"{v & 0xFF:02x}" for v in reversed(row)) for row in lanes]   # lane 0 = rightmost byte


def main() -> int:
    args = [a for a in sys.argv[1:] if not a.startswith("--")]
    check = "--check" in sys.argv
    sel = sys.argv[sys.argv.index("--slots") + 1] if "--slots" in sys.argv else "all"
    if "--slots" in sys.argv:
        args.remove(sel)
    slot_list = [16, 8] if sel == "all" else [int(sel)]
    wdir = Path(args[0]) if args else Path("hardware/rtl/weights")
    bad = 0
    for slots in slot_list:
        for name, cin, cout, k, mode in LAYERS:
            w = read_weights(wdir / f"weights_{name}.mem", cin, cout, k, mode)
            text = "\n".join(lines_for(slot_lanes(w, mode, slots))) + "\n"
            dst = wdir / wpipe_name(name, slots)
            if check:
                ok = dst.exists() and dst.read_text() == text
                print(f"{'OK  ' if ok else 'FAIL'} {dst}")
                bad += not ok
            else:
                dst.write_text(text)
                print(f"wrote {dst} ({slots} lines x {len(text.splitlines()[0]) // 2} lanes)")
    return 1 if bad else 0


if __name__ == "__main__":
    sys.exit(main())
