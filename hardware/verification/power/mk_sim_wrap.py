#!/usr/bin/env python3
"""Writes sim_design_1.v: module sim_design_1 with the ports of design_1_sr_accel_top_0_0 and one instance named sr_accel_top_0 inside, so that the SAIF hierarchy is
tb_power/design_1_i/sr_accel_top_0/inst/...  (the block design's own path is design_1_i/sr_accel_top_0/inst).  Usage: mk_sim_wrap.py <ip_funcsim.v> <out.v>"""
import re, sys
src = open(sys.argv[1]).read()
m = re.search(r"module design_1_sr_accel_top_0_0\s*\((.*?)\);", src, re.S)
ports = [p.strip() for p in m.group(1).split(",")]
decl = []
for p in ports:
    d = re.search(r"\b(input|output)\s*(\[[^\]]+\])?\s*" + re.escape(p) + r"\s*;", src)
    decl.append(f"    {d.group(1)} {d.group(2) or ''} {p};")
body = "`timescale 1ns/1ps\nmodule sim_design_1 (" + ", ".join(ports) + ");\n" + "\n".join(decl) + "\n    design_1_sr_accel_top_0_0 sr_accel_top_0 (" + ", ".join(f".{p}({p})" for p in ports) + ");\nendmodule\n"
open(sys.argv[2], "w").write(body)
print("ports", len(ports))
