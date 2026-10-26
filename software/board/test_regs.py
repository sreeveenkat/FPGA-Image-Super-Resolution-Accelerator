"""Fails if software/board/sr_regs.h, hardware/rtl/top/sr_accel_top.v (PIPELINE version, branch `pipe`) and docs/REGISTER_MAP.md disagree.

The C header is evaluated by gcc (so expressions are real values); the Verilog is parsed with regular expressions that are tied to the way sr_accel_top.v is
written.  If the Verilog is restructured and a pattern no longer matches, the test FAILS (it never passes vacuously).
Run from the project root:  python3 software/board/test_regs.py
"""
import os
import re
import subprocess
import sys
import tempfile

ROOT = os.path.abspath(os.path.join(os.path.dirname(__file__), "..", ".."))
V_TOP = os.path.join(ROOT, "hardware/rtl/top/sr_accel_top.v")
V_CORE = os.path.join(ROOT, "hardware/rtl/pipe/sr_pipe_core.v")
H = os.path.join(ROOT, "software/board/sr_regs.h")
DOC = os.path.join(ROOT, "docs/REGISTER_MAP.md")

errors = []


def check(cond, msg):
    if not cond:
        errors.append(msg)


def must(pattern, text, what, flags=0):
    m = re.search(pattern, text, flags)
    if not m:
        errors.append(f"cannot find {what} in the Verilog (pattern {pattern!r}) - the test needs updating if the RTL was restructured")
    return m


def c_values(names, exprs=()):
    src = '#include <stdio.h>\n#include "sr_regs.h"\nint main(void){\n' + "".join(f'printf("{n}=%lu\\n",(unsigned long)({n}));\n' for n in names)
    src += "".join(f'printf("{k}=%lu\\n",(unsigned long)({e}));\n' for k, e in exprs) + "return 0;}\n"
    with tempfile.TemporaryDirectory() as d:
        c = os.path.join(d, "t.c")
        open(c, "w").write(src)
        subprocess.run(["gcc", "-Wall", "-Werror", "-std=c99", "-I", os.path.dirname(H), c, "-o", os.path.join(d, "t")], check=True)
        out = subprocess.run([os.path.join(d, "t")], check=True, capture_output=True, text=True).stdout
    return {k: int(v) for k, v in (l.split("=") for l in out.split())}


REGS = ["CONTROL", "STATUS", "FRAME_W", "CYCLES", "ERROR_CODE", "VERSION", "FRAME_H", "MAX_W", "DBG_IN_BEATS", "DBG_OUT_BEATS"]
NAMES = [f"SR_REG_{n}" for n in REGS] + [
    "SR_CTRL_START", "SR_CTRL_SRESET", "SR_STATUS_BUSY", "SR_STATUS_DONE", "SR_STATUS_ERROR",
    "SR_ERR_NONE", "SR_ERR_EARLY_TLAST", "SR_ERR_MISSING_TLAST", "SR_ERR_BAD_TKEEP", "SR_ERR_BAD_SIZE", "SR_ERR_INTERNAL",
    "SR_VERSION", "SR_MAX_W", "SR_MAX_H", "SR_HALO", "SR_HC", "SR_TILE_IN_BYTES", "SR_TILE_OUT_BYTES"]
C = c_values(NAMES, [("IN_BEATS_960", "SR_FRAME_IN_BEATS(960u, 540u)"), ("OUT_BYTES_960", "SR_FRAME_OUT_BYTES(960u, 540u)"),
                     ("IN_BYTES_64", "SR_FRAME_IN_BYTES(64u, 64u)"), ("OUT_BYTES_64", "SR_FRAME_OUT_BYTES(64u, 64u)")])

top = open(V_TOP).read()
core = open(V_CORE).read()
doc = open(DOC).read()
code = re.sub(r"//.*", "", top)
ccode = re.sub(r"//.*", "", core)

# ---- VERSION, MAXW, frame sizes
m = must(r"localparam \[31:0\] VERSION = 32'h([0-9A-Fa-f_]+);", code, "VERSION")
if m:
    check(int(m.group(1).replace("_", ""), 16) == C["SR_VERSION"], f"VERSION: Verilog {m.group(1)} vs header 0x{C['SR_VERSION']:08x}")
m = must(r"parameter MAXW\s*=\s*(\d+)", code, "default MAXW")
MAXW = int(m.group(1)) if m else 0
check(MAXW - 6 == C["SR_MAX_W"], f"MAX_W: Verilog MAXW - 6 = {MAXW - 6} vs SR_MAX_W {C['SR_MAX_W']}")
check(C["SR_TILE_IN_BYTES"] == C["IN_BYTES_64"] == 14700 and C["SR_TILE_OUT_BYTES"] == C["OUT_BYTES_64"] == 49152, "golden tile = 64 x 64 frame sizes")
check(C["IN_BEATS_960"] == (3 * 966 * 546 + 3) // 4 and C["OUT_BYTES_960"] == 1920 * 1080 * 3, "frame size macros at 960 x 540")
must(r"nbi\s*<=\s*\(3 \* npix_p \+ 3\) >> 2;", ccode, "input beat count in sr_pipe_core")
must(r"pw_a <= fw \+ 16'd6; ph_a <= fh \+ 16'd6;", ccode, "padded size (W+6, H+6) in sr_pipe_core")
must(r"nbo  <= 3 \* nlr_p;", ccode, "output beat count 3WH in sr_pipe_core")

# ---- read map
cases = {int(n) * 4: e.strip() for n, e in re.findall(r"4'd(\d+):\s+rdata <= (.*?);", code)}
check(len(cases) == len(REGS), f"expected {len(REGS)} read-case entries, found {len(cases)}")
exp_reads = {"CONTROL": "32'd0", "FRAME_W": "{16'd0, frame_w}", "CYCLES": "core_cycles", "ERROR_CODE": "{29'd0, err_code}", "VERSION": "VERSION",
             "FRAME_H": "{16'd0, frame_h}", "MAX_W": "MAXW - 6", "DBG_IN_BEATS": "in_beats", "DBG_OUT_BEATS": "out_beats"}
for n, expr in exp_reads.items():
    off = C[f"SR_REG_{n}"]
    check(cases.get(off) == expr, f"{n} (offset 0x{off:02x}): Verilog read value {cases.get(off)!r}, expected {expr!r}")
st = cases.get(C["SR_REG_STATUS"], "")
m = re.fullmatch(r"\{29'd0,\s*(.*)\}", st)
if not m:
    errors.append(f"STATUS read expression not understood: {st!r}")
else:
    parts = [p.strip() for p in re.split(r",\s*(?![^()]*\))", m.group(1))]
    bits = {p: len(parts) - 1 - i for i, p in enumerate(parts)}
    check(bits.get("busy_st") == 0 and C["SR_STATUS_BUSY"] == 1, "STATUS.busy bit")
    check(bits.get("done_s") == 1 and C["SR_STATUS_DONE"] == 2, "STATUS.done bit")
    check(bits.get("(err_code != 3'd0)") == 2 and C["SR_STATUS_ERROR"] == 4, "STATUS.error bit")

# ---- write side
m = must(r"aw_addr\[5:2\]\s*==\s*4'd(\d+)\s*&&\s*w_strb\[0\]", code, "CONTROL write decode")
if m:
    check(int(m.group(1)) * 4 == C["SR_REG_CONTROL"], "CONTROL write address")
m = must(r"start_r\s*<=\s*w_data\[(\d+)\]", code, "start bit")
if m:
    check(1 << int(m.group(1)) == C["SR_CTRL_START"], "CONTROL.start bit")
m = must(r"srst_r\s*<=\s*w_data\[(\d+)\]", code, "soft reset bit")
if m:
    check(1 << int(m.group(1)) == C["SR_CTRL_SRESET"], "CONTROL.soft-reset bit")
for n, var in (("FRAME_W", "frame_w"), ("FRAME_H", "frame_h")):
    m = must(rf"if \(aw_addr\[5:2\] == 4'd(\d+)\) begin\s*if \(w_strb\[0\]\) {var}\[7:0\]\s*<= w_data\[7:0\];\s*if \(w_strb\[1\]\) {var}\[15:8\] <= w_data\[15:8\];", code, f"{n} write decode")
    if m:
        check(int(m.group(1)) * 4 == C[f"SR_REG_{n}"], f"{n} write address: Verilog {int(m.group(1)) * 4} vs header {C['SR_REG_' + n]}")

# ---- error codes
m = must(r"if \(start_r && !core_busy && !size_ok\) err_code <= 3'd(\d+);\s*else if \(core_flags\[0\]\)\s*err_code <= 3'd(\d+);\s*else if \(core_flags\[1\]\)\s*err_code <= 3'd(\d+);"
         r"\s*else if \(core_flags\[2\]\)\s*err_code <= 3'd(\d+);\s*else if \(core_flags\[3\]\)\s*err_code <= 3'd(\d+);", code, "error-code mapping")
if m:
    size, early, missing, keep, internal = map(int, m.groups())
    for got, name in ((size, "SR_ERR_BAD_SIZE"), (early, "SR_ERR_EARLY_TLAST"), (missing, "SR_ERR_MISSING_TLAST"), (keep, "SR_ERR_BAD_TKEEP"), (internal, "SR_ERR_INTERNAL")):
        check(got == C[name], f"{name}: Verilog {got} vs header {C[name]}")
check(C["SR_ERR_NONE"] == 0, "SR_ERR_NONE must be 0")
check(re.search(r"size_ok\s*=\s*\(frame_w != 16'd0\) && \(frame_w <= MAXW - 6\) && \(frame_h != 16'd0\) && \(frame_h <= MAXH\);", code) is not None, "frame-size rule in the top")
m = must(r"localparam\s+MAXH\s*=\s*(\d+);", code, "MAXH")
if m:
    check(int(m.group(1)) == C["SR_MAX_H"], f"MAXH: Verilog {m.group(1)} vs SR_MAX_H {C['SR_MAX_H']}")
check(re.search(r"if \(s_axis_tlast && in_beats != nbi - 1\) error_flags\[0\]", ccode) is not None, "core flag[0] is no longer 'tlast on a non-last beat'")
check(re.search(r"if \(!s_axis_tlast && in_beats == nbi - 1\) error_flags\[1\]", ccode) is not None, "core flag[1] is no longer 'missing tlast'")
check(re.search(r"if \(s_axis_tkeep != 4'hF\) error_flags\[2\]", ccode) is not None, "core flag[2] is no longer the tkeep check")

# ---- Verilog header comment table and the document
tab = {n: int(o, 16) for o, n in re.findall(r"^//\s+(0x[0-9A-Fa-f]{2})\s+([A-Z0-9_]+)", top, re.M)}
for n in REGS:
    cn = f"SR_REG_{n}"
    check(tab.get(n) == C[cn], f"Verilog header comment: {n} at {tab.get(n)} vs header {C[cn]}")
    rows = re.findall(rf"\|\s*(0x[0-9A-Fa-f]{{2}})\s*\|\s*{n}\s*\|", doc)
    check(len(rows) == 1 and int(rows[0], 16) == C[cn], f"docs/REGISTER_MAP.md: {n} row {rows} vs header 0x{C[cn]:02x}")
check(f"0x{C['SR_VERSION']:08x}" in doc.lower(), "docs/REGISTER_MAP.md does not contain the VERSION value")

if errors:
    for e in errors:
        print("FAIL:", e)
    print(f"FAIL test_regs: {len(errors)} disagreement(s)")
    sys.exit(1)
print(f"PASS test_regs: sr_regs.h == sr_accel_top.v (+ sr_pipe_core.v sizes) == REGISTER_MAP.md ({len(NAMES)} constants, {len(REGS)} registers, MAXW={MAXW})")
