# Board session runbook (one sitting, in this order)

Prepared 2026-10-24. **Nothing in this runbook has been run on the board yet.** Pass values: `docs/paper/board_expected.md` (generated from each tree's own integer model).
Pass rules: `docs/paper/board_checklist.md` section 5b (PROPOSED merge criteria; the owner confirms). Known issues: `board_checklist.md` section 7.
Order: **0** prepare -> **1** R0/0602 with the hang test (T1, T2) -> **2** T7 -> **3** R2q -> **4** R3q -> **7** r0_125 (R0 at 125 MHz) -> **5** power (idle and processing for every bitstream).

Conventions used below
* `D=data/board/$(date +%F)` inside each tree: every log of the day goes there (`board_run.sh` creates it). Save **everything**: UART log, xsdb log, meta file, stats, outputs.
* Start every script **at the prompt of a normal terminal** with stdin closed where shown (`< /dev/null`): that is the fix for the 961 s hang (UNTESTED ON THE BOARD).
* Trees: R0 = `~/Desktop/venkat/sem_project_all`, R2q = `~/Desktop/venkat/sandbox_R2q`, R3q = `~/Desktop/venkat/sandbox_R3q`. Run each command from the root of the tree named in the step.
* Stop a stray process by PID only: `pgrep -x hw_server` then `kill <pid>` (never `pkill -f`).

## 0. Prepare (PC, before touching the cables)
```bash
source ~/Desktop/vivado_install/Vitis/2024.1/settings64.sh
cd ~/Desktop/venkat/sem_project_all
.venv/bin/python software/board/test_uart_capture.py          # PC test of the capture + wrapper: must end ALL PASS (2026-10-24: 23/23 PASS)
.venv/bin/python software/analysis/board_expected.py          # prints the expected table, exit 0 (all cross-checks OK)
md5sum ~/Desktop/venkat/TESTED_0602.bit ~/Desktop/venkat/R2q_artifacts/*.bit ~/Desktop/venkat/R3q_artifacts/*.bit    # compare with board_expected.md
```
Hardware: board on, micro-USB in **J17 (PROG/JTAG)** and **J14 (UART)**, boot jumpers on JTAG, `ls /dev/ttyACM0` shows the device. Close picocom, Vivado and Vitis (one reader of the UART, one owner of the JTAG cable).
Power-cycle the board (SW8 off 10 s, on). `pgrep -x hw_server` -> if a PID is printed, `kill` it.

## 1. R0 / 0602 (tree R0): the hang test, then T1 and T2
| # | Command | Pass when | Log |
|---|---|---|---|
| 1.1 | **Hang test, new form:** `time bash -c 'timeout --foreground 20 xsdb software/board/jtag_check.tcl < /dev/null; echo exit=$?'` | `JTAG_OK`, `exit=0`, real about 1-3 s | copy the terminal text to `$D/hang_test_new.txt` |
| 1.2 | **Hang test, old form (negative control, optional, costs 20 s):** `time bash -c 'timeout 20 xsdb software/board/jtag_check.tcl; echo exit=$?'` | on 13 Oct this form hung; reproduced on the PC; here `exit=124` after 20 s would confirm the cause on the real xsdb, `exit=0` would mean the cause is different on the real tool. Either way, write the result down. | `$D/hang_test_old.txt` |
| 1.3 | `software/board/demo.sh --no-view < /dev/null` | ends with `PASS: DEMO COMPLETE`, in about 25-30 s (13 Oct: 961 s). Any "xsdb did not exit within N s" is the hang again: note the step. | `data/board/demo/demo_<time>.log` (made by the script) |
| 1.4 | `software/board/board_run.sh t1_r0 software/board/build/sr_app_t1.elf - -` | exit 0; `t1_r0_stats.txt`: `result=0`, `version=0x53520602`, `stat6=20`; CYCLES (stat0..2) each in 926,210-926,241; UART log shows `T1 PASS` | `$D/t1_r0.log` (UART), `t1_r0_xsdb.log`, `t1_r0_meta.txt`, `t1_r0_stats.txt` |
| 1.5 | `software/board/board_run.sh t2_r0 software/board/build/sr_app_t2.elf data/board/div2k_img0193_lr_960x540.raw $D/t2_r0.raw` then `.venv/bin/python software/host_tools/compare_raw.py $D/t2_r0.raw data/board/div2k_img0193_expected_1920x1080.raw; echo exit=$?` | `fnv1a32=0xcf947f22`, `BYTE-EXACT: yes`, `exit=0`; stat0 about 1,311,000 us | `$D/t2_r0.*` |
| 1.6 | **20-frame timing (R0 repeat, needed as the reference for R2q/R3q):** `software/board/board_run.sh t3_r0 software/board/build/sr_app_t3_20f.elf data/board/div2k_img0193_lr_960x540.raw $D/t3_r0.raw` then the awk line below | mean within +-2 ms of 1,311.9 ms, max - min <= 3 ms, CYCLES 926,210-926,241, `$D/t3_r0.raw` compares byte-exact (0xcf947f22) | `$D/t3_r0.log` has the 20 per-frame lines |

Frame statistics from the UART log (used in every timing step):
```bash
grep -oE 'frame [0-9]+: total [0-9]+' $D/t3_r0.log | awk '{t=$4; s+=t; if(n==0||t<mn)mn=t; if(t>mx)mx=t; n++} END{printf "frames %d  mean %.1f ms  min %.1f  max %.1f  max-min %.1f ms\n", n, s/n/1000, mn/1000, mx/1000, (mx-mn)/1000}'
grep -E 'T3: CYCLES' $D/t3_r0.log
```
If a step fails: `xsdb software/board/dap_reset.tcl < /dev/null`, then retry once; if it fails again, power-cycle (SW8 off 10 s) and retry; record every failure, never hide a retry.

## 2. T7: ARM only, no accelerator (tree R0; never run before)
| # | Command | Pass when | Log |
|---|---|---|---|
| 2.1 | `software/board/board_run.sh t7_r0 software/board/build/sr_app_t11.elf data/board/div2k_img0193_lr_960x540.raw $D/t7_r0.raw` then `compare_raw.py $D/t7_r0.raw data/board/div2k_img0193_expected_1920x1080.raw` | `result=0`, `BYTE-EXACT: yes`, fnv 0xcf947f22. Record from the stats: stat1 = time per frame (us), stat4 pad, stat5 ARM tile copy, stat6 ARM compute. **No expected time exists** (the same C code takes 0.91 s per frame on the PC at -O2, `test_swmodel.sh` 2026-10-24). | `$D/t7_r0.*` |

If it prints `ERROR: no ready marker after 900 s`, T7 is slower than 900 s per frame: raise `set TIMEOUT_S` in `software/board/run_board.tcl` (and `XSDB_TIMEOUT`), run again, and note it. The 20-frame T7 (power) needs a larger `TIMEOUT_S` too.

## 3. R2q (tree R2q; bitstream `~/Desktop/venkat/R2q_artifacts/design_1_wrapper_R2q.bit` is the tree default; VERSION 0x53522201)
Run steps 3.1-3.8 in `~/Desktop/venkat/sandbox_R2q`. `board_run.sh` exists only on main, so in a sandbox first run `export SR_TREE=$PWD; BR=~/Desktop/venkat/sem_project_all/software/board/board_run.sh` (the run then uses the sandbox's ELFs, `run_board.tcl` and bitstream default, and saves under the sandbox's `data/board/<date>/`; PC-tested with a fake tree). Expected values: `board_expected.md` section R2q.
| # | Command | Pass when |
|---|---|---|
| 3.1 | `$BR t1_r2q software/board/build/sr_app_t1.elf - -` | `result=0`, **`version=0x53522201`**, `stat6=20`, CYCLES 926,210-926,241, `T1 PASS` in the UART log |
| 3.2 | `$BR t2_r2q software/board/build/sr_app_t2.elf data/board/div2k_img0193_lr_960x540.raw $D/t2_r2q.raw`, then `compare_raw.py $D/t2_r2q.raw data/board/div2k_img0193_expected_1920x1080.raw` | `fnv1a32=0x2afbc9ae`, `BYTE-EXACT: yes` |
| 3.3 | negative control (output): `compare_raw.py $D/t2_r2q.raw ~/Desktop/venkat/sem_project_all/data/board/div2k_img0193_expected_1920x1080.raw` | `BYTE-EXACT: no` (R2q must differ from R0) |
| 3.4 | negative control (VERSION): `SR_BIT=~/Desktop/venkat/TESTED_0602.bit $BR t1_r2q_wrongbit software/board/build/sr_app_t1.elf - -` | exit != 0 and the UART log shows `SR: VERSION 0x53520602, expected 0x53522201`; then run 3.1 again (it reprograms the right bitstream) and it must pass |
| 3.5 | 20-frame timing: `$BR t3_r2q software/board/build/sr_app_t3_20f.elf data/board/div2k_img0193_lr_960x540.raw $D/t3_r2q.raw`, awk line of section 1 | mean within +-2 ms of 1,311.9 ms, max - min <= 3 ms, CYCLES 926,210-926,241, output fnv 0x2afbc9ae |
| 3.6 | 119 images (optional, about 11 min; the PC prep was done on 2026-10-24: 119 `_lr.raw` + 119 `_exp.raw` files in `data/board/testsets/` of each sandbox; if they are missing run `.venv/bin/python software/host_tools/board_testsets.py prep` first): `software/board/run_testsets.sh $D/testsets_r2q.log < /dev/null`, then `.venv/bin/python software/host_tools/board_testsets.py eval` | `run_testsets: 119 byte-exact, 0 failed of 119`; `eval` exit 0 |
| 3.7 | T7: `$BR t7_r2q software/board/build/sr_app_t11.elf data/board/div2k_img0193_lr_960x540.raw $D/t7_r2q.raw`, `compare_raw.py` | fnv 0x2afbc9ae, `BYTE-EXACT: yes` |
| 3.8 | Timing check of the build: Vivado WNS stays met (+0.944 ns, `m6_system_R2q.md` in branch `r2q`) | nothing to run; cite the file |

R2q goes first; if any item fails, R3q is not tried before the cause is understood. Pass rule for the merge: `board_checklist.md` section 5b items 1-5.

## 4. R3q (tree R3q; only after section 3 passed; VERSION 0x53523201)
Same commands as section 3 with `t..._r3q` names in `~/Desktop/venkat/sandbox_R3q`; expected: T1 `version=0x53523201`; T2 `0x45dd4e2d`; negative controls: the R3q output must differ from the R2q expected file and from the R0 expected file (`BYTE-EXACT: no` for both);
wrong-bitstream control with the R2q bitstream (`SR_BIT=~/Desktop/venkat/R2q_artifacts/design_1_wrapper_R2q.bit`): `SR: VERSION 0x53522201, expected 0x53523201`; 119 images; T7 fnv 0x45dd4e2d; 20-frame timing as in 3.5. This is the first real-hardware check of the anchor's halo-aligned read (135 tiles).

## 5. Power (after the functional steps of each design)
Procedure: `board_checklist.md` section 4. **Primary: inline DC power meter between the 12 V adapter and the barrel jack. Cross-check: J21** (10 mOhm, 1 W sense resistor in series with the 12 V input, per forum quotes of the ZedBoard Hardware User's Guide; page citation to be added): I = V_J21 / 0.010 Ohm, P = I x V_in. Measure V_in in every state.
For **each bitstream** (R0, R2q, R3q, r0_125): idle (T1 finished, ARM in its idle loop) and processing (`sr_app_t3_200f.elf` of that tree, read during the run); plus P0 (PL not programmed) and P3 (ARM only, `sr_app_t11_20f.elf`). Wait 30 s per state, then at least 5 readings over at least 30 s, both meters in the same window; report mean/min/max/count. Repeat R0 idle/processing at the end (drift).
Start the long runs with `board_run.sh` (it prints the start time), e.g. `software/board/board_run.sh p2_r0 software/board/build/sr_app_t3_200f.elf data/board/div2k_img0193_lr_960x540.raw $D/p2_r0.raw` (R0 tree); in a sandbox `export SR_TREE=$PWD; BR=~/Desktop/venkat/sem_project_all/software/board/board_run.sh` and `$BR p2_r2q ...`.
Board-level power: not comparable to Vivado's on-chip estimate; compare deltas only. Write down both meter models, accuracy, range, resolution, and every reading with its time in `$D/power_readings.txt`.

## 6. What to bring back (all under `data/board/<date>/` of each tree)
`*.log` (UART with time stamps), `*_xsdb.log`, `*_meta.txt` (git revision, bitstream and ELF md5), `*_stats.txt`, the `compare_raw.py` lines (also the negative controls), the hang-test texts of 1.1-1.3, the meter readings, and a list of every retry with its reason.
After the session update the local project log, `docs/STATUS.md` and the merge decision; commit only on request.

## 7. After R3q: r0_125, R0 at 125 MHz (tree `~/Desktop/venkat/sandbox_R0_125`, branch `r0_125`; VERSION 0x53524201)
Only after sections 1-4 passed (checklist section 5a). Built 2026-10-25, Vivado WNS +0.632 ns at 125.000 MHz, simulation 88/88; **nothing on the board yet** (`docs/paper/fmax_plan.md` section 7, `results/utilization/m6_system_R0_125.md` in that branch). Expected answers: `docs/paper/board_expected.md`, section "R0 at 125 MHz".
Same commands as section 1, from the sandbox root (the bitstream `~/Desktop/venkat/R0_125_artifacts/design_1_wrapper_R0_125.bit` is the tree default; the tree's driver refuses every other bitstream):
```bash
cd ~/Desktop/venkat/sandbox_R0_125; export SR_TREE=$PWD; BR=~/Desktop/venkat/sem_project_all/software/board/board_run.sh
$BR r125_t1 software/board/build/sr_app_t1.elf - - < /dev/null
$BR r125_t2 software/board/build/sr_app_t2.elf data/board/div2k_img0193_lr_960x540.raw $D/r125_t2.raw < /dev/null
~/Desktop/venkat/sem_project_all/.venv/bin/python software/host_tools/compare_raw.py $D/r125_t2.raw data/board/div2k_img0193_expected_1920x1080.raw; echo exit=$?
$BR r125_t3 software/board/build/sr_app_t3_20f.elf data/board/div2k_img0193_lr_960x540.raw $D/r125_t3.raw < /dev/null
```
Pass: VERSION 0x53524201; T1 20/20 and CYCLES 926,214-926,245; T2 `BYTE-EXACT: yes`, fnv **0xcf947f22** (same weights as R0); T3 20-frame mean in the plausible range 1,033-1,064 ms (predicted 1,061.8 ms; **a prediction**). If T1 or T2 fails, record it and stop; do not retry silently. Do not compare power with the other designs (the clock differs).
