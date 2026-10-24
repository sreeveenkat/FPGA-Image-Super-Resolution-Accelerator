# Paper draft (skeleton, 2026-10-24)

* `main.tex`: IEEE conference skeleton (`IEEEtran`): Abstract, Introduction, Related Work, Model, Quantization, Architecture, Results, Discussion. Filled: Model, Quantization, Results (tables with a source file named in the comment next to each). Skeleton only: Introduction, Related Work, Architecture, Discussion.
* `refs.bib`: only FSRCNN (the one paper that has been read; the others in `docs/paper/related_work_and_venues.md` must be read before they are cited).
* `check_tex.py`: structural check (braces, `\begin`/`\end`, `\ref`/`\label`, `\cite` keys, table cell counts). **It is not a compile.**

**Compiled? No.** No TeX distribution is installed on this PC (`pdflatex`, `xelatex`, `latexmk`, `tectonic` are all missing; `kpsewhich` exists but there is no `IEEEtran.cls`), and installing one needs `sudo`.
To build: install TeX Live (`texlive-publishers` has IEEEtran, `texlive-latex-extra`, `texlive-bibtex-extra`), then `cd docs/paper/draft && pdflatex main && bibtex main && pdflatex main && pdflatex main`.
Expect to fix small things on the first real compile (the structural check cannot see package or class errors).

Rules for this draft: baseline = the **deployed checkpoint** (INT8 35.02 / 31.40 / 30.53 dB PSNR-Y), not the 2-seed R0 mean of the ladder study; every R2q / R3q board number is "pending board run" until the board session
(`docs/paper/board_session_runbook.md`); power is a Vivado estimate; predictions (cycle model) must be labelled as predictions. Venue, page limit and review type are not chosen.
