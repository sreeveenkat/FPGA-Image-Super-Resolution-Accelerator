#!/usr/bin/env python3
"""Time the same network on the PC (CPU, GPU) for the 960x540 -> 1920x1080 board test frame.

Run from the project root:
    .venv/bin/python software/analysis/cpu_baseline.py [--repeats 10] [--md docs/paper/cpu_baseline.md]

Rows:
  * FP32 PyTorch, CPU with 1 thread and with all threads (the fair "software" baseline)
  * FP32 PyTorch, CUDA GPU (if available; TF32 convs, synchronised timing): compute only, and incl. host<->GPU copies
Energy: CPU package energy from RAPL when readable (run with sudo), GPU board power from nvidia-smi during a frame loop.
  * INT8 NumPy integer model (the golden reference: correctness tool, NOT optimised for speed)
Times are wall-clock per frame (median of the repeats, after one warm-up), excluding file I/O.
The INT8 output is also compared with the expected board output (byte-exact check).
"""
from __future__ import annotations

import argparse
import os
import statistics
import subprocess
import sys
import threading
import time
from pathlib import Path

import numpy as np
import torch

ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(ROOT / "software" / "ai"))
sys.path.insert(0, str(ROOT / "software" / "host_tools"))
from models.srnet import predict_full  # noqa: E402
from quantization.integer_reference import QNet, upscale  # noqa: E402
from quantization.quantize import load_fp32  # noqa: E402
from srim import read_srim  # noqa: E402

LR_RAW = ROOT / "data/board/div2k_img0193_lr_960x540.raw"
EXPECTED_RAW = ROOT / "data/board/div2k_img0193_expected_1920x1080.raw"
QPARAMS = ROOT / "software/ai/quantization/qparams.npz"
W, H = 960, 540
MACS = 2560 * W * H
BOARD_MS = 1311.9  # results/speed/m7_timing_20frames.md


def timed(fn, repeats: int, sync=lambda: None) -> list[float]:
    fn()
    sync()
    out = []
    for _ in range(repeats):
        t0 = time.perf_counter()
        fn()
        sync()
        out.append((time.perf_counter() - t0) * 1e3)
    return out


RAPL = Path("/sys/class/powercap/intel-rapl:0")   # CPU package energy counter (readable as root only on this kernel)


def rapl_uj() -> int | None:
    try:
        return int((RAPL / "energy_uj").read_text())
    except (OSError, ValueError):
        return None


def rapl_joules(e0: int, e1: int) -> float:
    if e1 < e0:  # counter wrapped
        e1 += int((RAPL / "max_energy_range_uj").read_text())
    return (e1 - e0) / 1e6


class GpuPowerLog:
    """nvidia-smi power samples (every 100 ms) with our own monotonic time stamps.  Readings above 1.2 x the enforced power
    limit are dropped: this laptop GPU sometimes reports a nonsense value (749.67 W) when it wakes from its idle state."""

    def __init__(self):
        lim = subprocess.run(["nvidia-smi", "--query-gpu=enforced.power.limit", "--format=csv,noheader,nounits"],
                             capture_output=True, text=True).stdout.strip()
        self.limit = float(lim)
        self.samples: list[tuple[float, float]] = []
        self.p = subprocess.Popen(["nvidia-smi", "--query-gpu=power.draw", "--format=csv,noheader,nounits", "-lms", "100"],
                                  stdout=subprocess.PIPE, text=True)
        self.t = threading.Thread(target=self._read, daemon=True)
        self.t.start()

    def _read(self):
        for line in self.p.stdout:
            try:
                w = float(line.strip())
            except ValueError:
                continue
            self.samples.append((time.monotonic(), w))

    def stop(self):
        self.p.terminate()
        self.p.wait()

    def mean(self, t0: float, t1: float) -> tuple[float, int, int]:
        """(mean W, samples used, samples dropped) between t0 and t1."""
        win = [w for t, w in self.samples if t0 <= t <= t1]
        ok = [w for w in win if 0 < w <= 1.2 * self.limit]
        return (statistics.mean(ok) if ok else float("nan")), len(ok), len(win) - len(ok)


def main() -> None:
    ap = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    ap.add_argument("--repeats", type=int, default=20)
    ap.add_argument("--int8-repeats", type=int, default=3)
    ap.add_argument("--gpu-seconds", type=float, default=8.0, help="length of the GPU energy loop")
    ap.add_argument("--md", help="also write the report to this Markdown file")
    a = ap.parse_args()

    lr = read_srim(LR_RAW)
    assert lr.shape == (H, W, 3), lr.shape
    model = load_fp32()
    net = QNet.load(QPARAMS)
    rows = []          # (name, times in ms, energy J per frame or None, note)
    rapl_ok = rapl_uj() is not None

    idle_cpu_w = None
    if rapl_ok:
        e0, t0 = rapl_uj(), time.perf_counter()
        time.sleep(3.0)
        idle_cpu_w = rapl_joules(e0, rapl_uj()) / (time.perf_counter() - t0)

    nthreads = os.cpu_count()
    for threads in (1, nthreads):
        torch.set_num_threads(threads)
        e0 = rapl_uj()
        t = timed(lambda: predict_full(model, lr), a.repeats)
        e1 = rapl_uj()
        ej = rapl_joules(e0, e1) / (a.repeats + 1) if rapl_ok else None   # +1: the warm-up run is inside the energy window
        rows.append((f"FP32 PyTorch, CPU, {threads} thread(s)", t, ej, "CPU package (RAPL)" if rapl_ok else ""))
    torch.set_num_threads(nthreads)

    gpu_name, gpu_power = None, None
    if torch.cuda.is_available():
        gpu_name = torch.cuda.get_device_name(0)
        mg = load_fp32().cuda()
        x = torch.from_numpy(lr).permute(2, 0, 1).float().div(255).unsqueeze(0)
        x = torch.nn.functional.pad(x, (3,) * 4, mode="replicate").cuda()

        @torch.no_grad()
        def gpu_compute():
            mg(x).clamp(0, 1).mul(255).round().byte()

        @torch.no_grad()
        def gpu_with_copies():
            xi = torch.from_numpy(lr).cuda().permute(2, 0, 1).float().div(255).unsqueeze(0)
            xi = torch.nn.functional.pad(xi, (3,) * 4, mode="replicate")
            mg(xi).clamp(0, 1).mul(255).round().byte()[0].permute(1, 2, 0).cpu().numpy()

        t_c = timed(gpu_compute, a.repeats, torch.cuda.synchronize)
        t_x = timed(gpu_with_copies, a.repeats, torch.cuda.synchronize)
        try:
            log = GpuPowerLog()
        except (OSError, ValueError):
            log = None
        if log is not None:
            time.sleep(2.0)                                   # idle window
            ti0 = time.monotonic()
            time.sleep(2.0)
            ti1 = time.monotonic()
            n, tl0 = 0, time.monotonic()
            while time.monotonic() - tl0 < a.gpu_seconds:     # load window: frames back to back, with copies
                gpu_with_copies()
                n += 1
            torch.cuda.synchronize()
            tl1 = time.monotonic()
            time.sleep(0.3)
            log.stop()
            p_load, n_ok, n_bad = log.mean(tl0 + 1.0, tl1)    # skip the first second (clock ramp)
            p_idle, _, _ = log.mean(ti0, ti1)
            ms_loop = (tl1 - tl0) * 1e3 / n
            gpu_power = dict(p_load=p_load, p_idle=p_idle, n_ok=n_ok, n_bad=n_bad, frames=n, ms=ms_loop, limit=log.limit)
        ej = gpu_power["p_load"] * gpu_power["ms"] / 1e3 if gpu_power else None
        rows.append(("FP32 PyTorch, GPU, compute only (input already on the GPU)", t_c, None, ""))
        rows.append(("FP32 PyTorch, GPU, incl. host->GPU->host copies", t_x, ej,
                     "GPU board power (nvidia-smi) x loop time per frame" if ej else ""))

    t = timed(lambda: upscale(net, lr), a.int8_repeats)
    rows.append(("INT8 NumPy integer model, CPU (reference, unoptimised)", t, None, ""))
    out = upscale(net, lr)
    exact = EXPECTED_RAW.exists() and np.array_equal(out, read_srim(EXPECTED_RAW))

    lines = ["# PC baseline: same network, 960x540 -> 1920x1080\n",
             f"Generated by `software/analysis/cpu_baseline.py` on {time.strftime('%Y-%m-%d %H:%M')}. "
             f"CPU: `{_cpu_model()}` ({nthreads} logical CPUs); GPU: {gpu_name or 'none'}; PyTorch {torch.__version__}. "
             f"Input `{LR_RAW.relative_to(ROOT)}`. Times: median of {a.repeats} runs (INT8: {a.int8_repeats}) after one "
             "warm-up, wall-clock, file I/O excluded.\n",
             "| Implementation | Median ms/frame | Min / max ms | fps | GMAC/s | Speed vs ZedBoard | Energy J/frame | Energy source |",
             "|---|---|---|---|---|---|---|---|"]
    for name, t, ej, src in rows:
        med = statistics.median(t)
        lines.append(f"| {name} | {med:,.1f} | {min(t):,.1f} / {max(t):,.1f} | {1e3 / med:.2f} | "
                     f"{MACS / med / 1e6:.2f} | {BOARD_MS / med:.2f}x | {f'{ej:.3f}' if ej else 'not measured'} | {src} |")
    lines.append("| ZedBoard FPGA, 68 DSP, 100 MHz (board-measured time) | 1,311.9 | 1,311.4 / 1,313.2 | 0.76 | "
                 f"{MACS / BOARD_MS / 1e6:.2f} | 1.00x | not measured (Vivado estimate 1.913 W chip -> ~2.5 J) | |")
    lines.append(f"\nINT8 integer model output == expected board output (`{EXPECTED_RAW.name}`): "
                 f"**{'yes, byte-exact' if exact else 'NO'}**.\n")
    lines.append("Energy notes:")
    if rapl_ok:
        lines.append(f"* CPU: RAPL package energy over the timed runs / runs (whole CPU package incl. idle and other processes); "
                     f"idle package power before the runs {idle_cpu_w:.1f} W.")
    else:
        lines.append("* CPU: not measured (RAPL `energy_uj` needs root here). Run the script with `sudo .venv/bin/python ...` to add it.")
    if gpu_power:
        g = gpu_power
        lines.append(f"* GPU: nvidia-smi board power every 100 ms during {g['frames']} back-to-back frames with copies "
                     f"({g['ms']:.1f} ms per frame in the loop): mean {g['p_load']:.1f} W over {g['n_ok']} samples "
                     f"({g['n_bad']} dropped as > 1.2 x the {g['limit']:.0f} W limit); idle before: {g['p_idle']:.1f} W. "
                     "GPU power only (not CPU, RAM or the rest of the laptop); software-reported, not an external meter.")
    lines.append("* FPGA: needs a measurement on the board (12 V input current); the Vivado figure is an estimate.\n")
    lines.append("Other notes: many CPU threads are not faster here (small network, thread overhead, P/E cores; wide spread).")
    text = "\n".join(lines) + "\n"
    print(text)
    if a.md:
        Path(a.md).write_text(text)


def _cpu_model() -> str:
    try:
        for line in open("/proc/cpuinfo"):
            if line.startswith("model name"):
                return line.split(":", 1)[1].strip()
    except OSError:
        pass
    return "unknown"


if __name__ == "__main__":
    main()
