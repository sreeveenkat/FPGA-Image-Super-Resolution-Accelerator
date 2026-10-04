# CLAUDE_AUTONOMOUS.md — rules for autonomous Claude Code runs

> `CLAUDE.md` already exists and is the project's running log (status, decisions, measured numbers). **Read it too**, and follow its
> rule "add one line to the Update Log after every change". This file only adds the autonomous-run rules and the verified commands.
> `HANDOFF.md` has the environment, GitHub rules and the next milestone (M5).

## Project
FPGA image super-resolution (x2, 960x540 -> 1920x1080) on a ZedBoard: a 2,620-parameter INT8 CNN is trained in PyTorch (software/ai),
quantized to a bit-exact NumPy integer model (the golden reference) and implemented in Verilog (hardware/). M1-M5 are done (software
baseline, FP32 model, INT8 + golden model, conv engine RTL, full tile core RTL); preparation of M6 (AXI wrapper in simulation) is next; M0/M6/M7 need the board, which is not available.

## Commands
All commands are run from the project root, with the venv Python: `.venv/bin/python`. Every command below was executed on 2026-10-04 and exited 0.

### Lint
```bash
.venv/bin/python -m pyflakes $(git ls-files -c -o --exclude-standard 'software/*.py')   # prints nothing, exit 0
```
There is no other linter or formatter (no Verilog linter, no black/ruff). `iverilog -Wall` runs inside `run_tests.sh`; its only warning is a harmless timescale note.

### Verify
Python (each prints one PASS line per test, 13 + 9 + 21 + 7 tests; `-W error` turns warnings into failures):
```bash
.venv/bin/python -W error software/ai/evaluation/test_baseline.py      # 13 PASS
.venv/bin/python -W error software/ai/evaluation/test_model.py         # 9 PASS
.venv/bin/python -W error software/ai/quantization/test_integer.py     # 21 PASS
.venv/bin/python -W error software/ai/quantization/test_export.py      # 7 PASS
python3 software/ai/quantization/check_export_independent.py           # pure-Python recompute of all golden tiles: "ALL OK: 10 tiles"
.venv/bin/python software/ai/dataset/check_dataset.py                  # "OK: ... no train/test overlap"
.venv/bin/python software/ai/dataset/check_lr_protocol.py              # "OK: LR protocol reproduces the official LR files"
.venv/bin/python software/ai/evaluation/check_target_res.py            # "OK"
```
RTL (Icarus Verilog 12; the script exits non-zero if any run prints FAIL or no PASS):
```bash
hardware/verification/run_tests.sh quick     # 29 runs, about 2 min   -> "== summary: 29 test runs passed, 0 failed (quick)"   (engine + tile core + 20-tile seam test)
hardware/verification/run_tests.sh full      # 73 runs, about 20 min -> "== summary: 73 test runs passed, 0 failed (full)"    (adds all real-size tiles and the real-size seam test)
hardware/verification/run_postsynth.sh       # needs Vivado 2024.1; simulates the synthesized netlists (4 layers + tile core), about 2.5 min -> "5 passed, 0 failed"
```
Results guard (after running any eval script; only tracked files are covered):
```bash
git diff --exit-code -- results/quality software/ai/quantization/qparams.npz   # exit 0 = results and parameters unchanged
```

**Which verify to run:** changed `software/ai/models|dataset|training|evaluation` -> the Python tests + dataset/LR/target checks; changed
`software/ai/quantization` -> all four Python tests + `check_export_independent.py` + `run_tests.sh quick`; changed anything in `hardware/rtl`,
`hardware/verification` or the exported weights -> `run_tests.sh full` AND `run_postsynth.sh`. When unsure, run everything.
After a change to RTL that is on a timing-critical path also re-run place and route and compare the slack (see the Vivado commands below).

### Run (regenerate things)
```bash
.venv/bin/python software/ai/evaluation/eval_baseline.py        # bicubic/nearest -> results/quality/baseline_x2.*
.venv/bin/python software/ai/evaluation/eval_model.py           # FP32 model     -> results/quality/model_fp32_x2.*
.venv/bin/python software/ai/evaluation/eval_int8.py            # INT8 model     -> results/quality/model_int8_x2.* (several min)
.venv/bin/python software/ai/evaluation/eval_int8.py --sweep    # quantization settings on VALIDATION images only (about 4 min)
.venv/bin/python software/ai/quantization/quantize.py [--out PATH]   # -> software/ai/quantization/qparams.npz (deterministic: re-run gives identical bytes)
.venv/bin/python software/ai/quantization/export_rtl.py         # -> hardware/rtl/weights/* and data/golden/* (git-ignored golden tiles)
.venv/bin/python software/ai/quantization/gen_unit_vectors.py   # -> data/golden/unit/* (requant vectors, randomized layers)
vivado -mode batch -nojournal -source hardware/vivado/scripts/synth_conv_engine.tcl -tclargs <layer 1-4> 10.0 [small|impl]   # after: source ~/Desktop/vivado_install/Vivado/2024.1/settings64.sh
vivado -mode batch -nojournal -source hardware/vivado/scripts/synth_sr_tile_core.tcl -tclargs 10.0 [small|impl]          # whole tile core (impl ~2 min)
.venv/bin/python software/ai/quantization/seam_test.py gen --hc 8 --h 37 --w 29    # seam test data (run_tests.sh does gen + simulate + check; "check" needs the RTL dumps)
```
Training smoke test (works, exit 0; NOT the real training): `.venv/bin/python software/ai/training/train.py --epochs 1 --steps 3 --images 192 --val 12 --threads 2 --out <scratch dir>/tiny.pt` (run once; wrote only the scratch file).
The real training command is in CLAUDE.md section 6c. **Never run it with `--out software/ai/checkpoints/srnet_fp32.pt`**: that checkpoint is frozen.

## Definition of done
The task is finished only when ALL of these hold in the same run:
1. The lint command and every verify command that applies to the changed area (see "Which verify to run") exit 0, with the expected PASS counts above and **0 SKIP lines**.
2. No test was deleted, skipped, weakened, or loosened (no raised tolerances, no removed assertions, no `-k` filtering, no catching of failures).
3. No broad `try/except`, `|| true`, `2>/dev/null` or other error suppression was added to hide a failure.
4. `CLAUDE.md` has a new Update Log line (and the Status/Measured tables if numbers changed) — this is an existing project rule.
5. The final output of the verify and lint commands is pasted in the final message.

## Workflow rules
- After every change, run the verify command(s) for that area and read the FULL output (not just the last line).
- Find the root cause before editing. Never retry the same fix twice.
- After 3 failed attempts on the same error, stop and report what was tried, what was observed, and what you suspect.
- Never edit tests, golden vectors, expected outputs, the verify scripts (`run_tests.sh`, `run_postsynth.sh`, `test_*.py`, `check_*.py`) to make them pass.
  Changing a test is allowed only when the test itself is shown to be wrong, and then say so explicitly and ask first.
- Never claim success without pasting the final command output.
- A passing test does not prove the test checks anything. After writing or changing a testbench or test, break the code on purpose once and confirm the test fails; also check that missing or truncated golden files make it FAIL (an `X === X` comparison passes vacuously), and that parameters the testbench overrides are also tested at their DEFAULT values.
- Never `pkill -f '<pattern>'` with a pattern that also appears in your own command line: it kills your own shell.
- Read the Vivado/iverilog warnings, not only the pass/fail line (a ROM that simulated fine was silently ignored by Vivado once).
- Git (from HANDOFF.md): commit and push ONLY when the user asks; messages short, past tense, specific ("Added ..."); NO `Co-Authored-By` or other trailers;
  several small commits; never force-push; plain `git` over SSH, not the `gh` CLI; run git from inside this folder (`/home/sreevenkat` is also a git repo).
- Never claim a number that was not measured; hardware numbers are simulation/synthesis results until a board measurement exists.
- Do not delete or overwrite checkpoints, datasets or `data/golden` without looking at them first; `software/ai/checkpoints/srnet_fp32.pt` (sha256 starts `f1ae81f706ad3707`) is frozen.

## Conventions
- Python 3.12 in `.venv` (created with `--system-site-packages`: numpy, opencv, matplotlib, pillow, torch come from the system). Pinned versions: `requirements.txt`. Scripts run from the project root.
- Folders: `software/ai/{dataset,models,training,quantization,evaluation,scripts,checkpoints}`, `hardware/rtl/{common,conv_engine,weights,...}`,
  `hardware/verification/{run_tests.sh,run_postsynth.sh,tb}`, `hardware/vivado/scripts`, `data/` (git-ignored except READMEs), `results/{quality,utilization}`, `docs/milestones/M0..M8.md`.
- No Python in `hardware/`; no Verilog in `software/`. Generated files (Vivado build, golden tiles, datasets) are never committed; `hardware/vivado/build/` is git-ignored.
- Images are RGB uint8 everywhere in Python (OpenCV loads BGR; loaders convert). All convolutions are VALID; whole images are replicate-padded by 3 px.
- Reference chain: PyTorch FP32 -> NumPy integer model (`software/ai/quantization/integer_reference.py`) -> RTL. RTL is compared bit-exact with the integer model, never with PyTorch.
- Verilog: Verilog-2001 style, compiled with `iverilog -g2012`; testbench stimulus is driven on the FALLING clock edge; a netlist simulation must wait for `glbl.GSR`.
  Weight ROMs are loaded with a plain `$readmemh` from `wrom_Ln.mem` (never rebuild the layout in an `initial` loop: Vivado ignores it).
- Vivado keeps `*.backup.log` copies of old runs in `hardware/vivado/build/`: do not glob `L*.log` when counting warnings.
- `run_tests.sh` and `run_postsynth.sh` regenerate golden/unit files (and `export_rtl.py` rewrites `hardware/rtl/weights/*`) when `data/golden` is missing: after a first run
  check `git status` and `git diff` so a regeneration cannot hide a corrupted tracked file.
- Do not trust estimates in the docs: the guides contain design estimates; measured values live in `CLAUDE.md` section 6 and `results/`.

## Known weak spots in verification (flagged, nothing added without your OK)
See the report that accompanied this file; the main ones: no single verify entry point, Python test runners exit 0 when tests SKIP, no CI, the post-synthesis
simulation only covers the 12x12 tile, no automated check that documented numbers match `results/`.
