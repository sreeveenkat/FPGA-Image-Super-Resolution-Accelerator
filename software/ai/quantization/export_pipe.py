#!/usr/bin/env python3
"""Slot-major weight ROMs for the whole-frame pipeline (docs/ARCHITECTURE_PIPELINE.md, hardware/rtl/pipe/pipe_stage.v).

Reads the canonical weights_Ln.mem ([co][ci][ky][kx], int8) of a weight directory and writes wpipe_Ln.mem next to it:
16 lines (one per slot s), each = the lane weights of that slot, lane 0 = rightmost byte.
    L1 (MODE 0, conv3x3 3->16):    lane tap*3 + ci   = w[s][ci][tap]
    L2 (MODE 1, depthwise3x3 16):  lane tap          = w[s][0][tap]
    L3 (MODE 0, conv1x1 16->16):   lane ci           = w[s][ci][0]
    L4 (MODE 2, conv3x3 16->12):   lane g*9 + tap    = w[g][s][tap]          tap = ky*K + kx

Run from the project root:  .venv/bin/python software/ai/quantization/export_pipe.py [weight_dir] [--check]
--check only verifies that the existing wpipe files match (exit 1 otherwise).
"""
from __future__ import annotations

import sys
from pathlib import Path

import numpy as np

# (name, C_in, C_out, K, mode)
LAYERS = [("L1", 3, 16, 3, 0), ("L2", 16, 16, 3, 1), ("L3", 16, 16, 1, 0), ("L4", 16, 12, 3, 2)]
SLOTS = 16


def read_weights(path: Path, cin: int, cout: int, k: int, mode: int) -> np.ndarray:
    vals = [int(t, 16) for t in path.read_text().split()]
    vals = [v - 256 if v >= 128 else v for v in vals]
    ci_w = 1 if mode == 1 else cin
    w = np.array(vals, dtype=np.int64).reshape(cout, ci_w, k * k)
    return w


def slot_lanes(w: np.ndarray, mode: int) -> list[list[int]]:
    """lanes[s][l] for the 16 slots."""
    cout, ci_w, kk = w.shape
    out = []
    for s in range(SLOTS):
        if mode == 0:
            lanes = [int(w[s, ci, tap]) for tap in range(kk) for ci in range(ci_w)]
        elif mode == 1:
            lanes = [int(w[s, 0, tap]) for tap in range(kk)]
        else:
            lanes = [int(w[g, s, tap]) for g in range(cout) for tap in range(kk)]
        out.append(lanes)
    return out


def lines_for(lanes: list[list[int]]) -> list[str]:
    return ["".join(f"{v & 0xFF:02x}" for v in reversed(row)) for row in lanes]   # lane 0 = rightmost byte


def main() -> int:
    args = [a for a in sys.argv[1:] if not a.startswith("--")]
    check = "--check" in sys.argv
    wdir = Path(args[0]) if args else Path("hardware/rtl/weights")
    bad = 0
    for name, cin, cout, k, mode in LAYERS:
        w = read_weights(wdir / f"weights_{name}.mem", cin, cout, k, mode)
        text = "\n".join(lines_for(slot_lanes(w, mode))) + "\n"
        dst = wdir / f"wpipe_{name}.mem"
        if check:
            ok = dst.exists() and dst.read_text() == text
            print(f"{'OK  ' if ok else 'FAIL'} {dst}")
            bad += not ok
        else:
            dst.write_text(text)
            print(f"wrote {dst} ({SLOTS} lines x {len(text.splitlines()[0]) // 2} lanes)")
    return 1 if bad else 0


if __name__ == "__main__":
    sys.exit(main())
