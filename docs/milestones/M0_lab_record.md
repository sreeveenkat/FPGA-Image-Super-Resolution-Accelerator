# M0 — Zynq Basics: Lab Record (owner's board run, 10-11 Oct 2026)

Reported by the owner after running everything on a real ZedBoard (not re-run by Claude). The Vivado/Vitis projects live OUTSIDE this repo:
`/home/sreevenkat/Desktop/venkat/vitis/` (Vivado: main project `vitis_helloladdu`, custom IP in `ip_repo/adder_ip_1_0`, backups `m0_step1_hello`, `m0_step2_gpio`, `m0_step3_adder`, `m0_complete`) and `/home/sreevenkat/Desktop/venkat/vitis_workspace/` (Vitis: platform `zed_platform`, apps `my_app`, `gpio_app`, `adder_app`, `dma_app`).

**Board:** ZedBoard (`xc7z020clg484-1`), Vivado + Vitis 2024.1 (Vitis Unified IDE, SDT flow), Ubuntu. Boot mode JTAG (MIO2-MIO6 to GND). Power switch SW8.

## Results

| Step | Goal | Result |
|---|---|---|
| 1 | ARM prints over UART | `Hello from Zynq! count = N` every second: PASS |
| 2 | AXI GPIO | SW0-SW7 drive LD0-LD7: PASS |
| 3 | Own AXI-Lite IP (`adder_ip`) | `25 + 17 = 42`, 6/6 tests: PASS |
| 4 | AXI DMA loopback (DDR -> MM2S -> stream FIFO -> S2MM -> DDR) | 256 B, 64 KB, 1 MB byte-exact: PASS |

## Setup facts that matter for M6

* ZedBoard board files were copied from Digilent `vivado-boards` into `~/Desktop/vivado_install/Vivado/2024.1/data/boards/board_files`; board part `digilentinc.com:zedboard:part0:1.1`.
* UART = `/dev/ttyACM0` (`sudo picocom -b 115200 /dev/ttyACM0`, exit Ctrl+A then Ctrl+X). JTAG = FT232H (`/dev/ttyUSB0`, vanishes while `hw_server` uses it: normal).
* `lsusb` fails in a terminal that sourced Vitis `settings64.sh`: use a fresh terminal. Stuck JTAG: `pkill hw_server`, replug the PROG cable.
* Block design `design_1`: PS7 (UART1, M_AXI_GP0 + S_AXI_HP0 enabled, FCLK_CLK0 100 MHz), AXI GPIO x2, `adder_ip_0` (0x43C0_0000), `axi_dma_0` (0x4040_0000), `axis_data_fifo_0` loopback, `axi_mem_intercon` -> HP0. GPIO LEDs 0x4120_0000, switches 0x4121_0000.
* AXI DMA settings that worked: simple mode (no scatter-gather), buffer length register **26 bits**, 32-bit memory and stream width, burst 16, address width 32, unaligned transfers off. M6 tile sizes are 14,700 B in / 49,152 B out, both divisible by 4.
* Vitis 2024.1 SDT flow: `XAxiDma_LookupConfig()` takes the BASE ADDRESS, not a device id.
* Vitis launch trap: a new app's `_ide/launch.json` may point the init file at the custom IP's helper tcl (`adder_ip.tcl`) and fail with `invalid command name "ps7_init"`. Set it to `_ide/psinit/ps7_init.tcl` for every new app.
* Buffers: global (not on the stack), `aligned(64)`; `Xil_DCacheFlushRange` before the DMA reads, `Xil_DCacheInvalidateRange` before the ARM reads DMA output; start S2MM (receive) before MM2S (send); poll with a timeout.
* After any hardware change: Validate, Generate Bitstream, Export Hardware (with bitstream) overwriting `design_1_wrapper.xsa`, Vitis platform `vitis-comp.json` -> Switch XSA -> Build, then the app. Back up the Vivado project (Save As) before a new step and reopen the main `.xpr` (check the title bar).
* Warnings PSU-1..PSU-4 (negative DQS delay) in validation are the normal ZedBoard DDR preset warnings.

## AXI in one table (exit-checklist item)

| Type | Used for | In M0 |
|---|---|---|
| AXI4-Lite | few 32-bit control/status registers | GPIO, adder IP, DMA control port via M_AXI_GP0 |
| AXI4 memory-mapped | bulk reads/writes with addresses and bursts | DMA M_AXI_MM2S/S2MM -> interconnect -> S_AXI_HP0 -> DDR |
| AXI4-Stream | continuous data, no addresses (TDATA, TVALID/TREADY, TLAST) | DMA <-> FIFO now; pixels into `sr_tile_core` in M6 |

The ARM caches memory, the DMA reads/writes DDR directly. Flush makes the ARM's writes visible to the DMA; invalidate makes the DMA's writes visible to the ARM. Forgetting either gives partly wrong or zero data.
