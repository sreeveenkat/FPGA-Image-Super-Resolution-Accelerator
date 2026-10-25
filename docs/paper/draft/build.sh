#!/usr/bin/env bash
# Build main.pdf into an output directory (default: ./build, git-ignored).  Needs pdflatex + bibtex + IEEEtran on PATH
# (a user-space TeX Live works: put its bin directory on PATH).   Usage: build.sh [outdir]
set -eu
cd "$(dirname "$0")"
OUT="${1:-build}"
mkdir -p "$OUT"
export BIBINPUTS="$PWD:"
pdflatex -interaction=nonstopmode -halt-on-error -output-directory="$OUT" main.tex > "$OUT/pass1.log"
openout_any=a bibtex "$OUT/main" > "$OUT/bibtex.log" || { cat "$OUT/bibtex.log"; exit 1; }
pdflatex -interaction=nonstopmode -halt-on-error -output-directory="$OUT" main.tex > "$OUT/pass2.log"
pdflatex -interaction=nonstopmode -halt-on-error -output-directory="$OUT" main.tex > "$OUT/pass3.log"
echo "pages: $(pdfinfo "$OUT/main.pdf" | awk '/^Pages:/{print $2}')"
echo "remaining warnings:"; grep -h -E "^LaTeX Warning|^Overfull|^Underfull|Package .* Warning" "$OUT/pass3.log" || echo "  none"
