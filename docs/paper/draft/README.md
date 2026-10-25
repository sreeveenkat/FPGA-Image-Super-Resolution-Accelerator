# Paper draft (2026-10-24 skeleton, compiled 2026-10-25)

* `main.tex`: IEEE conference skeleton (`IEEEtran`): Abstract, Introduction, Related Work, Model, Quantization, Architecture, Results, Discussion. Filled: Model, Quantization, Results (tables with a source file named in the comment next to each). Skeleton only: Introduction, Related Work, Architecture, Discussion.
* `refs.bib`: only FSRCNN (the one paper that has been read; the others in `docs/paper/related_work_and_venues.md` must be read before they are cited).
* `check_tex.py`: structural check (braces, `\begin`/`\end`, `\ref`/`\label`, `\cite` keys, table cell counts). **It is not a compile.**

**Compiled? Yes (2026-10-25).** `./build.sh [outdir]` runs pdflatex, bibtex, pdflatex, pdflatex with IEEEtran and prints the page count and the remaining warnings (default output `build/`, git-ignored). The TeX Live used was installed in user space (`~/texlive/2026`, scheme-basic plus `ieeetran`, `collection-latexrecommended`, `collection-fontsrecommended`); put `~/texlive/2026/bin/x86_64-linux` on `PATH`. The system packages on this PC (`texlive-base`, `texlive-binaries`) have no LaTeX format and no IEEEtran.
Page count and warnings of the last build: see the commit message of the build and `build.sh` output; the page limit of a venue is not known.

Rules for this draft: baseline = the **deployed checkpoint** (INT8 35.02 / 31.40 / 30.53 dB PSNR-Y), not the 2-seed R0 mean of the ladder study; every R2q / R3q board number is "pending board run" until the board session
(`docs/paper/board_session_runbook.md`); power is a Vivado estimate; predictions (cycle model) must be labelled as predictions. Venue, page limit and review type are not chosen.
