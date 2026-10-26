# Review demo: step by step (2026-10-13, 15:00)

Everything here was run on 2026-10-12 with the board that is used for the demo. The rehearsal timing is at the end.
Bitstream for the demo: **0602** (`~/Desktop/venkat/vitis/m6_sr_0602`). It passed the full board regression on 2026-10-12. **0601** (`m6_sr`) is the fallback.

## 0. Before the review (10 minutes)
1. **Cables.**
   * The 12 V supply goes into the ZedBoard power jack.
   * A micro-USB cable goes into **PROG/JTAG (J17)** and to the PC. The UART cable (J14) is not needed.
2. **Boot-mode jumpers** stay at JTAG (MIO2-MIO6 to GND), as in M0. No SD card is needed.
3. **Power-up.** Switch SW8 on and check that the green power LED lights.
4. **Close Vitis and the Vivado Hardware Manager.** They hold the JTAG cable.
5. **Open a terminal** in the project folder:
   ```
   cd ~/Desktop/venkat/sem_project_all
   ```
6. **Optional:** run the board demo once (step 1) as a final check, then power-cycle the board (SW8 off 10 s, on), so the review starts from a fresh power-up.

## 1. Board demo: one command, about 30 s
```
software/board/demo.sh
```
The script prints one line per step and a big PASS/FAIL at the end. The full log goes to `data/board/demo/demo_<time>.log`.

| Screen line | What it means | What to say |
|---|---|---|
| `[1/5] board on JTAG ... OK  FPGA is not configured` | The PC sees the Zynq over JTAG: the ARM cores and the FPGA (xc7z020). After a power-up the FPGA is still empty. | "The board is fresh: the FPGA is empty." |
| `[2/5] ... OK  FPGA programmed, VERSION 0x53520602` | The bitstream was loaded safely: the PL is held in reset and the PS-PL level shifters are off while it is programmed. The ARM then read the accelerator's VERSION register over AXI-Lite. | "The ARM talks to my accelerator over AXI-Lite. 0x5352 is 'SR', 0602 is the hardware version." |
| `[3/5] PASS  golden tile bit-exact, 20/20 repeats identical; CYCLES 926220, tile time 9.52 ms` | One 70x70 input tile went through the DMA, the 4 CNN layers and the DMA back. All 49,152 output bytes are identical to the golden output of the Python integer model, 21 times in a row. CYCLES is counted by the hardware. | "926 thousand clock cycles at 100 MHz: 9.5 ms per 64x64 tile. Simulation predicted 926,202: the board is within 0.002 %." (The +15 to +18 cycles are not investigated; DMA/AXI handshake latency is the likely suspect, not proven.) |
| `[4/5] PASS  frame BYTE-EXACT vs the integer model (6,220,800 bytes), checksum 0xcf947f22, frame time 1311.4 ms (= 0.76 fps)` | A full 960x540 picture was cut into 135 tiles by the ARM. Each tile ran on the FPGA, and the 1920x1080 result is identical, byte for byte, to the integer model on the PC. | "Full HD output, bit-exact with my software model. 1.31 s per frame. That is the first, unoptimised version: the engines are folded and load, compute and output are not overlapped." |
| `[5/5] OK ... side_by_side_<time>.png` + image viewer | Left: the input (pixels shown 2x). Right: the FPGA output. | Point at edges and text: the CNN output is sharper than a plain enlargement. |
| `PASS: DEMO COMPLETE in ~25 s` | All of the above passed. | |

* **Input image.** It is a DIV2K **training** image (img0193). It is fine for showing bit-exactness and speed, but **do not quote quality numbers from it**. For quality, use the test-image figure in section 2.
* **Fallback to 0601:** `software/board/demo.sh --0601`. The output must be the same, with VERSION `0x53520601`.

## 2. Quality figure (no board needed, already made)
`docs/demo/compare_zebra.png`: Set14 'zebra', a **test** image never used in training, run on the board with 0602 (byte-exact, 20 tiles, 193 ms).
* **Panels:** bicubic | FPGA output | ground truth, with 2 zoomed crops each.
* **PSNR-Y:** bicubic 30.65 dB, FPGA 32.57 dB (**+1.92 dB**). PSNR-RGB: 29.34 dB vs 31.11 dB.
* **To regenerate** (needs the board):
  ```
  xsdb software/board/run_board.tcl software/board/build/sr_app_t2.elf data/board/testsets/Set14/zebra_lr.raw data/board/demo/zebra_board.raw
  .venv/bin/python software/host_tools/make_demo_figure.py Set14 zebra data/board/demo/zebra_board.raw docs/demo/compare_zebra.png
  ```

**Bigger zooms for slides** (the difference is easiest to see here). All of these images were run on the board with 0602 on 2026-10-12 and are byte-exact with the integer model:

| Figure | Image | PSNR-Y bicubic -> FPGA |
|---|---|---|
| `docs/demo/zoom_ppt3.png` | Set14 ppt3: text "Create effective multimedia presentations", 5x zoom. **Clearest one** | 26.80 -> 28.06 dB |
| `docs/demo/zoom_butterfly.png` | Set5 butterfly: wing edges and spots, 5x zoom | 27.44 -> 29.22 dB |
| `docs/demo/compare_{butterfly,monarch,ppt3,302008}.png` | full panels + 2 crops, like zebra | butterfly 27.44 -> 29.22, monarch 32.95 -> 34.58, ppt3 26.80 -> 28.06, BSD100 302008 34.51 -> 36.79 dB |

Regenerate one: run the image's `data/board/testsets/<set>/<name>_lr.raw` with `sr_app_t2.elf` (as above), then
`.venv/bin/python software/host_tools/make_zoom_figure.py Set14 ppt3 data/board/demo/ppt3_board.raw docs/demo/zoom_ppt3.png 244 28 92 150 5`
(the arguments after the output file are y x h w zoom, in ground-truth pixels).

## 3. Simulation demo (no board needed, about 3 min)
```
hardware/verification/demo_sim.sh          # RTL regression (36 runs) + one small tile with a waveform; --wave = waveform only (1 s)
```
* **Prints:** `36 test runs passed, 0 failed`, then `PASS ... 108 output beats bit-exact ... CYCLES=10962`.
* **GTKWave:** it then opens with `hardware/verification/demo_sim.gtkw`. **GTKWave is not installed yet:** `sudo apt install gtkwave`.
* **Waveform:** one HC=6 tile, 10,962 cycles. The `state` row is labelled 0 IDLE 1 LOAD 2 L1 3 L2 4 L3 5 L4 6 OUT.

| Phase | Cycles (from the VCD) | Shown by |
|---|---|---|
| AXI-Lite write of START | - | `awvalid`, `awaddr=0`, `start_r` pulse, `busy_st` goes high |
| LOAD (input stream) | 433 | `s_tvalid/s_tready` beats, `s_tlast` on the last word |
| L1 conv 3x3 3->16 | 2,726 | `bz1` |
| L2 depthwise 3x3 | 1,043 | `bz2` |
| L3 conv 1x1 16->16 | 1,050 | `bz3` |
| L4 conv 3x3 16->12 | 5,206 | `bz4`: the biggest layer, 144 cycles per pixel |
| OUT (pixel shuffle + output stream) | 504 | `m_tvalid` beats, `m_tlast` on the last word |
| done | - | `wrap_done` pulse, `done_s` (STATUS.DONE) stays high |

## 4. Numbers to quote (all measured; labels as in the project)
| What | Value |
|---|---|
| Network | 4 layers + pixel shuffle, 2,620 parameters, INT8 (uint8 activations, int8 weights) |
| Quality (INT8, mean PSNR-Y over the test sets) | Set5 35.02, Set14 31.40, BSD100 30.53 dB. Bicubic: 33.67 / 30.32 / 29.56. Beats bicubic on 119/119 images. INT8 loses 0.08-0.18 dB vs FP32 |
| Hardware == software | Board output byte-identical to the integer model: golden tile, 128x128, 960x540, and **all 119 test images** (Set5 + Set14 + BSD100, 2026-10-12) |
| Speed (**board**) | 9.52 ms per 64x64 tile (926,220 cycles at 100 MHz). 960x540 -> 1920x1080 in 1.312 s (0.76 fps), of which DMA + compute 1.279 s |
| Resources (Vivado estimate, 0602 system) | 5,296 LUT (10 %), 7,831 FF (7 %), 72 BRAM (51 %), **68 DSP (31 %)**. Timing met at 100 MHz (WNS +0.503 ns, WHS +0.016 ns) |
| Power (Vivado **estimate**, confidence Low) | 1.91 W whole chip, of which the ARM side (PS7) 1.56 W and the accelerator 0.18 W. About 2.5 J per frame (0.23 J for the accelerator alone). Not measured on the board |
| Robustness (**board**, 2026-10-12) | T6: 2 x 1000 tiles, 0 errors. 50 fresh program loads, 50 OK. Error recovery 10/10 |

**Honest limits** (say them before you are asked):
* The design reaches 0.76 fps, not real time.
* Tiles are processed one after another, without overlapping load, compute and output.
* 2 single first-tile failures seen on 2026-10-11 are still unexplained (`results/speed/m6_board.md`). They did not happen in any of the thousands of tiles since the PL-isolation fix.

## 5. If something goes wrong
| Symptom | Fix (in this order) |
|---|---|
| `FAIL the board does not answer on JTAG` | Is the power LED on? Is the cable in J17 (PROG), not J14? Then `pkill hw_server` and run again. Replug the PROG cable, wait 5 s, run again. Power-cycle (SW8 off 10 s, on). Close Vitis / Hardware Manager. |
| `FAIL no result from the board` / "AHB AP transaction error" in the log | `xsdb software/board/dap_reset.tcl`, then run again. If it fails again: power-cycle, run again. |
| `FAIL VERSION ..., expected 0x53520602` | The wrong bitstream was loaded. Check that `~/Desktop/venkat/vitis/m6_sr_0602/m6_sr.runs/impl_1/design_1_wrapper.bit` exists. Otherwise use `--0601`. |
| `FAIL golden tile` or `frame NOT byte-exact` | Run once more. If it repeats: `xsdb software/board/dap_reset.tcl`, power-cycle, then `software/board/demo.sh --0601`. Show `docs/demo/compare_zebra.png` and the simulation demo. |
| `missing file ...` | The fix is printed on the screen (`build_elf.sh 1`, `build_elf.sh 2`, `make_test_images.py`). |
| No picture window | Open the PNG from the last OK line by hand: `eog data/board/demo/side_by_side_*.png`. |
| Board completely dead / no time | Show `docs/demo/compare_zebra.png` (board-made), `results/speed/m6_board.md` and run `hardware/verification/demo_sim.sh --wave` (1 s). |

## 6. Manual equivalent of demo.sh (if the script itself is the problem)
```
source ~/Desktop/vivado_install/Vitis/2024.1/settings64.sh
xsdb software/board/run_board.tcl software/board/build/sr_app_t1.elf - - /tmp/t1.txt                       # golden tile: result=0, stat6=20, version=...
xsdb software/board/run_board.tcl software/board/build/sr_app_t2.elf data/board/div2k_img0193_lr_960x540.raw /tmp/out.raw /tmp/t2.txt
.venv/bin/python software/host_tools/compare_raw.py /tmp/out.raw data/board/div2k_img0193_expected_1920x1080.raw   # BYTE-EXACT: yes
```
0601 fallback with the same commands: put `SR_BIT=/home/sreevenkat/Desktop/venkat/vitis/m6_sr/m6_sr.runs/impl_1/design_1_wrapper.bit` in front of each `xsdb ...`.

## 7. The same demo with the newer designs (added 2026-10-27; none of them has run on a board yet)
Each sandbox tree has its own `software/board/demo.sh`, which loads that tree's bitstream and expects its own VERSION; the xsdb timeout fix of main
(`< /dev/null`, `timeout --foreground`) is in every tree, **untested on the board**. Run it from the tree's root, e.g. `cd ~/Desktop/venkat/sandbox_pipe && software/board/demo.sh`.

| Tree | `[2/5]` VERSION | `[3/5]` golden tile CYCLES (simulation) | `[4/5]` checksum | `[4/5]` frame time |
|---|---|---|---|---|
| `sandbox_R3q` | 0x53523201 | 926,202 | 0x45dd4e2d | about 1,312 ms (same cycles as R0) |
| `sandbox_R3q_125` | 0x53524301 | 926,206 | 0x45dd4e2d | predicted about 1,062 ms |
| `sandbox_pipe` (whole-frame pipeline) | 0x53525301 | 74,641 (the tile runs as a 64 x 64 frame) | 0x45dd4e2d | **predicted 73-102 ms** |

What to say for the pipeline, if it passes: "All four layers run at the same time on 170 DSPs, 16 clock cycles per pixel, the whole frame in one DMA
transfer: the same bytes as before, predicted 13-18x faster than the tiled design." If it fails, say what failed and show the simulation result
(`results/utilization/m6_system_pipe.md` in branch `pipe`: 960x540 bit-exact in simulation). The checksum differs from section 1 (0xcf947f22) because these
trees use the R3q weights; the expected outputs are in each tree's `data/board/`. The simulation demo of section 3 exists on `main` only (the pipe
branch has no tiled RTL).
