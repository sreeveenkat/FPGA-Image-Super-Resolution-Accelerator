"""Mutation test of the anchor RTL (R3q): apply ONE deliberate defect to a copy of an RTL file, run the quick anchor tests, and require that some test FAILS.
Run from anywhere:  .venv/bin/python hardware/verification/mutate_anchor.py [--seam]      (~3 min; --seam also runs the 20-tile seam set for survivors)
A mutant that no test catches is printed as SURVIVED; known-equivalent mutants are listed as such in MUTANTS (marked EQUIV) and must really survive.
Exit code 0 only if every non-equivalent mutant was caught and every EQUIV mutant survived (so that a wrong "equivalent" claim is noticed too).
"""
import re
import shutil
import subprocess
import sys
import tempfile
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]
RTL = ROOT / "hardware" / "rtl"
TB = ROOT / "hardware" / "verification" / "tb"
SEAM = ROOT / "data" / "golden" / "seam"

# (file, old, new, description, expect) ; expect = "caught" or "equiv"
MUTANTS = [
    ("common/requant.v", "a1 <= ADD_EN ? add : 8'd0;", "a1 <= 8'd0;", "anchor add ignored", "caught"),
    ("common/requant.v", "({41'd0, a1} << SHIFT)", "({41'd0, a1} << (SHIFT - 1))", "add shifted by SHIFT-1", "caught"),
    ("common/requant.v", "s2 <= p1 + rndx;", "s2 <= p1 - (rndx - RND) + RND - (rndx - RND);", "add subtracted instead of added", "caught"),
    ("common/requant.v", "wire signed [48:0] rndx = ADD_EN ? (RND | ({41'd0, a1} << SHIFT)) : RND;", "wire signed [48:0] rndx = ADD_EN ? ({41'd0, a1} << SHIFT) : RND;", "rounding bit dropped in anchor mode", "caught"),
    ("common/requant.v", "a1 <= ADD_EN ? add : 8'd0;", "a1 <= ADD_EN ? (add >> 1) : 8'd0;", "add halved", "caught"),
    ("common/requant.v", "else if (shifted > 255) y <= 8'd255;", "else if (shifted > 255) y <= shifted[7:0];", "no upper saturation (wraps)", "caught"),
    ("common/requant.v", "RND | ({41'd0, a1} << SHIFT)", "RND + ({41'd0, a1} << SHIFT)", "OR replaced by + (bits are disjoint)", "equiv"),
    ("conv_engine/conv_engine.v", "anc_a <= ANC_OFF * ANC_W + ANC_OFF;", "anc_a <= (ANC_OFF - 1) * ANC_W + ANC_OFF;", "halo offset: one row too high", "caught"),
    ("conv_engine/conv_engine.v", "anc_a <= ANC_OFF * ANC_W + ANC_OFF;", "anc_a <= ANC_OFF * ANC_W + ANC_OFF - 1;", "halo offset: one column too left", "caught"),
    ("conv_engine/conv_engine.v", "localparam ANC_ROWSTEP = ANC_W - OW + 1;", "localparam ANC_ROWSTEP = ANC_W - OW;", "row step off by one", "caught"),
    ("conv_engine/conv_engine.v", "if (anc_x == OW - 1) begin anc_x <= 0;", "if (anc_x == OW - 2) begin anc_x <= 0;", "row wrap one pixel early", "caught"),
    ("conv_engine/conv_engine.v", "case (rq_i[3:2])", "case (rq_i[1:0])", "colour from the sub-pixel index instead of k>>2", "caught"),
    ("conv_engine/conv_engine.v", "2'd0:    rq_add_r <= ANCHOR ? anc_data[7:0]   : 8'd0;", "2'd0:    rq_add_r <= ANCHOR ? anc_data[23:16] : 8'd0;", "R and B swapped", "caught"),
    ("conv_engine/conv_engine.v", "default: rq_add_r <= ANCHOR ? anc_data[23:16] : 8'd0;", "default: rq_add_r <= ANCHOR ? anc_data[15:8] : 8'd0;", "blue uses green", "caught"),
    ("conv_engine/conv_engine.v", "if (rst || (start && !busy)) begin\n            anc_x <= 0;", "if (rst) begin\n            anc_x <= 0;", "anchor address not restarted on start (2nd tile)", "caught"),
    ("conv_engine/conv_engine.v", "end else if (wr_pend) begin\n            if (anc_x", "end else if (rq_v) begin\n            if (anc_x", "anchor address advances per requantized byte, not per word", "caught"),
    ("conv_engine/conv_engine.v", ".add(rq_add_r)", ".add(8'd0)", "requantizer gets no anchor pixel", "caught"),
    ("conv_engine/conv_engine.v", ".ADD_EN(ANCHOR)", ".ADD_EN(1'b0)", "ADD_EN off", "caught"),
    ("sr_core/sr_tile_core.v", "(ANCHOR != 0 && state == S_L4) ? anc_raddr : r0_raddr_e1", "(ANCHOR != 0 && state == S_L3) ? anc_raddr : r0_raddr_e1", "ram0 read port switched in the wrong state", "caught"),
    ("sr_core/sr_tile_core.v", "(ANCHOR != 0 && state == S_L4) ? anc_raddr : r0_raddr_e1", "r0_raddr_e1", "anchor address never reaches ram0", "caught"),
    ("sr_core/sr_tile_core.v", ".ANC_W(IW1)", ".ANC_W(IW2)", "anchor row stride of the 72-pixel layer-1 output", "caught"),
    ("sr_core/sr_tile_core.v", ".ANC_OFF(3)", ".ANC_OFF(2)", "halo offset 2 instead of 3", "caught"),
    ("sr_core/sr_tile_core.v", ".ANC_OFF(3)", ".ANC_OFF(4)", "halo offset 4 instead of 3", "caught"),
    ("sr_core/sr_tile_core.v", ".anc_data(r0_rdata)", ".anc_data(24'd0)", "layer 4 gets no anchor data", "caught"),
    ("sr_core/sr_tile_core.v", "parameter ANCHOR = 1,", "parameter ANCHOR = 0,", "core default ANCHOR = 0", "caught"),
    ("sr_core/sr_tile_core.v", "parameter SHIFT4 = 25,", "parameter SHIFT4 = 24,", "core default SHIFT4 wrong", "caught"),
]

COMMON = ["common/mac_unit.v", "common/requant.v", "common/tile_ram.v", "common/weight_rom.v", "conv_engine/conv_engine.v"]
CORE = ["common/mac_unit.v", "common/requant.v", "common/weight_rom.v", "common/tile_ram_split.v", "conv_engine/conv_engine.v", "sr_core/sr_tile_core.v"]


def sh(cmd, **kw):
    return subprocess.run(cmd, cwd=ROOT, capture_output=True, text=True, **kw)


def build_run(tmp, name, files, tb, params, plus):
    vvp = tmp / f"{name}.vvp"
    r = sh(["iverilog", "-g2012", "-I", ".", "-o", str(vvp)] + sum([["-P", p] for p in params], []) + files + [str(TB / tb)])
    if r.returncode != 0:
        return "build error", r.stderr.strip().splitlines()[:2]
    out = sh(["vvp", str(vvp)] + plus, timeout=600).stdout
    ok = "PASS" in out and "FAIL" not in out
    return ("pass" if ok else "FAIL"), [l for l in out.splitlines() if "FAIL" in l][:1]


def suite(tmp, mut, files_override):
    def f(lst):
        return [str(files_override.get(x, RTL / x)) for x in lst]
    yield "requant_add s22", build_run(tmp, "ra22", f(["common/requant.v"]), "tb_requant_add.v", ["tb_requant_add.SHIFT=22"], [])
    yield "requant_add s25", build_run(tmp, "ra25", f(["common/requant.v"]), "tb_requant_add.v", ["tb_requant_add.SHIFT=25"], [])
    yield "layer4 small12", build_run(tmp, "l4", f(COMMON), "tb_conv_layer.v", ["tb_conv_layer.LAYER=4", "tb_conv_layer.HC=6"], ["+TILE=small12"])
    yield "layer4 random anchor", build_run(tmp, "l4r", f(COMMON), "tb_conv_layer.v",
                                            ["tb_conv_layer.LAYER=4", "tb_conv_layer.HC=6", "tb_conv_layer.HH=4", "tb_conv_layer.RAND=1", "tb_conv_layer.ANCHOR=1"], [])
    yield "core small12", build_run(tmp, "core", f(CORE), "tb_sr_tile.v", ["tb_sr_tile.HC=6"], ["+TILE=small12", "+TILE2=small12b"])


def seam_suite(tmp, files_override):
    files = [str(files_override.get(x, RTL / x)) for x in CORE]
    vvp = tmp / "seam8.vvp"
    r = sh(["iverilog", "-g2012", "-I", ".", "-o", str(vvp), "-P", "tb_sr_tile.HC=8"] + files + [str(TB / "tb_sr_tile.v")])
    if r.returncode != 0:
        return "build error", []
    for fin in sorted(SEAM.glob("hc8_t*_in.hex"))[:6]:
        b = fin.name[:-7]
        out = sh(["vvp", str(vvp), "+NOEXTRA", f"+IN={fin}", f"+OUT={SEAM / (b + '_out.hex')}"]).stdout
        if "FAIL" in out or "PASS" not in out:
            return "FAIL", [b]
    return "pass", []


def main():
    use_seam = "--seam" in sys.argv
    if use_seam and not any(SEAM.glob("hc8_t*_in.hex")):
        sh([str(ROOT / ".venv/bin/python"), "software/ai/quantization/seam_test.py", "gen", "--hc", "8", "--h", "37", "--w", "29"])
    tmp = Path(tempfile.mkdtemp())
    # sanity: the pristine design must pass the whole suite
    base = list(suite(tmp, None, {}))
    if any(r[0] != "pass" for _, r in base):
        print("PRISTINE DESIGN FAILS:", base)
        sys.exit(2)
    print("pristine: all", len(base), "anchor tests pass")
    bad = 0
    for n, (rel, old, new, desc, expect) in enumerate(MUTANTS, 1):
        src = (RTL / rel).read_text()
        assert src.count(old) >= 1, f"mutant {n}: pattern not found in {rel}: {old!r}"
        mdir = tmp / f"m{n}"
        mdir.mkdir()
        mf = mdir / Path(rel).name
        mf.write_text(src.replace(old, new, 1))
        res = list(suite(tmp, n, {rel: mf}))
        caught = [(nm, r) for nm, r in res if r[0] != "pass"]
        if not caught and use_seam:
            r = seam_suite(tmp, {rel: mf})
            if r[0] != "pass":
                caught = [("seam hc=8", r)]
        status = "caught" if caught else "survived"
        invalid = [c for c in caught if c[1][0] == "build error"]
        by = ", ".join(f"{nm}" for nm, _ in caught) or "-"
        ok = (status == expect) or (expect == "equiv" and status == "survived")
        print(f"{'OK ' if ok else 'BAD'} mutant {n:2d} [{rel}] {desc}: {status.upper()}{' (build error: invalid mutant)' if invalid else ''}  <- {by}")
        if not ok or invalid:
            bad += 1
    shutil.rmtree(tmp, ignore_errors=True)
    print(f"{'FAIL' if bad else 'PASS'} anchor mutation test: {len(MUTANTS)} mutants, {bad} problems")
    sys.exit(1 if bad else 0)


if __name__ == "__main__":
    main()
