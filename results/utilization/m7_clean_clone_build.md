# M7 - clean-folder reproduction test (2026-10-12, 18:43-19:15)

A fresh `git clone` of this repository (commit `e12c898`) into an empty scratch folder, a new `.venv` (`pip install -r requirements.txt`; the first
attempt timed out on the network, the retry worked), and the steps of README "Reproduce from scratch". Datasets were copied from the main folder
(not re-downloaded); training was not re-run (committed checkpoint). Nothing in the main folder, `vitis/m6_sr`, `vitis/m6_sr_0602` or the Vitis
workspace was used or changed (the build_elf.sh/run_board.tcl defaults were overridden with SR_BSP / SR_LSCRIPT / SR_BIT).

| Step | Result in the clone |
|---|---|
| eval_baseline, check_dataset | OK ("all files decode, no duplicates, no train/test overlap, all test LR present") |
| quantize, export_rtl, gen_unit_vectors | `git status` empty: qparams.npz, weights .mem, baseline results byte-identical to the committed files |
| test_integer, test_export, test_model | PASS |
| run_all.py --no-fpga | max difference to the published CSVs 0 |
| run_tests.sh quick | 36 passed, 0 failed (3 min) |
| build_m6_system.tcl (2 jobs) | 6 min 51 s, write_bitstream Complete, **WNS +0.503 / WHS +0.016 ns, 5,296 LUT / 7,831 FF / 72 BRAM / 68 DSP, 1.913 W est. = identical to the 0602 build**; 12/12 .mem read from the clone's path; 0 CRITICAL WARNING in the run logs |
| create_platform.py (Vitis CLI) | PLATFORM_OK in 31 s; `xparameters.h` identical to the Vitis workspace's m6_platform |
| golden_tile_h, build_elf.sh 1/2/3 | built (only the known BSP `XPAR_*` redefinition warnings) |
| board T1 (clone bitstream + ELF) | result 0, VERSION 0x53520602, 20/20 repeats, CYCLES 926,217-926,220, 9.52 ms |
| board T2 128x128 / 960x540 | byte-exact, fnv 0x91a4506d / 0xcf947f22, 1,311.4 ms |
| board T3 (5 frames) | mean 1,312.3 ms, min 1,311.5, max 1,313.2, byte-exact |
| board_testsets prep + run_testsets.sh + run_all.py | **119/119 byte-exact**, table A regenerated identical to the committed one |

Found and fixed while doing it: the block design, the M0 IP, the linker script and a platform recipe were only outside the repo (now
`hardware/vivado/bd/`, `hardware/vivado/ip_repo/`, `software/board/sr_app/lscript.ld`, `software/board/create_platform.py`); the RTL default WDIR
would have made a clone read the ORIGINAL folder's weights (the build script now sets WDIR to the checkout); `check_dataset.py` needs
`eval_baseline.py` to run first (README order). Not covered: `demo.sh` (fixed paths to the original PC), dataset downloads, training.
