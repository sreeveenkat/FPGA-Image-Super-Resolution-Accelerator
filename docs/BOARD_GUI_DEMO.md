# Showing the project in the Vivado and Vitis GUIs, connected to the ZedBoard

This guide is for a live demo with the GUIs (Vivado + Vitis + a serial terminal), not with the one-command script.
It says what to open, where to click, what you will see, and what to say.

Written 2026-10-13. Two kinds of steps:
* **[tested]**: run on the board before (the numbers come from those runs).
* **[not run]**: the GUI clicks. I cannot click a GUI, so these follow the same steps you used in M0. Rehearse them once before the review.

---

## 0. Which projects to open (important)

There are several old copies on the PC. Use **only** these:

| What | Path | Why this one |
|---|---|---|
| Vivado project | `~/Desktop/venkat/vitis/m6_sr_0602/m6_sr.xpr` | The **0602** hardware: the build that passed the full board regression and the 119-image run |
| Bitstream (inside it) | `~/Desktop/venkat/vitis/m6_sr_0602/m6_sr.runs/impl_1/design_1_wrapper.bit` | md5 `d48ef9ea1b1b4e513ad9b6b52e90c8a9` |
| Hardware file for Vitis | `~/Desktop/venkat/vitis/m6_sr_0602/design_1_wrapper.xsa` | Exported from the 0602 project |
| **Vitis workspace** | `~/Desktop/venkat/vitis_ws_demo_0602/` | **New, made today for this demo** (see below) |
| Vitis platform (inside it) | `vitis_ws_demo_0602/m6_platform` | Made from the 0602 `.xsa` |
| Vitis application (inside it) | `vitis_ws_demo_0602/sr_app` | The ARM program from the repo (`software/board/sr_app/*.c *.h` + `sr_regs.h`), built with `SR_TEST=1` = test T1 (golden tile) |

**Do NOT use the old workspace `~/Desktop/venkat/vitis_workspace/sr_app` for the demo.** I checked it today:
* its bitstream is the old **0601** (md5 `8b5fe08f…`);
* its C sources are the **first** version from 2026-10-11, before the timer fix, so it prints "tile time 0 us".

I left it untouched.

### How the new workspace was made (2026-10-13, by me, with the Vitis command line)
1. Platform `m6_platform` from `m6_sr_0602/design_1_wrapper.xsa`. Result: "Platform Build Finished successfully".
2. Application `sr_app` from the "Empty Application" template. I copied the repo's sources into `sr_app/src/`.
3. In `sr_app/src/UserConfig.cmake` I put `SR_TEST=1` under `USER_COMPILE_DEFINITIONS`.
4. Built it. Result: `sr_app/build/sr_app.elf`. I checked that the compile used `-DSR_TEST=1` and that the T1 text is inside the ELF.
5. The new app's `sr_app/_ide/bitstream/design_1_wrapper.bit` is the 0602 bitstream (same md5 as above).
6. **The M0 trap came back and I fixed it.** The new launch file (`sr_app/_ide/.theia/launch.json`) pointed the init script at `psinit/adder_ip.tcl`. I changed it to `psinit/ps7_init.tcl`.

**Not done yet:** this new app has **not been run on the board yet** (I did not touch the board). Its C code is the same code as the board-tested `software/board/build/sr_app_t1.elf`, but it is compiled by Vitis, not by `build_elf.sh`. So rehearse section 4 once.

---

## 1. Cables and power (before opening anything)

| Cable | Port on the ZedBoard | Needed for |
|---|---|---|
| 12 V power | power jack, switch **SW8** | everything |
| micro-USB #1 | **J17 "PROG"** (JTAG) | Vivado Hardware Manager + Vitis Run (programming FPGA, loading the ARM program) |
| micro-USB #2 | **J14 "UART"** | seeing the ARM's printf text (`/dev/ttyACM0`). **Needed for this GUI demo** (the script demo does not need it) |

* **Boot jumpers:** JTAG mode (MIO2–MIO6 to GND), as in M0. No SD card.
* **Power on:** switch SW8 on. The green power LED lights. The blue **DONE** LED stays off: the FPGA is still empty.
* **Check on the PC** (in a fresh terminal):
  ```
  ls /dev/ttyACM0        # the UART: it must exist
  ```
  If it is missing, check the J14 cable.

---

## 2. Terminal 1: the serial terminal (open it FIRST)

The ARM program prints its result over the UART. If you open the terminal after the program has run, you miss the text.

```
sudo picocom -b 115200 /dev/ttyACM0
```
* You see `Terminal ready`. Leave this window open and visible.
* To exit later: **Ctrl+A**, then **Ctrl+X**.

---

## 3. Vivado: show the hardware design and program the FPGA

### 3.1 Open the project
```
source ~/Desktop/vivado_install/Vivado/2024.1/settings64.sh
vivado ~/Desktop/venkat/vitis/m6_sr_0602/m6_sr.xpr &
```
Wait until the title bar shows `m6_sr - [/home/sreevenkat/Desktop/venkat/vitis/m6_sr_0602/m6_sr.xpr]`. Check that the path says **m6_sr_0602**.

> ⚠️ **Do NOT click** "Generate Bitstream", "Run Synthesis", "Run Implementation" or "Reset Runs".
> * The bitstream is already built and tested.
> * A rebuild takes a long time.
> * With the default 8 jobs, a rebuild froze this PC once (2026-10-12).
>
> If Vivado says something is "out-of-date", **ignore it**: you are only looking.

### 3.2 What to show (all read-only)

| Click | What you see | What to say |
|---|---|---|
| Flow Navigator → **IP INTEGRATOR → Open Block Design** | The block design `design_1`: the Zynq PS7, `axi_dma_0`, `sr_accel_top_0` (my accelerator), interconnects, plus the M0 parts (GPIO, adder IP) | "The ARM (PS) sends tiles to my accelerator through the AXI DMA. It controls it with AXI-Lite registers." |
| Click on `sr_accel_top_0`, look at its ports | `s_axi` (control registers), `s_axis` (pixels in), `m_axis` (pixels out), `aclk`, `aresetn` | "s_axi is AXI4-Lite for registers, s_axis/m_axis are AXI4-Stream for pixel data." |
| Window → **Address Editor** | `sr_accel_top_0/s_axi` at **0x4000_0000** (4K); `axi_dma_0` at **0x4040_0000** | "These are the addresses the ARM program uses (`sr_driver.h`)." |
| Sources → Design Sources → under `design_1_wrapper` | `sr_accel_top.v` → `sr_axis_wrapper` → `sr_tile_core` → 4 × `conv_engine` | "Four conv engines, one per CNN layer, written in Verilog." |
| Flow Navigator → **IMPLEMENTATION → Open Implemented Design** (takes ~1 min) | The routed chip view | |
| Then **Report Utilization** (or Project Summary → Utilization) | **5,296 LUT, 7,831 FF, 72 BRAM, 68 DSP** (whole system) | "68 of 220 DSPs, 72 of 140 block RAMs." |
| **Report Timing Summary** | **WNS +0.503 ns, WHS +0.016 ns**, all constraints met | "Timing is met at 100 MHz: positive slack." |
| **Report Power** (optional) | ~**1.91 W** total, accelerator ~**0.18 W** | "This is Vivado's estimate (confidence Low), not a measurement." |

The numbers in this table come from `results/utilization/m6_system_0602.md` and `results/utilization/m7_power.md`. If Vivado shows exactly these, you are on the right project.

### 3.3 Program the FPGA from Vivado (shows the JTAG connection)
1. Flow Navigator → **PROGRAM AND DEBUG → Open Hardware Manager**.
2. **Open Target → Auto Connect.**
3. The Hardware panel shows `localhost` → `xilinx_tcf/Digilent/...`, with two devices:
   * `arm_dap_0`: the ARM debug port;
   * `xc7z020_1`: the FPGA.

   Say: "The PC sees the Zynq chip over JTAG."
4. Right-click `xc7z020_1` → **Program Device**. Check that the bitstream file is
   `.../m6_sr_0602/m6_sr.runs/impl_1/design_1_wrapper.bit`, then press **Program**.
5. The progress bar finishes, and the **blue DONE LED** on the board turns on. Say: "The FPGA is now configured with my accelerator."
6. **Before going to Vitis: Hardware Manager → Close Target** (right-click `localhost` → Close Server, or File → Close Hardware Manager).
   This frees the JTAG cable for Vitis.

Note: Vitis "Run" programs the FPGA **again** (with a system reset). That is fine: step 3.3 is only to *show* the JTAG connection in Vivado. On the board, the safe way to reprogram is with a system reset first, and Vitis Run does that (`resetSystem: true` in the launch file).

---

## 4. Vitis: build and run the ARM program on the board

### 4.1 Open the workspace
In a **new** terminal:
```
source ~/Desktop/vivado_install/Vitis/2024.1/settings64.sh
vitis -w ~/Desktop/venkat/vitis_ws_demo_0602 &
```
The Vitis Unified IDE opens. On the left, under **VITIS COMPONENTS**, you see:
* `m6_platform`: the hardware platform made from the 0602 `.xsa`;
* `sr_app`: the ARM application.

### 4.2 What to show

| Click | What you see | What to say |
|---|---|---|
| `sr_app` → `Sources` → `src` → `main.c` | The test program: T1 golden tile, T2 full image, T3 timing | "The ARM program, bare metal C, no Linux." |
| `src` → `sr_driver.c` | `sr_run_tile()`: flush cache → arm DMA receive (S2MM) → arm DMA send (MM2S) → write START → wait DONE → invalidate cache | "This is how one tile goes PS → PL → PS." |
| `src` → `sr_regs.h` | Register offsets: CONTROL 0x00, STATUS 0x04, TILE_SIZE 0x08, CYCLES 0x0C, ERROR_CODE 0x10, VERSION 0x14 | "Same register map as in the Verilog (`sr_accel_top.v`) and `docs/REGISTER_MAP.md`; a test checks they agree." |
| `src` → `golden_tile.h` | A big array: one 70×70 input tile and its expected 128×128 output, made by the Python integer model | "The ARM compares the FPGA output with this golden output, byte for byte." |
| `src` → `UserConfig.cmake` | `SR_TEST=1` | "This build runs test T1." |
| `m6_platform` → `vitis-comp.json` | The `.xsa` path: `.../m6_sr_0602/design_1_wrapper.xsa` | "The platform comes from the Vivado hardware export." |

### 4.3 Build
1. Bottom-left **FLOW** panel → choose component **sr_app** → **Build**.
2. The output panel ends with `Build Finished successfully` (or similar) and shows the ELF size.

   It is already built, so this is quick. If it fails, see section 7.

### 4.4 Run on the board
1. Check that the picocom window (section 2) is open and visible.
2. **FLOW** panel → **Run** (under sr_app).
3. Vitis then:
   * resets the system;
   * programs the FPGA with the 0602 bitstream;
   * runs `ps7_init`;
   * loads `sr_app.elf` into DDR;
   * starts the ARM.

   This takes about 10–20 s.
4. **The picocom window shows something like this.** The values come from the board runs of 2026-10-12 with 0602; the CYCLES and µs values can differ by a few.
   ```
   --- SR accelerator test (SR_BASE 0x40000000, DMA 0x40400000) ---
   memory: program 0x... - 0x... (top of stack), in 0x..., out 0x..., ...
   init ok: VERSION 0x53520602, TILE_SIZE 64
   T1: golden tile (real0), 14700 bytes in, 49152 bytes out
   T1: CYCLES = 926217 (expected 926202 in simulation), tile time 9520 us (DMA + compute)
   T1: first run: all 49152 bytes identical to the golden output
   T1: 20 of 20 repeated runs identical to the first
   T1: CYCLES over 21 runs: min 926217, max 926220, mean 926219 (simulation: 926202)
   T1: tile time over 21 runs (DMA + compute + cache ops): min 9520 us, max 9523 us, mean 9521 us
   T1 PASS
   done, result 0
   ```

### 4.5 What each line means (say this)

| Line | Meaning |
|---|---|
| `SR_BASE 0x40000000, DMA 0x40400000` | The addresses from the Vivado Address Editor (section 3.2): hardware and software agree. |
| `init ok: VERSION 0x53520602` | The ARM read my accelerator's VERSION register over AXI-Lite. 0x5352 = "SR", 0602 = hardware version. **This proves the PS↔PL connection works.** |
| `TILE_SIZE 64` | The core works on 64×64 tiles (70×70 with the 3-pixel border). |
| `14700 bytes in, 49152 bytes out` | 70×70×3 bytes go in by DMA; 128×128×3 bytes come back (2× bigger). |
| `CYCLES = 926217` | Clock cycles counted **by the hardware** for one tile. Simulation said 926,202, which is 15 cycles less (0.002 %). The difference is not investigated; DMA/AXI handshake latency is likely, not proven. |
| `tile time 9520 us` | 9.52 ms per tile at 100 MHz (926k cycles × 10 ns = 9.26 ms + DMA and cache work). |
| `all 49152 bytes identical to the golden output` | The FPGA result is **bit-exact** with the Python integer model. |
| `20 of 20 repeated runs identical` | It gives the same answer every time. |
| `T1 PASS` / `done, result 0` | Test passed. |

If you get **`T1 FAIL`** or nothing at all, see section 7.

---

## 5. The full frame and the picture (terminal; needs the cable free)

Vitis T1 shows one tile. For the full **960×540 → 1920×1080** frame you need to send an image into DDR and read the result back. The scripts do that over JTAG.

1. **Close Vitis** (File → Exit). It holds the JTAG cable.
2. Leave picocom open if you like (the script does not need it).
3. In a terminal:
   ```
   cd ~/Desktop/venkat/sem_project_all
   software/board/demo.sh
   ```
4. **Expected:** `[1/5]` … `[5/5]`, then `PASS: DEMO COMPLETE` (~25 s). This was tested on 2026-10-12 (rehearsal 24.8 s).
   * Frame BYTE-EXACT, checksum `0xcf947f22`, frame time ~1311 ms (0.76 fps).
   * A side-by-side PNG opens.

   Line-by-line meanings are in `docs/DEMO.md`, section 1.
5. **If `[1/5]` fails:** run `pkill hw_server`, then try again. Still failing? Power-cycle (SW8 off 10 s, on) and run again.

**Quality picture** (no board needed): open `docs/demo/compare_zebra.png` or `docs/demo/zoom_ppt3.png`. The numbers for them are in `docs/DEMO.md`, section 2.

---

## 6. Suggested order for the review (≈10 minutes)

| # | Where | What | Time |
|---|---|---|---|
| 1 | Vivado | Block design, address editor, utilization, timing (3.2) | 3 min |
| 2 | Vivado | Hardware Manager → Auto Connect → Program Device → blue DONE LED (3.3), then Close Target | 1 min |
| 3 | Vitis | Show main.c / sr_driver.c / golden_tile.h (4.2), Run (4.4), read the picocom output (4.5) | 3 min |
| 4 | Terminal | Close Vitis, `software/board/demo.sh`: full frame byte-exact + 0.76 fps + side-by-side picture (5) | 1 min |
| 5 | Image viewer | `compare_zebra.png` / `zoom_ppt3.png`: quality vs bicubic | 1 min |

**Backup plan:** if any GUI step fails during the review, close Vivado and Vitis and run only `software/board/demo.sh`. It is the tested path and shows the same results (VERSION, golden tile, full frame).

---

## 7. Troubleshooting

| Problem | Fix |
|---|---|
| No `/dev/ttyACM0` | J14 UART cable not plugged in, or board off. Replug, wait 5 s. |
| picocom: permission denied | Use `sudo picocom ...` (as in M0). |
| picocom shows nothing after Run | Was picocom opened before Run? Press **Run** again (it resets and reruns). Check the baud rate (115200). |
| Vivado Auto Connect finds nothing | Board on? Cable in **J17** (PROG), not J14? Close Vitis/other xsdb. `pkill hw_server`, replug J17, try again. |
| Vitis Run: `invalid command name "ps7_init"` | The launch file points at the wrong init script (M0 trap). In `sr_app/_ide/.theia/launch.json`, `ps7InitTclFile` must end in `psinit/ps7_init.tcl` (I already set it; Vitis may rewrite it if you change the launch configuration). |
| Vitis Run: "target busy" / cannot connect | Vivado Hardware Manager still holds the target: close it (3.3 step 6). Or `pkill hw_server` and Run again. |
| `init ok: VERSION 0x53520601` | The old 0601 bitstream was loaded: you are in the old workspace `vitis_workspace`. Open `vitis_ws_demo_0602`. |
| `tile time 0 us` | Old program sources (old workspace). Same fix. |
| `sr_init failed` / `T1 FAIL` / no output and Run again does not help | Close Vitis, then `source ~/Desktop/vivado_install/Vitis/2024.1/settings64.sh` and `xsdb software/board/dap_reset.tcl` (in the project folder). Or power-cycle the board (SW8 off 10 s). Then Run again. |
| Vitis build fails | Check `UserConfig.cmake` still has `SR_TEST=1` and `src/` has the 9 files (`main.c sr_driver.c/.h sr_memmap.h sr_tiling.c/.h sr_regs.h golden_tile.h lscript.ld`). |
| Want the UART menu instead of T1 | In `UserConfig.cmake` change `SR_TEST=1` to `SR_TEST=0` and rebuild. Then type `1` in picocom for T1 or `5` for the error-recovery test. **Not tested from the menu on the board yet**, so try it before the review. Menu `2`/`3` need an image already in DDR, so use `demo.sh` for those. |

---

## 8. If you change the hardware later (not needed for the demo)
* **Vivado:** change the design, run Validate, then Generate Bitstream (Tools → Settings: use `-jobs 2`), then File → Export → Export Hardware (include bitstream) over `design_1_wrapper.xsa`.
* **Vitis:**
  1. `m6_platform` → `vitis-comp.json` → **Switch XSA** → Build;
  2. then `sr_app` → Build;
  3. check `launch.json` again (section 7).
* **Repo:** the Tcl way to rebuild is in `docs/RUN_GUIDE.md`, Part 7.
