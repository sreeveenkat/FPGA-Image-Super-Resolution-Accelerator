#!/usr/bin/env python3
"""Predicted frame time of TODAY'S architecture if one pipeline register per engine run (+1 cycle per run) lets the fabric clock rise.  MODEL, nothing built.

    .venv/bin/python software/analysis/fmax_prediction.py            (prints a markdown table; docs/paper/fmax_plan.md quotes it)

Same convention as cycle_model.py Part 3: frame = tiles x cycles_per_tile / f + overhead, overhead = board frame time - core time at 100 MHz (61.5 ms), held CONSTANT with the clock
(conservative for the DMA part, which would shrink; the ARM copy/padding part does not depend on the fabric clock).  Cycles per tile: board mean 926,220 (+ extra register cycles).
"""
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))
import cycle_model as cm  # noqa: E402

EXTRA_CYCLES_PER_TILE = 4          # one register stage = +1 cycle per engine run, 4 engines (the 2026-10-09 requantizer stage went 926,197 -> 926,201 in simulation)


def frame_ms(f_hz: float, extra: int = 0) -> float:
    cur = cm.current_design()
    overhead = cm.BOARD_FRAME_MS - cur["tiles"] * cm.BOARD_CYCLES_PER_TILE / 1e5
    return cur["tiles"] * (cm.BOARD_CYCLES_PER_TILE + extra) / f_hz * 1e3 + overhead


def table() -> str:
    cur = cm.current_design()
    overhead = cm.BOARD_FRAME_MS - cur["tiles"] * cm.BOARD_CYCLES_PER_TILE / 1e5
    L = ["| Clock | Cycles per tile | Frame time | fps |", "|---|---|---|---|",
         f"| 100 MHz, today (board-measured 1,311.9 ms) | {cm.BOARD_CYCLES_PER_TILE:,} | {cm.BOARD_FRAME_MS:,.1f} ms | {1e3 / cm.BOARD_FRAME_MS:.3f} |"]
    for f in (100e6, 125e6, 150e6):
        ms = frame_ms(f, EXTRA_CYCLES_PER_TILE)
        L.append(f"| {f / 1e6:.0f} MHz, +{EXTRA_CYCLES_PER_TILE} cycles per tile (predicted) | {cm.BOARD_CYCLES_PER_TILE + EXTRA_CYCLES_PER_TILE:,} | {ms:,.1f} ms | {1e3 / ms:.3f} |")
    L.append("")
    L.append(f"Tiles per frame {cur['tiles']}; overhead held at {overhead:.1f} ms (ARM padding + copies + DMA handshakes, as measured at 100 MHz).")
    return "\n".join(L)


if __name__ == "__main__":
    print(table())
