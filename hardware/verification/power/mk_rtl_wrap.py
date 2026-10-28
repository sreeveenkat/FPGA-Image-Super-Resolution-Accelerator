#!/usr/bin/env python3
"""RTL stand-in for the IP netlist: module design_1_sr_accel_top_0_0 (same ports) with the RTL sr_accel_top as instance `inst`, so that the SAIF path of an RTL run is
the same as the netlist's: tb_power/design_1_i/sr_accel_top_0/inst/...   Usage: mk_rtl_wrap.py <ip_funcsim.v> <weights_dir/> <out.v> [HC]"""
import re, sys
src = open(sys.argv[1]).read(); wdir = sys.argv[2]; hc = sys.argv[4] if len(sys.argv) > 4 else None
m = re.search(r"module design_1_sr_accel_top_0_0\s*\((.*?)\);", src, re.S)
ports = [p.strip() for p in m.group(1).split(",")]
decl = []
for p in ports:
    d = re.search(r"\b(input|output)\s*(\[[^\]]+\])?\s*" + re.escape(p) + r"\s*;", src)
    decl.append(f"    {d.group(1)} {d.group(2) or ''} {p};")
par = f'.WDIR("{wdir}")' + (f", .HC({hc})" if hc else "")
open(sys.argv[3], "w").write("`timescale 1ns/1ps\nmodule design_1_sr_accel_top_0_0 (" + ", ".join(ports) + ");\n" + "\n".join(decl) + f"\n    sr_accel_top #({par}) inst (" + ", ".join(f".{p}({p})" for p in ports) + ");\nendmodule\n")
