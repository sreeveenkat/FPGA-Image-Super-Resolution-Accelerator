#!/usr/bin/env python3
"""Cycle model of the SR accelerator: current design (validated) vs a layer pipeline.

Run from the project root:
    .venv/bin/python software/analysis/cycle_model.py [--md docs/paper/cycle_model.md]

Part 1 rebuilds the CURRENT design (four folded engines, one after the other, per 64x64 tile) from the
same formula as conv_engine.v (PERIOD = max(STEPS, C_OUT)) and compares it with the simulated and the
board-measured numbers. Part 2 uses the same building blocks for a PREDICTED design: whole-frame
line-buffer streaming with all four layers running at the same time, lanes per layer chosen for a DSP
budget, clock as a parameter. Part 2 numbers are model estimates, NOT measurements.
"""
from __future__ import annotations

import argparse
import itertools
import math

# (name, C_in, C_out, K, depthwise)
LAYERS = [("L1", 3, 16, 3, False), ("L2", 16, 16, 3, True), ("L3", 16, 16, 1, False), ("L4", 16, 12, 3, False)]
HALO = 3
TILE = 64
LR_W, LR_H = 960, 540
DSP_TOTAL = 220
REQ_DSP = 2  # DSPs per requantizer (32x17-bit multiply), as in the current RTL

# Measured / simulated reference values (sources in results/)
SIM_LAYER_CYCLES = [124_872, 69_713, 69_720, 589_844]   # results/utilization/m4_conv_engine.md
SIM_CORE_CYCLES = 926_201                                 # results/utilization/m5_tile_core.md
BOARD_CYCLES_PER_TILE = 926_220                           # results/speed/m7_timing_20frames.md (mean)
BOARD_FRAME_MS = 1_311.9                                  # same file
BOARD_PAD_MS = 5.9                                        # ARM padding, same file
CURRENT_DSP = 68


def steps(cin: int, k: int, dw: bool) -> int:
    return k * k * (1 if dw else cin)


def macs_per_px(cin: int, cout: int, k: int, dw: bool) -> int:
    return steps(cin, k, dw) * cout


def tile_out_sizes() -> list[int]:
    """Output side of each layer for one tile (valid convs on a TILE+2*HALO input)."""
    side, out = TILE + 2 * HALO, []
    for _, _, _, k, _ in LAYERS:
        side -= k - 1
        out.append(side)
    return out


def frame_out_sizes() -> list[tuple[int, int]]:
    """Output size of each layer for a whole replicate-padded frame (no tiles)."""
    w, h, out = LR_W + 2 * HALO, LR_H + 2 * HALO, []
    for _, _, _, k, _ in LAYERS:
        w, h = w - k + 1, h - k + 1
        out.append((w, h))
    return out


# ---------------------------------------------------------------- Part 1: current design
def current_design() -> dict:
    rows, total = [], 0
    for (name, cin, cout, k, dw), side, sim in zip(LAYERS, tile_out_sizes(), SIM_LAYER_CYCLES):
        period = max(steps(cin, k, dw), cout)
        model = side * side * period
        lanes = cout
        util = macs_per_px(cin, cout, k, dw) / (period * lanes)
        rows.append((name, side, period, model, sim, util, lanes + REQ_DSP))
        total += model
    io = SIM_CORE_CYCLES - sum(SIM_LAYER_CYCLES)
    tiles = math.ceil(LR_W / TILE) * math.ceil(LR_H / TILE)
    tile_macs = sum(macs_per_px(*l[1:]) * s * s for l, s in zip(LAYERS, tile_out_sizes()))
    return dict(rows=rows, model_engines=total, io=io, tiles=tiles, tile_macs=tile_macs)


# ---------------------------------------------------------------- Part 2: layer pipeline
def lane_options(cin: int, cout: int, k: int, dw: bool) -> list[int]:
    """Lane counts that map to whole output channels x whole kernel steps (no ragged loops)."""
    s = steps(cin, k, dw)
    div = lambda n: [d for d in range(1, n + 1) if n % d == 0]
    return sorted({a * b for a in div(cout) for b in div(s)})


def layer_cost(layer, lanes: int) -> tuple[int, int]:
    """(cycles per output pixel, DSPs) for a layer with `lanes` MAC lanes."""
    _, cin, cout, k, dw = layer
    cyc = math.ceil(macs_per_px(cin, cout, k, dw) / lanes)
    req = math.ceil(cout / cyc)  # one requantizer finishes one output value per cycle
    return cyc, lanes + REQ_DSP * req


def best_pipeline(budget: int):
    """Lanes per layer minimising the slowest stage (frame cycles), within `budget` DSPs."""
    sizes = frame_out_sizes()
    best = None
    for lanes in itertools.product(*(lane_options(*l[1:]) for l in LAYERS)):
        costs = [layer_cost(l, p) for l, p in zip(LAYERS, lanes)]
        dsp = sum(c[1] for c in costs)
        if dsp > budget:
            continue
        stage = [c[0] * w * h for c, (w, h) in zip(costs, sizes)]
        key = (max(stage), dsp)
        if best is None or key < best[0]:
            best = (key, lanes, costs, stage)
    return best


def pipeline_frame_cycles(costs, stage, stream_bytes: int) -> tuple[int, str]:
    """Frame cycles = slowest stage, I/O limit and pipeline fill (a few rows per layer)."""
    w4, h4 = frame_out_sizes()[-1]
    out_bytes = w4 * h4 * 12                      # 2x2x3 output bytes per LR pixel
    io = math.ceil(out_bytes / stream_bytes)      # output stream is the larger one
    ii = max(c[0] for c in costs)
    fill = sum((k - 1) * (LR_W + 2 * HALO) * ii for _, _, _, k, _ in LAYERS)
    core = max(max(stage), io)
    return core + fill, ("I/O stream" if io > max(stage) else "compute")


def shared_engine(dsp: int):
    """ONE engine for all four layers, time-shared tile by tile (layers one after another, like today, but every layer gets all lanes).
    R requantizers (2 DSP each) + MAC lanes = dsp; per layer the largest lane count that maps to whole channels x whole kernel steps.
    Returns the best (cycles per tile for the engines, R, lanes per layer, cycles/px per layer)."""
    best = None
    for r in range(1, dsp // 2):
        budget = dsp - REQ_DSP * r
        if budget < 1:
            break
        lanes, cyc, total = [], [], 0
        for layer, side in zip(LAYERS, tile_out_sizes()):
            opts = [p for p in lane_options(*layer[1:]) if p <= budget]
            p = max(opts)
            c = max(math.ceil(macs_per_px(*layer[1:]) / p), math.ceil(layer[2] / r))
            lanes.append(p); cyc.append(c); total += c * side * side
        if best is None or total < best[0]:
            best = (total, r, lanes, cyc)
    return best


def line_buffer_bram36() -> int:
    """K-1 rows per 3x3 layer, row <= 1024 pixels -> one BRAM36 (1Kx36) per 36 bits of pixel width."""
    n = 0
    for _, cin, _, k, _ in LAYERS:
        if k > 1:
            n += (k - 1) * math.ceil(8 * cin / 36)
    return n


# ---------------------------------------------------------------- report
def report() -> str:
    out = []
    p = out.append
    cur = current_design()
    p("# Cycle model: current design vs layer pipeline\n")
    p("Generated by `software/analysis/cycle_model.py`. Part 1 checks the model against simulation and the board; "
      "Parts 2 and 3 are **predictions** (model, not measured).\n")

    p("## Part 1 - current design (sequential folded engines, 64x64 tiles)\n")
    p("| Layer | Out side | Cycles/px (PERIOD) | Model cycles/tile | Simulated | Diff | Lane util. | DSP |")
    p("|---|---|---|---|---|---|---|---|")
    for name, side, period, model, sim, util, dsp in cur["rows"]:
        p(f"| {name} | {side} | {period} | {model:,} | {sim:,} | {sim - model:+d} | {util:.0%} | {dsp} |")
    core = sum(SIM_LAYER_CYCLES) + cur["io"]
    p(f"\nEngines {sum(SIM_LAYER_CYCLES):,} + byte-stream I/O {cur['io']:,} = {core:,} cycles/tile (simulated); "
      f"board CYCLES mean {BOARD_CYCLES_PER_TILE:,}.")
    t_core = cur["tiles"] * BOARD_CYCLES_PER_TILE / 1e8 * 1e3
    p(f"Frame: {cur['tiles']} tiles x {BOARD_CYCLES_PER_TILE:,} / 100 MHz = {t_core:,.1f} ms core; "
      f"board {BOARD_FRAME_MS:,.1f} ms -> ARM/DMA overhead {BOARD_FRAME_MS - t_core:,.1f} ms.\n")

    frame_macs = 2560 * LR_W * LR_H
    tiled_macs = cur["tile_macs"] * cur["tiles"]
    p("### Utilization gap\n")
    p("| Quantity | Value |\n|---|---|")
    p(f"| MACs per frame, no halo (2,560 x 960 x 540) | {frame_macs / 1e9:.3f} G |")
    p(f"| MACs per frame as tiled (halo recomputed) | {tiled_macs / 1e9:.3f} G (+{tiled_macs / frame_macs - 1:.1%}) |")
    p(f"| Ideal time, {CURRENT_DSP} DSP x 100 MHz | {frame_macs / (CURRENT_DSP * 1e8):.3f} s |")
    p(f"| Ideal time, {DSP_TOTAL} DSP x 100 MHz | {frame_macs / (DSP_TOTAL * 1e8):.3f} s |")
    mpc_core = cur["tile_macs"] / BOARD_CYCLES_PER_TILE
    mpc_frame = tiled_macs / (BOARD_FRAME_MS * 1e-3 * 1e8)
    p(f"| MACs per cycle inside the core (tile MACs / CYCLES) | {mpc_core:.1f} = {mpc_core / CURRENT_DSP:.1%} of {CURRENT_DSP} DSPs |")
    p(f"| MACs per cycle over the whole frame (incl. ARM/DMA) | {mpc_frame:.1f} = {mpc_frame / CURRENT_DSP:.1%} of {CURRENT_DSP} DSPs |")
    p("\nCause: each engine keeps its lanes busy (L1/L3/L4 100 %, L2 56 %), but only one engine runs at a time, "
      "so on average about 3/4 of the DSPs are idle.\n")

    p("## Part 2 - prediction: whole-frame line-buffer pipeline, all layers at once\n")
    p("Assumptions: no tiles (no halo recomputation); each layer streams with a fixed cycles-per-pixel; lanes = whole "
      "output channels x whole kernel steps; requantizers = ceil(C_out / cycles-per-pixel), 2 DSP each; "
      "32-bit output stream (4 bytes/cycle); fill = (K-1) rows per layer; no stalls; ARM padding "
      f"{BOARD_PAD_MS} ms added (as measured today). Real designs lose some of this to stalls and control.\n")
    p("| DSP budget | Lanes L1/L2/L3/L4 | Cycles/px per layer | DSP used | Limit | Frame cycles | "
      "100 MHz | 125 MHz | 150 MHz |")
    p("|---|---|---|---|---|---|---|---|---|")
    for budget in (68, 100, 150, 200):
        best = best_pipeline(budget)
        if best is None:
            continue
        (_, dsp), lanes, costs, stage = best
        cyc, limit = pipeline_frame_cycles(costs, stage, 4)
        cells = []
        for f in (100e6, 125e6, 150e6):
            ms = cyc / f * 1e3 + BOARD_PAD_MS
            cells.append(f"{ms:,.0f} ms / {1e3 / ms:.1f} fps")
        p(f"| {budget} | {'/'.join(map(str, lanes))} | {'/'.join(str(c[0]) for c in costs)} | {dsp} | {limit} | "
          f"{cyc / 1e6:.2f} M | " + " | ".join(cells) + " |")
    p(f"\nLine buffers: about {line_buffer_bram36()} BRAM36 (K-1 rows per 3x3 layer) instead of the "
      "70 BRAM tiles of today's five tile RAMs (weights extra; wide weight reads for many lanes may need LUTRAM/registers).")
    p("\n## Part 3 - prediction: one shared engine (same 68 DSP), layers time-shared per tile\n")
    p("Same tiles as today (64x64 + 3 px halo, halo recomputed) and the same activation RAMs; the four per-layer engines are replaced by one "
      "engine that gets all DSPs for each layer in turn. Two I/O cases: today's byte-wide load/output (72,052 cycles per tile, not overlapped) "
      f"and fully overlapped I/O (0). ARM/DMA overhead as measured today ({BOARD_FRAME_MS - cur['tiles'] * BOARD_CYCLES_PER_TILE / 1e5:,.1f} ms "
      "per frame) is added. Model, not measured.\n")
    p("| DSP | Requantizers | Lanes L1/L2/L3/L4 | Cycles/px per layer | Engine cycles/tile | I/O | 100 MHz | 150 MHz | BRAM |")
    p("|---|---|---|---|---|---|---|---|---|")
    se = shared_engine(CURRENT_DSP)
    overhead_ms = BOARD_FRAME_MS - cur["tiles"] * BOARD_CYCLES_PER_TILE / 1e5
    for io_name, io in (("today (72,052)", cur["io"]), ("overlapped (0)", 0)):
        tile = se[0] + io
        cells = []
        for f in (100e6, 150e6):
            ms = cur["tiles"] * tile / f * 1e3 + overhead_ms
            cells.append(f"{ms:,.0f} ms / {1e3 / ms:.1f} fps")
        p(f"| {CURRENT_DSP} | {se[1]} | {'/'.join(map(str, se[2]))} | {'/'.join(map(str, se[3]))} | {se[0]:,} | {io_name} | "
          + " | ".join(cells) + " | ~70 (today's tile RAMs; weights for all layers in one ROM) |")
    p(f"\nFor comparison, today's four engines: {sum(SIM_LAYER_CYCLES):,} engine cycles per tile; measured frame {BOARD_FRAME_MS:,.1f} ms.")
    # Part 4: the r0_125 sandbox build (docs/paper/fmax_plan.md section 7)
    extra = 4                                            # +1 cycle per engine run x 4 engines; simulated 926,201 -> 926,205 (branch r0_125)
    p("\n## Part 4 - prediction: the r0_125 build (deployed network, one more register per engine run, fabric clock 125 MHz)\n")
    p("Same architecture as today plus one register between the activation RAM mux and the MAC DSP (`docs/paper/fmax_plan.md`). The build exists "
      "(branch `r0_125`, routed WNS +0.632 ns at 125 MHz, 0 failing endpoints) and is simulated, but it has NOT run on the board: the frame times below are "
      f"model predictions. Cycles per tile = board mean {BOARD_CYCLES_PER_TILE:,} + {extra}; ARM/DMA overhead held at {overhead_ms:,.1f} ms (as in Part 3).\n")
    p("| Clock | Cycles per tile | Core time per frame | Frame time (predicted) | fps (predicted) |")
    p("|---|---|---|---|---|")
    for f in (100e6, 125e6):
        core = cur["tiles"] * (BOARD_CYCLES_PER_TILE + extra) / f * 1e3
        ms = core + overhead_ms
        p(f"| {f / 1e6:.0f} MHz | {BOARD_CYCLES_PER_TILE + extra:,} | {core:,.1f} ms | {ms:,.1f} ms | {1e3 / ms:.3f} |")
    p("\nCaveats: the 125 MHz build met timing in Vivado (post-route, not on the board); 150 MHz is NOT shown to close timing. Today's whole system has "
      "WNS +0.503 ns at 100 MHz, and a 152.38 MHz trial "
      "of the unchanged design failed by 1.693 ns (`docs/paper/timing_150mhz.md`; path: activation RAM -> split-RAM mux -> MAC DSP input), "
      "so the 150 MHz figures of Part 3 still need a pipelining change. Do not mix the two 3.9 fps figures: Part 2's is the line-buffer "
      "pipeline at 100 MHz, Part 3's is the shared engine at 150 MHz with fully overlapped I/O. "
      "The 32-bit stream caps the pipeline at 3 cycles per LR pixel (64-bit would halve that); "
      "DSP packing of two INT8 multiplies is not modelled.")
    p(part5(cur, overhead_ms))
    return "\n".join(out) + "\n"


# ---------------------------------------------------------------- Part 5: architecture choice for the next design
PIPE_BUDGET = 168      # DSPs of the chosen layer pipeline (lanes 27/9/16/108 + 4 requantizers); best_pipeline(168) picks exactly these lanes


def part5(cur: dict, overhead_ms: float) -> str:
    out = []
    p = out.append
    p("\n## Part 5 - prediction: next architecture, (i) one shared engine with all DSPs vs (ii) a line-buffer layer pipeline\n")
    p("Both with the R3q network (same layers; the anchor add sits in the last requantizer, no extra cycle). Model, NOT measured.\n")
    p("(i) Shared engine: today's tiles (64x64 + 3 px halo, halo recomputed), layers one after another, every layer gets all lanes "
      "(`shared_engine()`, Part 3 method). Frame time = 135 tiles x (engine + I/O cycles) / clock + today's ARM/DMA overhead "
      f"({overhead_ms:,.1f} ms: the ARM still cuts and places tiles).\n")
    p("(ii) Layer pipeline: whole frame streamed in raster order, no tiles, all four layers at the same time, 2-row line buffers "
      "for the 3x3 layers (`best_pipeline()`, Part 2 method). Frame time = slowest stage + fill (2 rows per 3x3 layer) / clock + "
      f"ARM padding {BOARD_PAD_MS} ms (no tile copy: the DMA reads the padded frame and writes the 1920x1080 output in place).\n")
    p("| Design | DSP | Lanes L1/L2/L3/L4 | Cycles/px per layer | Cycles per frame | 100 MHz | 125 MHz |")
    p("|---|---|---|---|---|---|---|")
    rows = []
    for dsp in (DSP_TOTAL,):
        se = shared_engine(dsp)
        used = max(se[2]) + REQ_DSP * se[1]           # widest layer's lanes + the requantizers
        for io_name, io in (("I/O as today", cur["io"]), ("I/O overlapped", 0)):
            cyc = cur["tiles"] * (se[0] + io)
            cells = [f"{(ms := cyc / f * 1e3 + overhead_ms):,.0f} ms / {1e3 / ms:.1f} fps" for f in (100e6, 125e6)]
            rows.append((f"(i) shared, {io_name}", used, se[2], se[3], cyc, cells))
    (_, dsp), lanes, costs, stage = best_pipeline(PIPE_BUDGET)
    cyc, _ = pipeline_frame_cycles(costs, stage, 4)
    cells = [f"{(ms := cyc / f * 1e3 + BOARD_PAD_MS):,.0f} ms / {1e3 / ms:.1f} fps" for f in (100e6, 125e6)]
    rows.append(("(ii) layer pipeline", dsp, lanes, [c[0] for c in costs], cyc, cells))
    for name, dsp, ln, cpp, cyc, cells in rows:
        p(f"| {name} | {dsp} | {'/'.join(map(str, ln))} | {'/'.join(map(str, cpp))} | {cyc / 1e6:.2f} M | " + " | ".join(cells) + " |")
    p(f"\n(i) is given the whole device ({DSP_TOTAL} DSP) and picks its own number of requantizers (it uses {rows[0][1]}). (ii) uses 168 DSP: "
      "16 cycles per output pixel in EVERY layer (rate-matched), which more DSPs cannot shorten without breaking that balance "
      f"(best_pipeline at 200-220 DSP gives {best_pipeline(DSP_TOTAL)[0][0] / 1e6:.2f} M stage cycles, "
      f"{1 - best_pipeline(DSP_TOTAL)[0][0] / max(stage):.1%} fewer, for 34 more DSPs and uneven layers).\n")
    p("| | (i) shared engine | (ii) layer pipeline |")
    p("|---|---|---|")
    p(f"| Predicted fps at 125 MHz | {rows[0][5][1].split('/ ')[1]} (I/O as today) .. {rows[1][5][1].split('/ ')[1]} (I/O fully overlapped) | {rows[-1][5][1].split('/ ')[1]} |")
    p(f"| BRAM36 (estimate) | ~70 (today's tile RAMs) + banking for multi-pixel reads | ~{line_buffer_bram36() + PIPE_EXTRA_BRAM} "
      f"({line_buffer_bram36()} line buffers + {PIPE_EXTRA_BRAM} anchor FIFO / output row buffers) |")
    p("| LUT (estimate, accelerator only) | ~4-6k: lane operand crossbar that differs per layer, address generators for 4 layer shapes | "
      "~6-8k: adder trees (L4: 12 x 9-input), window registers, 16:1 channel selects, weight ROMs in LUTs |")
    p("| MACs per cycle actually used | 144-192 lanes, but only while computing; tiles still recompute the 17 % halo | "
      f"160 lanes, {2560 / (16 * 160):.0%} busy (L1 27, L2 9, L3 16, L4 108 lanes all at 16 cycles per pixel) |")
    p("| ARM work per frame | pad + cut 135 tiles + place outputs (measured today: 32.3 ms) | pad only (measured today: 5.9 ms) |")
    p("| Design risk | HIGH: the MAC operand mux grows with the lane count, on the path that already limits fmax "
      "(RAM -> mux -> DSP, `timing_150mhz.md`); L1/L4 need 9 pixel reads per cycle (banked RAM or a window buffer); "
      "tile I/O and halo stay | MEDIUM: four fixed-function stages, each with ONE operand pattern; new parts are line buffers, "
      "per-pixel flow control between stages and a row buffer for the raster output; no tiles, no seams |")
    p("| Verification reuse | engines + core tests largely replaced | integer model `upscale()` on whole frames is the golden "
      "reference directly (no tiling step), small frames simulate quickly |")
    p("\nChoice: (ii), see `docs/ARCHITECTURE_PIPELINE.md`. Not modelled for either: AXI/DDR stalls, cache maintenance of the "
      "whole frame buffers on the ARM, DSP packing of two INT8 multiplies.")
    return "\n".join(out)


PIPE_EXTRA_BRAM = 9    # anchor FIFO 4096 x 24 bit (3 BRAM36) + double-buffered 2-HR-row output buffer (2 x 3 BRAM36); estimate


def main() -> None:
    ap = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    ap.add_argument("--md", help="also write the report to this Markdown file")
    a = ap.parse_args()
    text = report()
    print(text)
    if a.md:
        with open(a.md, "w") as f:
            f.write(text)


if __name__ == "__main__":
    main()
