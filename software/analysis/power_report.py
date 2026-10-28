#!/usr/bin/env python3
"""Collects the Vivado power reports of results/power_estimate/ into tables and energy per frame.  Every number is a Vivado ESTIMATE, not measured.  Created 2026-10-28.

    .venv/bin/python software/analysis/power_report.py            (writes results/power_estimate/tables.md and tables.csv)

Inputs (made by hardware/vivado/scripts/power_baseline.tcl and power_saif.tcl):
  results/power_estimate/{pipe,r0}_power_vectorless.txt                      baseline, default (vectorless) settings
  results/power_estimate/raw/{pipe,r0}_rtl_power.txt (+_core_match.txt)       RTL simulation SAIF
  results/power_estimate/raw/r0_impl_w{1..5}_power.txt, pipe_impl_w{1,2}_*    post-implementation functional netlist SAIF windows
Windows are combined with time weights = number of simulated cycles (power is linear in the toggle rates; static power is constant).
"""
import re
from pathlib import Path

R = Path("results/power_estimate")
RAW = R / "raw"
ROWS = ["Clocks", "Slice Logic", "Signals", "Block RAM", "DSPs", "I/O", "PS7", "Static Power", "Total"]


def num(s):
    s = s.strip()
    return 0.0005 if s.startswith("<") else float(s)          # '<0.001' shown as 0.0005 (half the print resolution)


def parse(p):
    t = Path(p).read_text()
    d = {}
    for k, key in (("total", r"Total On-Chip Power \(W\)"), ("dynamic", r"Dynamic \(W\)"), ("static", r"Device Static \(W\)")):
        d[k] = float(re.search(r"\|\s*" + key + r"\s*\|\s*([0-9.]+)", t).group(1))
    d["conf"] = re.search(r"\|\s*Confidence Level\s*\|\s*(\w+)", t).group(1)
    m = re.search(r"Design Nets Matched\s*\|\s*(NA|\d+%\s*\((\d+)/(\d+)\))", t)
    d["matched"] = m.group(1).strip() if m else "NA"
    for r in ROWS:
        m = re.search(r"^\|\s*" + re.escape(r) + r"\s*\|\s*([<0-9.]+)", t, re.M)
        d[r] = num(m.group(1)) if m else float("nan")
    cm = Path(str(p).replace("_power.txt", "_core_match.txt")) if str(p).endswith("_power.txt") else Path("/nonexistent")
    if cm.exists():
        c = dict(l.split() for l in cm.read_text().splitlines())
        tot = int(c["core_nets_total"]); s = int(c.get("source_(S)", 0))
        d["core_matched"] = f"{100 * s / tot:.0f}% ({s}/{tot})"
    else:
        d["core_matched"] = "NA"
    return d


def duration_ps(saif):
    with open(saif) as f:
        for line in f:
            m = re.search(r"\(DURATION\s+(\d+)\)", line)
            if m:
                return int(m.group(1))


def combine(ds, ws):
    out = {}
    for k in ["total", "dynamic", "static"] + ROWS:
        out[k] = sum(w * d[k] for d, w in zip(ds, ws)) / sum(ws)
    out["conf"] = ds[0]["conf"]; out["matched"] = ds[0]["matched"]; out["core_matched"] = ds[0]["core_matched"]
    return out


def main():
    W = Path.home() / "Desktop/venkat/power_estimate_work"
    res = {}
    res["pipe vectorless"] = parse(R / "pipe_power_vectorless.txt")
    res["r0 vectorless"] = parse(R / "r0_power_vectorless.txt")
    res["pipe RTL SAIF (400k cycles)"] = parse(RAW / "pipe_rtl_power.txt")
    res["r0 RTL SAIF (whole tile)"] = parse(RAW / "r0_rtl_power.txt")
    r0w = [parse(RAW / f"r0_impl_w{k}_power.txt") for k in range(1, 6)]
    r0d = [duration_ps(W / f"r0/xi/r0_netlist_w{k}.saif") for k in range(1, 6)]
    # window 5 contains about 0.24 ms of idle time after the tile ended; weight it with the cycles of the tile that were left (926,2xx - 760,000)
    r0c = [190000, 190000, 190000, 190000, 926238 - 760000]
    res["r0 post-impl SAIF (5 windows, whole tile)"] = combine(r0w, r0c)
    pw = [parse(RAW / f"pipe_impl_w{k}_power.txt") for k in (1, 2)]
    res["pipe post-impl SAIF (2 windows, 150k cycles)"] = combine(pw, [75000, 75000])
    lines = ["# Vivado power estimates (NOT measured)", "", "Total on-chip power, W, and breakdown (W). PS7 = the Zynq processing system as Vivado models it (not our design).", "",
             "| Run | Total | Dynamic | Static | Clocks | Slice Logic | Signals | BRAM | DSP | I/O | PS7 | Confidence | Nets matched (design) | Nets matched (core instance) |", "|---|---|---|---|---|---|---|---|---|---|---|---|---|---|"]
    csv = ["run,total,dynamic,static,clocks,logic,signals,bram,dsp,io,ps7,confidence,matched,core_matched"]
    for k, d in res.items():
        lines.append(f"| {k} | {d['total']:.3f} | {d['dynamic']:.3f} | {d['static']:.3f} | {d['Clocks']:.3f} | {d['Slice Logic']:.3f} | {d['Signals']:.3f} | {d['Block RAM']:.3f} | {d['DSPs']:.3f} | {d['I/O']:.4f} | {d['PS7']:.3f} | {d['conf']} | {d['matched']} | {d['core_matched']} |")
        csv.append(",".join(str(x) for x in (k, round(d["total"], 4), round(d["dynamic"], 4), round(d["static"], 4), d["Clocks"], d["Slice Logic"], d["Signals"], d["Block RAM"], d["DSPs"], d["I/O"], d["PS7"], d["conf"], d["matched"].replace(",", ";"), d["core_matched"])))
    lines += ["", "Per window (post-implementation netlist SAIF), total W: R0 " + ", ".join(f"w{i + 1} {d['total']:.3f}" for i, d in enumerate(r0w)) + "; pipeline " + ", ".join(f"w{i + 1} {d['total']:.3f}" for i, d in enumerate(pw)), ""]
    # energy per frame
    cases = [("Pipeline (default build)", "pipe", 95.4, 67.19), ("Pipeline (non-cacheable DMA buffers)", "pipe", 70.5, 67.19), ("R0 (100 MHz)", "r0", 1312.5, 1250.4)]
    lines += ["## Energy per frame (Vivado estimate, not measured)", "",
              "E = P x t with the frame times of 2026-10-28 (pipeline 95.4 ms and 70.5 ms, R0 1,312.5 ms). 'PL' = total on-chip minus PS7 (includes the device static power); 'PL dynamic' = dynamic minus PS7.",
              "P_active = the power with the simulated activity (compute phase). 'Simple' assumes P_active for the whole frame; 'refined' uses P_active only while the core computes (core time / frame time) and P_idle = P_active minus the dynamic power of slice logic, signals, BRAM and DSP for the rest.", "",
              "| Case | Power source | Frame ms | P_total W | E_total mJ | P_PL W | E_PL mJ | P_PL dynamic W | E_PL dynamic mJ | refined E_total mJ | refined E_PL mJ |", "|---|---|---|---|---|---|---|---|---|---|---|"]
    for name, who, ms, core_ms in cases:
        for label, key in ((f"{who} vectorless", f"{who} vectorless"), (f"{who} post-impl SAIF", "pipe post-impl SAIF (2 windows, 150k cycles)" if who == "pipe" else "r0 post-impl SAIF (5 windows, whole tile)")):
            d = res[key]; t = ms / 1000
            idle = d["total"] - (d["Slice Logic"] + d["Signals"] + d["Block RAM"] + d["DSPs"])
            f = core_ms / ms
            pf = f * d["total"] + (1 - f) * idle
            lines.append(f"| {name} | {label} | {ms} | {d['total']:.3f} | {1000 * d['total'] * t:.0f} | {d['total'] - d['PS7']:.3f} | {1000 * (d['total'] - d['PS7']) * t:.0f} | {d['dynamic'] - d['PS7']:.3f} | {1000 * (d['dynamic'] - d['PS7']) * t:.1f} | {1000 * pf * t:.0f} | {1000 * (pf - d['PS7']) * t:.0f} |")
    (R / "tables.md").write_text("\n".join(lines) + "\n")
    (R / "tables.csv").write_text("\n".join(csv) + "\n")
    print("\n".join(lines))


if __name__ == "__main__":
    main()
