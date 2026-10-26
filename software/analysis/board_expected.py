#!/usr/bin/env python3
"""Expected board answers for the three designs (R0 / 0602, R2q, R3q), recomputed from each tree's OWN integer model and checked against the files the board test will use.

    .venv/bin/python software/analysis/board_expected.py [--md docs/paper/board_expected.md]      (project root of main; ~40 s)

Per design it (1) parses software/board/sr_app/golden_tile.h of that tree (T1 input and expected output) and re-runs that tree's integer model on the input:
the two must agree, (2) re-runs the model on data/board/div2k_img0193_lr_960x540.raw and on set14_baboon_lr_128x128.raw and compares with the stored expected files (T2, 135 and 4 tiles),
(3) reads the VERSION constant of that tree's RTL, (4) lists md5 and path of bitstream, xsa and the ELFs, and warns when a source file is newer than an ELF.
Checksum = FNV-1a 32 over the payload (after the 16-byte SRIM header), the number the board prints as fnv1a32.  Exit code 1 if any cross-check fails.
Nothing here touches the board; it says what the board must print, not what it printed.
"""
import argparse
import hashlib
import json
import re
import subprocess
import sys
from pathlib import Path

V = Path.home() / "Desktop/venkat"
TREES = {
    "R0 / 0602": dict(tree=V / "sem_project_all", version_expected="0x53520602",
                      bits=[("tested copy (read-only)", V / "TESTED_0602.bit"), ("Vivado project output (run_board.tcl default)", V / "vitis/m6_sr_0602/m6_sr.runs/impl_1/design_1_wrapper.bit")],
                      xsa=V / "vitis/m6_sr_0602/design_1_wrapper.xsa"),
    "R2q": dict(tree=V / "sandbox_R2q", version_expected="0x53522201", bits=[("sandbox build (tree default)", V / "R2q_artifacts/design_1_wrapper_R2q.bit")],
                xsa=V / "R2q_artifacts/design_1_wrapper_R2q.xsa"),
    "R3q": dict(tree=V / "sandbox_R3q", version_expected="0x53523201", bits=[("sandbox build (tree default)", V / "R3q_artifacts/design_1_wrapper_R3q.bit")],
                xsa=V / "R3q_artifacts/design_1_wrapper_R3q.xsa"),
    # After R3q (branch r0_125): deployed network, one more register per engine run, fabric clock 125 MHz.  Timing numbers here are PREDICTIONS (fmax_plan.md), not board values.
    "R0 at 125 MHz (r0_125)": dict(tree=V / "sandbox_R0_125", version_expected="0x53524201", bits=[("sandbox build (tree default)", V / "R0_125_artifacts/design_1_wrapper_R0_125.bit")],
                                   xsa=V / "R0_125_artifacts/design_1_wrapper_R0_125.xsa",
                                   cycles="926,214-926,245 (the R0 window of 926,210-926,241 plus the 4 extra cycles per tile of simulation: 926,201 -> 926,205)",
                                   t3="PREDICTED 1,061.8 ms (model, `docs/paper/fmax_plan.md`); plausible range **1,033-1,064 ms** (lower end = core cycles at 125 MHz 1,000.3 ms + ARM padding/copies 32.3 ms, i.e. the DMA handshake overhead would have to vanish; upper end = prediction + 2 ms); max - min <= 3 ms; output fnv as in the T2 row"),
}
ELFS = [("T1 golden tile", "sr_app_t1.elf"), ("T2 full frame", "sr_app_t2.elf"), ("T3 timing, 20 frames", "sr_app_t3_20f.elf"),
        ("T3 timing, 200 frames (power)", "sr_app_t3_200f.elf"), ("T7 ARM only, 1 frame", "sr_app_t11.elf"), ("T7 ARM only, 20 frames (power)", "sr_app_t11_20f.elf")]

# runs inside each tree with that tree's own modules
PROBE = r'''
import json, re, sys
from pathlib import Path
root = Path(".").resolve()
sys.path.insert(0, str(root / "software/ai")); sys.path.insert(0, str(root / "software/host_tools"))
import numpy as np
from quantization.integer_reference import QNet, upscale, run_tile
from srim import read_srim, fnv1a32
net = QNet.load(root / "software/ai/quantization/qparams.npz")
txt = (root / "software/board/sr_app/golden_tile.h").read_text()
def arr(name):
    m = re.search(name + r"\[\d+\][^{]*\{(.*?)\};", txt, re.S)
    return np.array([int(x, 16) for x in re.findall(r"0x[0-9a-fA-F]{2}", m.group(1))], dtype=np.uint8)
gin, gout = arr("sr_golden_in"), arr("sr_golden_out")
tile = run_tile(net, gin.reshape(70, 70, 3)).reshape(-1)
res = dict(t1_in_bytes=int(gin.size), t1_out_bytes=int(gout.size), t1_header_fnv=fnv1a32(gout.tobytes()), t1_model_fnv=fnv1a32(tile.tobytes()), t1_model_equals_header=bool(np.array_equal(tile, gout)))
for key, lr, exp in (("t2", "div2k_img0193_lr_960x540", "div2k_img0193_expected_1920x1080"), ("baboon", "set14_baboon_lr_128x128", "set14_baboon_expected_256x256")):
    out = upscale(net, read_srim(root / f"data/board/{lr}.raw"))
    ex = read_srim(root / f"data/board/{exp}.raw")
    res[key + "_shape"] = list(out.shape); res[key + "_model_fnv"] = fnv1a32(out.tobytes()); res[key + "_file_fnv"] = fnv1a32(ex.tobytes()); res[key + "_model_equals_file"] = bool(np.array_equal(out, ex))
print("PROBE_JSON " + json.dumps(res))
'''


def md5(p):
    return hashlib.md5(Path(p).read_bytes()).hexdigest() if Path(p).exists() else "MISSING"


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--md", default=None)
    a = ap.parse_args()
    lines, bad = [], []
    for name, d in TREES.items():
        t = d["tree"]
        r = subprocess.run([str(t / ".venv/bin/python"), "-I", "-c", "import sys; sys.argv=['x']\n" + PROBE], cwd=t, capture_output=True, text=True)
        js = [l for l in r.stdout.splitlines() if l.startswith("PROBE_JSON ")]
        if r.returncode or not js:
            bad.append(f"{name}: probe failed: {r.stderr[-400:]}")
            continue
        p = json.loads(js[0][len("PROBE_JSON "):])
        rtl = (t / "hardware/rtl/top/sr_accel_top.v").read_text()
        ver = re.search(r"localparam \[31:0\] VERSION\s*=\s*32'h([0-9a-fA-F_]+);", rtl)
        ver = "0x" + ver.group(1).replace("_", "").lower() if ver else "NOT FOUND"
        ok = (p["t1_model_equals_header"] and p["t2_model_equals_file"] and p["baboon_model_equals_file"] and p["t1_header_fnv"] == p["t1_model_fnv"]
              and ver == d["version_expected"] and p["t2_shape"] == [1080, 1920, 3] and p["baboon_shape"] == [256, 256, 3])
        if not ok:
            bad.append(f"{name}: cross-check failed: {p}, RTL VERSION {ver}")
        lines += [f"## {name}", "", f"Tree `{t}`. Cross-checks (model re-run in this tree vs the files the board test uses): T1 {'OK' if p['t1_model_equals_header'] else 'FAIL'}, "
                  f"T2 {'OK' if p['t2_model_equals_file'] else 'FAIL'}, baboon {'OK' if p['baboon_model_equals_file'] else 'FAIL'}, RTL VERSION constant in the tree `{ver}` "
                  f"({'= expected' if ver == d['version_expected'] else 'DIFFERS from ' + d['version_expected']}).", "",
                  "| Quantity | Expected on the board |", "|---|---|",
                  f"| `version=` in every stats file / `init ok: VERSION` on the UART | **{d['version_expected']}** |",
                  f"| T1 golden tile: `result=0`, stat6 (identical repeats) | 0 and **20**; the ARM compares {p['t1_out_bytes']} output bytes with the golden tile itself (FNV-1a 32 of that tile: `0x{p['t1_model_fnv']:08x}`) |",
                  f"| T1 CYCLES (stat0..2 = min/max/mean) | each within **{d.get('cycles', '926,210-926,241 (simulation 926,201 + 1 for the wrapper = 926,202)')}** |",
                  f"| T2 960x540 -> 1920x1080 (135 tiles): `fnv1a32=` in marker and stats, `compare_raw.py` | **0x{p['t2_model_fnv']:08x}**, `BYTE-EXACT: yes`, `bytes=6220816` (16-byte header + 6,220,800) |",
                  f"| 128x128 -> 256x256 baboon (4 tiles) | **0x{p['baboon_model_fnv']:08x}** |",
                  "| T3 20 frames | " + d.get("t3", "mean within +-2 ms of 1,311.9 ms, max - min <= 3 ms, CYCLES 926,210-926,241, output fnv as in the T2 row") + " |",
                  "| T7 (ARM only, 1 frame) | `BYTE-EXACT: yes`, fnv as in the T2 row; time per frame **unknown** (never run) |", ""]
        lines += ["| Artifact | Path | md5 |", "|---|---|---|"]
        for lab, b in d["bits"]:
            lines.append(f"| bitstream, {lab} | `{b}` | `{md5(b)}` |")
        lines.append(f"| xsa | `{d['xsa']}` | `{md5(d['xsa'])}` |")
        # golden_tile.h is regenerated by a script (same content, new mtime), so it is checked by CONTENT: the ELF must contain the header's input and output bytes
        gtxt = (t / "software/board/sr_app/golden_tile.h").read_text()
        garr = {n: bytes(int(x, 16) for x in re.findall(r"0x[0-9a-fA-F]{2}", re.search(n + r"\[\d+\][^{]*\{(.*?)\};", gtxt, re.S).group(1))) for n in ("sr_golden_in", "sr_golden_out")}
        # sr_weights.h is generated too (test_swmodel.sh rewrites it, same content, new mtime): only the T7 ELFs contain it, checked by content (all four int8 weight arrays)
        wtxt = (t / "software/board/sr_app/sr_weights.h").read_text()
        wbytes = [bytes(int(v) & 0xFF for v in re.findall(r"-?\d+", re.search(r"sr_L%d_w\[\d+\]\s*=\s*\{(.*?)\};" % n, wtxt, re.S).group(1))) for n in (1, 2, 3, 4)]
        srcs = [p_ for p_ in list((t / "software/board/sr_app").glob("*")) + [t / "software/board/sr_regs.h"] if p_.is_file() and p_.name not in ("golden_tile.h", "sr_weights.h")]
        for lab, e in ELFS:
            ep = t / "software/board/build" / e
            newer = [s.name for s in srcs if ep.exists() and s.stat().st_mtime > ep.stat().st_mtime]
            blob = ep.read_bytes() if ep.exists() else b""
            has_gold = all(v in blob for v in garr.values())
            is_t7 = e.startswith("sr_app_t11")
            has_w = all(w in blob for w in wbytes) if is_t7 else True
            note = (f" **sources newer than the ELF: {', '.join(newer)}**" if newer else "") + ("" if has_gold else " **ELF does not contain the current golden tile**") \
                + ("" if has_w else " **ELF does not contain the current weights**")
            if newer or not has_gold or not has_w:
                bad.append(f"{name}: {e}: newer sources {newer}, golden tile embedded: {has_gold}, weights embedded: {has_w}")
            lines.append(f"| ELF {lab} (current golden tile embedded: {'yes' if has_gold else 'NO'}" + (f"; current weights embedded: {'yes' if has_w else 'NO'}" if is_t7 else "") + f") | `{ep}` | `{md5(ep)}`{note} |")
        lines.append("")
    head = ["# Expected board answers (pass / fail on the day)", "",
            "Generated by `software/analysis/board_expected.py` on the PC (model re-run in each tree). These are the values the board MUST print; **nothing in this file was measured on the board in this session.**",
            "The CYCLES window and the frame-time rule come from `docs/paper/board_checklist.md` section 5b (proposed merge criteria, the owner confirms): "
            "CYCLES per tile 926,210-926,241 (`docs/paper/rehearsal_2026-10-13_notes.md`, `results/speed/m7_timing_20frames.md`); 20-frame mean within +-2 ms of 1,311.9 ms and max - min <= 3 ms "
            "(R0 measured: 1,311.9 ms, `results/speed/m7_timing_20frames.md`).", "",
            "How to read a stats file: `result=0` is required; `fnv1a32=` is the checksum; `stat0..` meanings are in `software/board/README.md` (stats block). Compare the output file with `compare_raw.py` (exit code 0 = byte-exact).", ""]
    out = "\n".join(head + lines + (["## Cross-check problems", ""] + [f"* {b}" for b in bad] if bad else []) + [""])
    print(out)
    if a.md:
        Path(a.md).write_text(out)
    return 1 if bad else 0


if __name__ == "__main__":
    sys.exit(main())
