#!/usr/bin/env python3
"""Structural check of main.tex when no TeX is installed (it is NOT a compile): braces balanced, \\begin/\\end paired and nested, every \\ref has a \\label,
every \\cite key is in refs.bib, table column counts (&) match the tabular spec on every row.   Usage: python3 docs/paper/draft/check_tex.py   (exit 0 = OK)"""
import re
import sys
from pathlib import Path

d = Path(__file__).resolve().parent
src = (d / "main.tex").read_text()
bib = (d / "refs.bib").read_text()
text = "\n".join(re.sub(r"(?<!\\)%.*", "", l) for l in src.splitlines())   # drop comments (an escaped \% stays)
errs = []

depth = 0
for i, ch in enumerate(re.sub(r"\\[{}]", "", text)):
    depth += (ch == "{") - (ch == "}")
    if depth < 0:
        errs.append(f"closing brace without opening one near char {i}")
        break
if depth > 0:
    errs.append(f"{depth} unclosed '{{'")

stack = []
for m in re.finditer(r"\\(begin|end)\{([^}]+)\}", text):
    if m.group(1) == "begin":
        stack.append(m.group(2))
    elif not stack or stack.pop() != m.group(2):
        errs.append(f"\\end{{{m.group(2)}}} does not match")
if stack:
    errs.append(f"unclosed environments: {stack}")

labels = set(re.findall(r"\\label\{([^}]+)\}", text))
for r in re.findall(r"\\ref\{([^}]+)\}", text):
    if r not in labels:
        errs.append(f"\\ref{{{r}}} has no \\label")
keys = set(re.findall(r"@\w+\{([^,]+),", bib))
for c in re.findall(r"\\cite\{([^}]+)\}", text):
    for k in c.split(","):
        if k.strip() not in keys:
            errs.append(f"\\cite key {k.strip()} not in refs.bib")

for m in re.finditer(r"\\begin\{tabular\}\{([^}]*)\}(.*?)\\end\{tabular\}", text, re.S):
    ncol = len(re.findall(r"[lcr]|p\{", m.group(1)))
    for row in [r for r in m.group(2).split("\\\\") if "&" in r or r.strip() and not r.strip().startswith("\\")]:
        row = re.sub(r"\\(toprule|midrule|bottomrule)", "", row).strip()
        if row and row.count("&") != ncol - 1:
            errs.append(f"table row has {row.count('&') + 1} cells, spec has {ncol}: {row[:60]}")

n_tab = len(re.findall(r"\\begin\{table\}", text))
print(f"main.tex: {n_tab} tables, {len(labels)} labels, {len(keys)} bib entries; " + ("OK" if not errs else f"{len(errs)} PROBLEM(S)"))
for e in errs:
    print("  -", e)
sys.exit(1 if errs else 0)
