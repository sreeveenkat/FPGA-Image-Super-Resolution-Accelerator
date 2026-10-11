"""Fails if software/board/sr_regs.h, hardware/rtl/top/sr_accel_top.v, hardware/rtl/axi_wrapper/sr_axis_wrapper.v and docs/REGISTER_MAP.md disagree.

The C header is evaluated by gcc (so expressions like (SR_HC + 2u*SR_HALO) are real values); the Verilog is parsed with regular expressions that are tied to the
way sr_accel_top.v is written.  If the Verilog is restructured and a pattern no longer matches, the test FAILS (it never passes vacuously).
Run from the project root:  python3 software/board/test_regs.py
"""
import os
import re
import subprocess
import sys
import tempfile

ROOT = os.path.abspath(os.path.join(os.path.dirname(__file__), "..", ".."))
V_TOP = os.path.join(ROOT, "hardware/rtl/top/sr_accel_top.v")
V_WRAP = os.path.join(ROOT, "hardware/rtl/axi_wrapper/sr_axis_wrapper.v")
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


def c_values(names):
    src = '#include <stdio.h>\n#include "sr_regs.h"\nint main(void){\n' + "".join(f'printf("{n}=%lu\\n",(unsigned long)({n}));\n' for n in names) + "return 0;}\n"
    with tempfile.TemporaryDirectory() as d:
        c = os.path.join(d, "t.c")
        open(c, "w").write(src)
        subprocess.run(["gcc", "-Wall", "-Werror", "-std=c99", "-I", os.path.dirname(H), c, "-o", os.path.join(d, "t")], check=True)
        out = subprocess.run([os.path.join(d, "t")], check=True, capture_output=True, text=True).stdout
    return {k: int(v) for k, v in (l.split("=") for l in out.split())}


DBG = {"DBG_IN_BEATS": "dbg_in_beats", "DBG_TLAST_AT": "dbg_tlast_at", "DBG_START2BEAT": "dbg_s2b", "DBG_PRE_BEATS": "dbg_pre",
       "DBG_STARTS": "{dbg_starts_ign, dbg_starts_ok}", "DBG_ERR_BEATS": "dbg_err_beats", "DBG_ERR_CYCLES": "dbg_err_cyc"}
NAMES = ["SR_REG_CONTROL", "SR_REG_STATUS", "SR_REG_TILE_SIZE", "SR_REG_CYCLES", "SR_REG_ERROR_CODE", "SR_REG_VERSION",
         *[f"SR_REG_{n}" for n in DBG],
         "SR_CTRL_START", "SR_CTRL_SRESET", "SR_STATUS_BUSY", "SR_STATUS_DONE", "SR_STATUS_ERROR",
         "SR_ERR_NONE", "SR_ERR_EARLY_TLAST", "SR_ERR_MISSING_TLAST", "SR_ERR_BAD_TKEEP",
         "SR_VERSION", "SR_HC", "SR_HALO", "SR_TILE_IN_W", "SR_TILE_OUT_W", "SR_TILE_IN_BYTES", "SR_TILE_OUT_BYTES"]
C = c_values(NAMES)

top = open(V_TOP).read()
wrap = open(V_WRAP).read()
doc = open(DOC).read()
code = re.sub(r"//.*", "", top)           # code without comments, for the behaviour patterns

# ---- VERSION and HC
m = must(r"localparam \[31:0\] VERSION = 32'h([0-9A-Fa-f_]+);", code, "VERSION")
if m:
    check(int(m.group(1).replace("_", ""), 16) == C["SR_VERSION"], f"VERSION: Verilog {m.group(1)} vs header 0x{C['SR_VERSION']:08x}")
m = must(r"parameter HC\s*=\s*(\d+)", code, "default HC")
HC = int(m.group(1)) if m else 0
check(HC == C["SR_HC"], f"HC: Verilog default {HC} vs SR_HC {C['SR_HC']}")
check(C["SR_TILE_IN_W"] == HC + 6 and C["SR_TILE_OUT_W"] == 2 * HC and C["SR_HALO"] == 3, "tile widths / halo")
check(C["SR_TILE_IN_BYTES"] == (HC + 6) ** 2 * 3, f"input tile bytes {C['SR_TILE_IN_BYTES']} vs (HC+6)^2*3 = {(HC + 6) ** 2 * 3}")
check(C["SR_TILE_OUT_BYTES"] == (2 * HC) ** 2 * 3, f"output tile bytes {C['SR_TILE_OUT_BYTES']} vs (2HC)^2*3 = {(2 * HC) ** 2 * 3}")
check((HC + 6) ** 2 * 3 % 4 == 0 and (2 * HC) ** 2 * 3 % 4 == 0, "tile byte counts must be multiples of 4 (32-bit beats)")

# ---- read map: case (s_axi_araddr[5:2]) entries
cases = dict()
for n, expr in re.findall(r"4'd(\d+):\s+rdata <= (.*?);", code):
    cases[int(n) * 4] = expr.strip()
check(len(cases) == 6 + len(DBG), f"expected {6 + len(DBG)} read-case entries, found {len(cases)}")
for n, expr in DBG.items():
    check(cases.get(C[f"SR_REG_{n}"]) == expr, f"{n} (offset 0x{C['SR_REG_' + n]:02x}): Verilog read value {cases.get(C['SR_REG_' + n])!r}, expected {expr!r}")
exp_reads = {"SR_REG_CONTROL": "32'd0", "SR_REG_TILE_SIZE": "HC", "SR_REG_CYCLES": "wrap_cycles", "SR_REG_ERROR_CODE": "{30'd0, err_code}", "SR_REG_VERSION": "VERSION"}
for name, expr in exp_reads.items():
    check(cases.get(C[name]) == expr, f"{name} (offset 0x{C[name]:02x}): Verilog read value {cases.get(C[name])!r}, expected {expr!r}")
st = cases.get(C["SR_REG_STATUS"], "")
m = re.fullmatch(r"\{29'd0,\s*(.*)\}", st)
if not m:
    errors.append(f"STATUS read expression not understood: {st!r}")
else:
    parts = [p.strip() for p in re.split(r",\s*(?![^()]*\))", m.group(1))]       # MSB first
    bits = {p: len(parts) - 1 - i for i, p in enumerate(parts)}
    check(bits.get("busy_st") == 0 and C["SR_STATUS_BUSY"] == 1 << 0, f"STATUS.busy bit: Verilog {bits.get('busy_st')} vs header 0x{C['SR_STATUS_BUSY']:x}")
    check(bits.get("done_s") == 1 and C["SR_STATUS_DONE"] == 1 << 1, f"STATUS.done bit: Verilog {bits.get('done_s')} vs header 0x{C['SR_STATUS_DONE']:x}")
    check(bits.get("(err_code != 2'd0)") == 2 and C["SR_STATUS_ERROR"] == 1 << 2, f"STATUS.error bit: Verilog {bits.get('(err_code != 2' + chr(39) + 'd0)')} vs header 0x{C['SR_STATUS_ERROR']:x}")

# ---- write side: CONTROL decode and bits
m = must(r"aw_addr\[5:2\]\s*==\s*4'd(\d+)\s*&&\s*w_strb\[0\]", code, "CONTROL write decode")
if m:
    check(int(m.group(1)) * 4 == C["SR_REG_CONTROL"], f"CONTROL write address: Verilog {int(m.group(1)) * 4} vs header {C['SR_REG_CONTROL']}")
m = must(r"start_r\s*<=\s*w_data\[(\d+)\]", code, "start bit")
if m:
    check(1 << int(m.group(1)) == C["SR_CTRL_START"], f"CONTROL.start bit: Verilog {m.group(1)} vs header 0x{C['SR_CTRL_START']:x}")
m = must(r"srst_r\s*<=\s*w_data\[(\d+)\]", code, "soft reset bit")
if m:
    check(1 << int(m.group(1)) == C["SR_CTRL_SRESET"], f"CONTROL.soft-reset bit: Verilog {m.group(1)} vs header 0x{C['SR_CTRL_SRESET']:x}")

# ---- error codes: wrapper flag -> code mapping in the top, flag meaning in the wrapper
m = must(r"if \(wrap_flags\[0\]\)\s*err_code <= 2'd(\d+);\s*else if \(wrap_flags\[1\]\)\s*err_code <= 2'd(\d+);\s*else if \(keep_bad\)\s*err_code <= 2'd(\d+);", code, "error-code mapping")
if m:
    early, missing, keep = map(int, m.groups())
    check(early == C["SR_ERR_EARLY_TLAST"], f"early-TLAST code: Verilog {early} vs header {C['SR_ERR_EARLY_TLAST']}")
    check(missing == C["SR_ERR_MISSING_TLAST"], f"missing-TLAST code: Verilog {missing} vs header {C['SR_ERR_MISSING_TLAST']}")
    check(keep == C["SR_ERR_BAD_TKEEP"], f"bad-TKEEP code: Verilog {keep} vs header {C['SR_ERR_BAD_TKEEP']}")
check(C["SR_ERR_NONE"] == 0, "SR_ERR_NONE must be 0")
wcode = re.sub(r"//.*", "", wrap)
check(re.search(r"s_axis_tlast && wcnt != NWI - 1\)\s*error_flags\[0\]", wcode) is not None, "wrapper flag[0] is no longer 'tlast on a non-last beat'")
check(re.search(r"!s_axis_tlast && wcnt == NWI - 1\)\s*error_flags\[1\]", wcode) is not None, "wrapper flag[1] is no longer 'missing tlast on the last beat'")
check(re.search(r"s_axis_tkeep != 4'hF", code) is not None, "tkeep check (!= 4'hF) not found in the top")

# ---- the comment table in the Verilog header and the document
tab = {n: int(o, 16) for o, n in re.findall(r"^//\s+(0x[0-9A-Fa-f]{2})\s+([A-Z0-9_]+)", top, re.M)}
names = {"CONTROL": "SR_REG_CONTROL", "STATUS": "SR_REG_STATUS", "TILE_SIZE": "SR_REG_TILE_SIZE", "CYCLES": "SR_REG_CYCLES", "ERROR_CODE": "SR_REG_ERROR_CODE", "VERSION": "SR_REG_VERSION",
         **{n: f"SR_REG_{n}" for n in DBG}}
for n, cn in names.items():
    check(tab.get(n) == C[cn], f"Verilog header comment: {n} at {tab.get(n)} vs header {C[cn]}")
    rows = re.findall(rf"\|\s*(0x[0-9A-Fa-f]{{2}})\s*\|\s*{n}\s*\|", doc)
    check(len(rows) == 1 and int(rows[0], 16) == C[cn], f"docs/REGISTER_MAP.md: {n} row {rows} vs header 0x{C[cn]:02x}")
check(f"0x{C['SR_VERSION']:08x}" in doc.lower().replace("0X", "0x"), "docs/REGISTER_MAP.md does not contain the VERSION value")
check("14,700" in doc and "49,152" in doc, "docs/REGISTER_MAP.md does not state the tile byte counts")

if errors:
    for e in errors:
        print("FAIL:", e)
    print(f"FAIL test_regs: {len(errors)} disagreement(s)")
    sys.exit(1)
print(f"PASS test_regs: sr_regs.h == sr_accel_top.v == REGISTER_MAP.md ({len(NAMES)} constants, {6 + len(DBG)} registers, HC={HC})")
