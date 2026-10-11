# M0 — Zynq Basics: Lab Record

**Milestone:** M0 — ARM, FPGA, AXI and DMA
**Board:** Avnet/Digilent ZedBoard (Zynq-7000, `xc7z020clg484-1`)
**Tools:** Vivado 2024.1 + Vitis Unified IDE 2024.1 on Ubuntu Linux (Dell G15)
**Dates:** 10 Oct 2026 (setup + Hello World), 11 Oct 2026 (GPIO, custom IP, DMA)
**Result:** All four M0 hardware goals passed ✅

---

## 1. Summary of results

| Step | Goal | Result |
|---|---|---|
| 1 | ARM boots and prints text | `Hello from Zynq! count = N` every second ✅ |
| 2 | ARM reads/writes FPGA registers (AXI GPIO) | Switches SW0–SW7 drive LEDs LD0–LD7 ✅ |
| 3 | Own AXI-Lite peripheral | `25 + 17 = 42`, all 6 tests passed ✅ |
| 4 | DMA round-trip DDR → FPGA → DDR | 256 B, 64 KB and 1 MB byte-exact ✅ |

### M0 exit checklist

- [x] Hello World prints after power cycle
- [x] Switches control LEDs through AXI GPIO
- [x] Own AXI-Lite IP returns the correct sum
- [x] DMA loopback of 256 B, 64 KB and 1 MB is byte-exact
- [ ] Explain AXI-Lite vs AXI4 vs AXI-Stream, and why `Xil_DCacheFlushRange` is needed (see Section 10)

---

## 2. Hardware and PC setup

### Board connections

| Item | Setting |
|---|---|
| PROG micro-USB (J17) | JTAG — programming and debug |
| UART micro-USB | Serial console (program output) |
| Power | 12 V adapter, switch SW8 ON |
| Boot mode jumpers | MIO2–MIO6 all to GND → **JTAG boot** |

### Linux one-time setup

| What | Where / command |
|---|---|
| Vivado/Vitis install folder | `~/Desktop/vivado_install/` |
| Vivado settings script | `~/Desktop/vivado_install/Vivado/2024.1/settings64.sh` |
| Vitis settings script | `~/Desktop/vivado_install/Vitis/2024.1/settings64.sh` |
| JTAG cable drivers installed from | `~/Desktop/vivado_install/Vivado/2024.1/data/xicom/cable_drivers/lin64/install_script/install_drivers` |
| ZedBoard board files copied into | `~/Desktop/vivado_install/Vivado/2024.1/data/boards/board_files` (from Digilent's `vivado-boards` GitHub) |
| Serial terminal | `picocom` (installed with apt) |

### USB devices (as seen by Linux)

| Device | USB ID | Linux name | Purpose |
|---|---|---|---|
| Digilent FT232H | `0403:6014` | `/dev/ttyUSB0` | JTAG. Disappears while Vitis's `hw_server` uses it — this is normal |
| Cypress USB-UART | `04b4:0008` | `/dev/ttyACM0` | UART — program output appears here |

### Useful commands

```bash
# Open the serial console (exit: Ctrl+A, release, then Ctrl+X)
sudo picocom -b 115200 /dev/ttyACM0

# Start Vivado with the project
source ~/Desktop/vivado_install/Vivado/2024.1/settings64.sh
vivado ~/Desktop/venkat/vitis/vitis_helloladdu/vitis_helloladdu.xpr

# Start Vitis with the workspace
source ~/Desktop/vivado_install/Vitis/2024.1/settings64.sh
vitis -w ~/Desktop/venkat/vitis_workspace

# Check the board is visible (use a FRESH terminal, not one where settings64.sh was sourced)
lsusb
ls /dev/ttyUSB* /dev/ttyACM*
sudo dmesg | tail -20

# Reset a stuck JTAG server
pkill hw_server
```

---

## 3. Folder and file map

### Top-level layout

```
/home/sreevenkat/Desktop/venkat/
├── vitis/                              ← Vivado side
│   ├── vitis_helloladdu/               ← MAIN Vivado project (all work done here)
│   ├── ip_repo/                        ← custom IP repository (adder_ip)
│   ├── m0_step1_hello/                 ← backup: Hello World design
│   ├── m0_step2_gpio/                  ← backup: + AXI GPIO
│   ├── m0_step3_adder/                 ← backup: + custom adder IP
│   └── m0_complete/                    ← backup: + AXI DMA (full M0, with run results)
└── vitis_workspace/                    ← Vitis side
    ├── zed_platform/                   ← platform built from the .xsa
    ├── my_app/                         ← Step 1: Hello World
    ├── gpio_app/                       ← Step 2: switches → LEDs
    ├── adder_app/                      ← Step 3: adder IP test
    └── dma_app/                        ← Step 4: DMA loopback test
```

### Vivado project: `vitis_helloladdu`

Full path: `/home/sreevenkat/Desktop/venkat/vitis/vitis_helloladdu/`

| File / folder | What it is |
|---|---|
| `vitis_helloladdu.xpr` | Project file (open this in Vivado — not by double-clicking, it opens in a browser) |
| `design_1_wrapper.xsa` | **Exported hardware** (with bitstream). Re-exported after every hardware change and given to Vitis |
| `vitis_helloladdu.srcs/sources_1/bd/design_1/design_1.bd` | The block design `design_1` (standard Vivado location) |
| `vitis_helloladdu.gen/sources_1/bd/design_1/hdl/design_1_wrapper.v` | HDL wrapper (Verilog, managed by Vivado) |
| `vitis_helloladdu.runs/synth_1/` | Synthesis run |
| `vitis_helloladdu.runs/impl_1/design_1_wrapper.bit` | Bitstream (standard Vivado location) |
| `vitis_helloladdu.cache/`, `.hw/`, `.ip_user_files/`, `.sim/` | Vivado internal folders |

Project settings: name `vitis_helloladdu`, part **Zedboard (xc7z020clg484-1)**, board part `digilentinc.com:zedboard:part0:1.1` (rev D.3), top module `design_1_wrapper`, target language Verilog.

### Custom IP repository: `ip_repo`

Full path: `/home/sreevenkat/Desktop/venkat/vitis/ip_repo/`

| File / folder | What it is |
|---|---|
| `adder_ip_1_0/` | Packaged IP `adder_ip` v1.0 (root directory of the IP) |
| `adder_ip_1_0/component.xml` | IP-XACT description used by Vivado's IP catalog |
| `adder_ip_1_0/hdl/adder_ip.v` | Top-level wrapper of the IP (not edited) |
| `adder_ip_1_0/hdl/adder_ip_slave_lite_v1_0_S00_AXI.v` | AXI-Lite slave with the 4 registers — **the file we edited** |
| `edit_adder_ip_v1_0.xpr` | Temporary IP-editing project (removed automatically after Re-Package) |

### Vitis workspace

Full path: `/home/sreevenkat/Desktop/venkat/vitis_workspace/`

| File / folder | What it is |
|---|---|
| `zed_platform/` | Platform component, built from `design_1_wrapper.xsa` |
| `zed_platform/hw/sdt/` | System device tree generated from the .xsa |
| `zed_platform/zynq_fsbl/` | First Stage Boot Loader domain (`fsbl.elf`) |
| `zed_platform/ps7_cortexa9_0/standalone_ps7_cortexa9_0/bsp/` | Board support package for our apps |
| `zed_platform/export/zed_platform/sw/standalone_ps7_cortexa9_0/include/` | BSP headers incl. `xparameters.h`, `xaxidma.h` |
| `zed_platform/export/zed_platform/hw/design_1_wrapper.xsa` | Copy of the hardware used by the platform |
| `<app>/src/main.c` | Our C code for each app |
| `<app>/src/lscript.ld` | Linker script (program loads into DDR at `0x00100000`) |
| `<app>/build/<app>.elf` | Built program |
| `<app>/_ide/bitstream/design_1_wrapper.bit` | Bitstream Vitis programs before running |
| `<app>/_ide/psinit/ps7_init.tcl` | PS initialisation script (clocks, DDR) run before the app |
| `<app>/_ide/launch.json` | Run configuration (shown as **Settings → launch.json** in Vitis) |

---

## 4. Final hardware design (`design_1`)

### Blocks

| Block | IP | Purpose |
|---|---|---|
| `processing_system7_0` | ZYNQ7 Processing System | ARM, DDR, UART1 (MIO 48–49), clocks; **M_AXI_GP0** and **S_AXI_HP0** enabled |
| `rst_ps7_0_100M` | Processor System Reset | Resets for all PL blocks (100 MHz FCLK_CLK0) |
| `ps7_0_axi_periph` | AXI Interconnect (1 slave → 4 masters) | GP0 → control registers (M00–M03) |
| `axi_gpio_0` | AXI GPIO | 8 LEDs (`leds_8bits`) |
| `axi_gpio_1` | AXI GPIO | 8 DIP switches (`sws_8bits`) |
| `adder_ip_0` | adder_ip v1.0 (custom) | AXI-Lite adder |
| `axi_dma_0` | AXI Direct Memory Access 7.1 | Moves data DDR ↔ stream |
| `axis_data_fifo_0` | AXI4-Stream Data FIFO | Loops the stream back (MM2S → S2MM) |
| `axi_mem_intercon` | AXI Interconnect (2 slaves → 1 master) | DMA MM2S + S2MM → **S_AXI_HP0** → DDR |

### Data paths

```
Control (AXI4-Lite):  ARM ─M_AXI_GP0─► ps7_0_axi_periph ─► axi_gpio_0 / axi_gpio_1 / adder_ip_0 / axi_dma_0 (S_AXI_LITE)

Data (AXI4 + Stream): DDR ◄─S_AXI_HP0─ axi_mem_intercon ◄─ axi_dma_0 (M_AXI_MM2S, M_AXI_S2MM)
                      axi_dma_0 M_AXIS_MM2S ─► axis_data_fifo_0 ─► axi_dma_0 S_AXIS_S2MM
```

### Address map (Vivado Address Editor)

**ARM view (`/processing_system7_0/Data`):**

| Block | Base address | Range |
|---|---|---|
| `axi_dma_0/S_AXI_LITE` | `0x4040_0000` | 64K |
| `axi_gpio_0/S_AXI` (LEDs) | `0x4120_0000` | 64K |
| `axi_gpio_1/S_AXI` (switches) | `0x4121_0000` | 64K |
| `adder_ip_0/S00_AXI` | `0x43C0_0000` | 64K |

**DMA view:**

| Master | Slave | Address range |
|---|---|---|
| `axi_dma_0/Data_MM2S` | `S_AXI_HP0` → `HP0_DDR_LOWOCM` | `0x0000_0000` – `0x1FFF_FFFF` (512 MB) |
| `axi_dma_0/Data_S2MM` | `S_AXI_HP0` → `HP0_DDR_LOWOCM` | `0x0000_0000` – `0x1FFF_FFFF` (512 MB) |

### Key IP settings

**ZYNQ7 PS:** board preset applied (UART1, DDR, clocks); PS-PL Configuration → HP Slave AXI Interface → **S AXI HP0 enabled**.

**AXI DMA (`axi_dma_0`):**

| Setting | Value |
|---|---|
| Enable Scatter Gather Engine | **Off** (Simple mode) |
| Width of Buffer Length Register | **26 bits** (max 64 MB per transfer; default 14 bits only allows ~16 KB) |
| Address Width | 32 |
| Read channel: MM data width / stream width / burst | 32 / 32 / 16 |
| Write channel: MM data width / stream width / burst | 32 / 32 / 16 |
| Allow Unaligned Transfers | Off |

**AXI4-Stream Data FIFO:** default settings.

---

## 5. Step 1 — Hello World

### Vivado

1. Created project `vitis_helloladdu`, changed the target from bare chip `xc7z020clg484-3` to the **Zedboard** board.
2. Block design `design_1`: added ZYNQ7 Processing System → Run Block Automation with **Apply Board Preset**.
3. Connected `FCLK_CLK0 → M_AXI_GP0_ACLK`.
4. Validated (only the 4 normal DDR warnings PSU-1 to PSU-4).
5. Created HDL wrapper (`design_1_wrapper`, Verilog, managed by Vivado) → Generate Bitstream → Export Hardware with bitstream → `design_1_wrapper.xsa`.

### Vitis

- Workspace: `/home/sreevenkat/Desktop/venkat/vitis_workspace`
- Platform `zed_platform` from `design_1_wrapper.xsa`, OS standalone, processor `ps7_cortexa9_0`, domains `zynq_fsbl` and `standalone_ps7_cortexa9_0`.
- BSP: `standalone_stdin` = `standalone_stdout` = `ps7_uart_1`.
- App `my_app` (empty application), file `my_app/src/main.c`:

```c
#include "xil_printf.h"   // for xil_printf() - prints to the UART
#include "sleep.h"        // for sleep()

int main(void)
{
    int count = 0;

    xil_printf("My first Zynq program started!\r\n");

    while (1) {
        xil_printf("Hello from Zynq! count = %d\r\n", count);
        count++;
        sleep(1);         // wait 1 second
    }

    return 0;
}
```

**Run:** Vitis programmed the FPGA, ran `ps7_init`, loaded `my_app.elf` into DDR at `0x00100000`, and started the ARM.
**Output:** `Hello from Zynq! count = 0, 1, 2 …` every second ✅

---

## 6. Step 2 — AXI GPIO (switches → LEDs)

### Vivado

1. Board tab → double-clicked **LED** → AXI GPIO → GPIO → created `axi_gpio_0` (→ `leds_8bits`).
2. Board tab → double-clicked **DIP switches** → *new* AXI GPIO → created `axi_gpio_1` (→ `sws_8bits`).
3. Run Connection Automation (All) → added `ps7_0_axi_periph` and `rst_ps7_0_100M`.
4. Validate → Save → Generate Bitstream → Export Hardware (overwrite `design_1_wrapper.xsa`).

### Vitis

1. `zed_platform` → Settings → `vitis-comp.json` → **Switch XSA** → new .xsa → Build platform.
2. New application `gpio_app` (platform `zed_platform`, domain `standalone_ps7_cortexa9_0`).

File `gpio_app/src/main.c`:

```c
#include "xil_io.h"
#include "xil_printf.h"

#define LED_ADDR  0x41200000   // axi_gpio_0 -> LEDs
#define SW_ADDR   0x41210000   // axi_gpio_1 -> switches

int main(void)
{
    xil_printf("GPIO test started\r\n");

    // Direction register (offset 0x4): 0 = output, 1 = input
    Xil_Out32(LED_ADDR + 0x4, 0x00);   // LEDs are outputs
    Xil_Out32(SW_ADDR  + 0x4, 0xFF);   // switches are inputs

    u32 old = 0xFFFF;

    while (1) {
        u32 sw = Xil_In32(SW_ADDR) & 0xFF;   // read switches (offset 0x0)
        Xil_Out32(LED_ADDR, sw);             // write LEDs  (offset 0x0)

        if (sw != old) {                     // print only when switches change
            xil_printf("switches = 0x%x\r\n", sw);
            old = sw;
        }
    }

    return 0;
}
```

**Output:** `GPIO test started`, then `switches = 0x…` on every change; each LED follows its switch ✅
**Note:** quick `0x0 / 0x1 / 0x0 …` lines at the start are mechanical **switch bounce** — normal.

---

## 7. Step 3 — Custom AXI-Lite IP (`adder_ip`)

### Create the IP

1. Vivado → Tools → Create and Package New IP → **Create a new AXI4 peripheral**.
2. Name `adder_ip`, version 1.0, location `/home/sreevenkat/Desktop/venkat/vitis/ip_repo`.
3. Interface `S00_AXI`, type **Lite**, mode **Slave**, data width 32, **4 registers**.
4. Chose **Edit IP** → opened project `edit_adder_ip_v1_0`.

### The Verilog change

File: `ip_repo/adder_ip_1_0/hdl/adder_ip_slave_lite_v1_0_S00_AXI.v`

Only the **read** line was changed (the write `case` for `2'h2` was left alone). Register 2 now returns `slv_reg0 + slv_reg1`:

```verilog
assign S_AXI_RDATA = (axi_araddr[ADDR_LSB+OPT_MEM_ADDR_BITS:ADDR_LSB] == 2'h0) ? slv_reg0 :
                     (axi_araddr[ADDR_LSB+OPT_MEM_ADDR_BITS:ADDR_LSB] == 2'h1) ? slv_reg1 :
                     (axi_araddr[ADDR_LSB+OPT_MEM_ADDR_BITS:ADDR_LSB] == 2'h2) ? (slv_reg0 + slv_reg1) :
                     (axi_araddr[ADDR_LSB+OPT_MEM_ADDR_BITS:ADDR_LSB] == 2'h3) ? slv_reg3 : 0;
```

Register map: `0x00` = reg0 (A), `0x04` = reg1 (B), `0x08` = A + B (read), `0x0C` = reg3 (unused).

### Package and add to the design

1. Package IP tab → Review and Package → **Merge changes** → **Re-Package IP** → closed the edit project.
   (Yellow warnings on Customization Parameters / Ports and Interfaces are normal template warnings.)
2. In `vitis_helloladdu`: Add IP → `adder_ip_v1.0` → `adder_ip_0` → Run Connection Automation (interconnect gained `M02_AXI`).
3. Address: `0x43C0_0000`. Validate → Save → Generate Bitstream → Export Hardware.

### Vitis

Switch XSA → Build platform → new application `adder_app`. File `adder_app/src/main.c`:

```c
#include "xil_io.h"
#include "xil_printf.h"

#define ADDER_ADDR  0x43C00000   // adder_ip_0 (from Vivado Address Editor)

int main(void)
{
    xil_printf("\r\n--- Adder IP test ---\r\n");

    // Test 1: the classic 25 + 17
    Xil_Out32(ADDER_ADDR + 0x00, 25);     // write reg0
    Xil_Out32(ADDER_ADDR + 0x04, 17);     // write reg1
    u32 sum = Xil_In32(ADDER_ADDR + 0x08); // read reg2 = reg0 + reg1
    xil_printf("25 + 17 = %d\r\n", sum);

    // Test 2: a few more pairs, checked automatically
    u32 a[] = {0, 1, 100, 12345, 70000};
    u32 b[] = {0, 1, 200, 54321, 30000};
    int errors = 0;

    for (int i = 0; i < 5; i++) {
        Xil_Out32(ADDER_ADDR + 0x00, a[i]);
        Xil_Out32(ADDER_ADDR + 0x04, b[i]);
        u32 hw = Xil_In32(ADDER_ADDR + 0x08);
        u32 sw = a[i] + b[i];
        xil_printf("%d + %d = %d  (expected %d) %s\r\n",
                   a[i], b[i], hw, sw, (hw == sw) ? "OK" : "FAIL");
        if (hw != sw) errors++;
    }

    if (errors == 0) xil_printf("ALL TESTS PASSED\r\n");
    else             xil_printf("%d TESTS FAILED\r\n", errors);

    while (1);   // stay here
    return 0;
}
```

**Output:**
```
--- Adder IP test ---
25 + 17 = 42
0 + 0 = 0  (expected 0) OK
1 + 1 = 2  (expected 2) OK
100 + 200 = 300  (expected 300) OK
12345 + 54321 = 66666  (expected 66666) OK
70000 + 30000 = 100000  (expected 100000) OK
ALL TESTS PASSED
```

---

## 8. Step 4 — AXI DMA loopback

### Vivado

1. ZYNQ7 PS → PS-PL Configuration → HP Slave AXI Interface → enabled **S AXI HP0**.
2. Added **AXI Direct Memory Access** (`axi_dma_0`) with the settings in Section 4 (no SG, 26-bit length).
3. Added **AXI4-Stream Data FIFO** (`axis_data_fifo_0`).
4. Connected the stream loop in the **Tcl Console** (dragging was fiddly):
   ```tcl
   connect_bd_intf_net [get_bd_intf_pins axi_dma_0/M_AXIS_MM2S] [get_bd_intf_pins axis_data_fifo_0/S_AXIS]
   connect_bd_intf_net [get_bd_intf_pins axis_data_fifo_0/M_AXIS] [get_bd_intf_pins axi_dma_0/S_AXIS_S2MM]
   ```
5. Run Connection Automation (All) → added `axi_mem_intercon` (DMA → HP0), DMA `S_AXI_LITE` on `M03_AXI`, FIFO clock/reset.
6. Validate (only PSU-1..4 DDR warnings) → Save → Generate Bitstream → Export Hardware.

### Vitis

Switch XSA → Build platform (`axidma` driver added automatically) → new application `dma_app`.

**Launch fix:** in `dma_app` → Settings → `launch.json`, changed the initialization file from
`${workspaceFolder}/dma_app/_ide/psinit/adder_ip.tcl` to
`${workspaceFolder}/dma_app/_ide/psinit/ps7_init.tcl` (see Section 9).

File `dma_app/src/main.c`:

```c
#include "xaxidma.h"
#include "xil_cache.h"
#include "xil_printf.h"
#include "xparameters.h"

#define DMA_ADDR  0x40400000          // axi_dma_0 (from Vivado Address Editor)
#define MAXN      (1024 * 1024)       // 1 MB, the biggest test

// Buffers in DDR. They MUST be global (not inside main), or the 1 MB
// arrays would overflow the stack and the board would hang.
static u8 src[MAXN] __attribute__((aligned(64)));
static u8 dst[MAXN] __attribute__((aligned(64)));
static XAxiDma dma;

static int dma_test(u32 n, u8 seed)
{
    // 1. Fill src with a pattern, clear dst
    for (u32 i = 0; i < n; i++) {
        src[i] = (u8)(i * 7 + seed);
        dst[i] = 0;
    }

    // 2. CACHE FLUSH: push the ARM's cached data out to real DDR,
    //    because the DMA reads DDR directly and can't see the cache
    Xil_DCacheFlushRange((UINTPTR)src, n);
    Xil_DCacheFlushRange((UINTPTR)dst, n);

    // 3. Start the receive side first (S2MM: stream -> DDR),
    //    then the send side (MM2S: DDR -> stream)
    int st = XAxiDma_SimpleTransfer(&dma, (UINTPTR)dst, n, XAXIDMA_DEVICE_TO_DMA);
    if (st != XST_SUCCESS) { xil_printf("  S2MM start failed (%d)\r\n", st); return 1; }

    st = XAxiDma_SimpleTransfer(&dma, (UINTPTR)src, n, XAXIDMA_DMA_TO_DEVICE);
    if (st != XST_SUCCESS) { xil_printf("  MM2S start failed (%d)\r\n", st); return 1; }

    // 4. Wait for both directions to finish (with a timeout so we never hang)
    u32 timeout = 100000000;
    while ((XAxiDma_Busy(&dma, XAXIDMA_DMA_TO_DEVICE) ||
            XAxiDma_Busy(&dma, XAXIDMA_DEVICE_TO_DMA)) && --timeout) { }

    if (timeout == 0) {
        xil_printf("  TIMEOUT! MM2S status=0x%x  S2MM status=0x%x\r\n",
                   XAxiDma_ReadReg(DMA_ADDR, XAXIDMA_TX_OFFSET + XAXIDMA_SR_OFFSET),
                   XAxiDma_ReadReg(DMA_ADDR, XAXIDMA_RX_OFFSET + XAXIDMA_SR_OFFSET));
        return 1;
    }

    // 5. CACHE INVALIDATE: throw away old cached copies of dst,
    //    so the ARM reads what the DMA actually wrote into DDR
    Xil_DCacheInvalidateRange((UINTPTR)dst, n);

    // 6. Compare byte by byte
    u32 errors = 0;
    for (u32 i = 0; i < n; i++) {
        if (dst[i] != src[i]) {
            if (errors < 5)
                xil_printf("  mismatch at %d: sent 0x%x, got 0x%x\r\n", i, src[i], dst[i]);
            errors++;
        }
    }

    if (errors == 0) xil_printf("  %d bytes OK\r\n", n);
    else             xil_printf("  %d bytes: %d ERRORS\r\n", n, errors);
    return errors ? 1 : 0;
}

int main(void)
{
    xil_printf("\r\n--- AXI DMA loopback test ---\r\n");

    XAxiDma_Config *cfg = XAxiDma_LookupConfig(DMA_ADDR);
    if (cfg == NULL) { xil_printf("DMA config not found\r\n"); return 1; }

    if (XAxiDma_CfgInitialize(&dma, cfg) != XST_SUCCESS) {
        xil_printf("DMA init failed\r\n"); return 1;
    }
    if (XAxiDma_HasSg(&dma)) {
        xil_printf("DMA is in Scatter-Gather mode, expected Simple mode\r\n"); return 1;
    }

    // We use polling, so switch the interrupts off
    XAxiDma_IntrDisable(&dma, XAXIDMA_IRQ_ALL_MASK, XAXIDMA_DEVICE_TO_DMA);
    XAxiDma_IntrDisable(&dma, XAXIDMA_IRQ_ALL_MASK, XAXIDMA_DMA_TO_DEVICE);

    int fails = 0;
    xil_printf("Test 1: 256 B\r\n");   fails += dma_test(256,         3);
    xil_printf("Test 2: 64 KB\r\n");   fails += dma_test(64 * 1024,   5);
    xil_printf("Test 3: 1 MB\r\n");    fails += dma_test(1024 * 1024, 9);

    if (fails == 0) xil_printf("ALL DMA TESTS PASSED\r\n");
    else            xil_printf("%d DMA TEST(S) FAILED\r\n", fails);

    while (1);
    return 0;
}
```

Note: in Vitis 2024.1 (SDT flow), `XAxiDma_LookupConfig()` takes the **base address**, not a device ID.

**Output:**
```
--- AXI DMA loopback test ---
Test 1: 256 B
  256 bytes OK
Test 2: 64 KB
  65536 bytes OK
Test 3: 1 MB
  1048576 bytes OK
ALL DMA TESTS PASSED
```

---

## 9. Problems hit and how they were solved

| Problem | Cause | Fix |
|---|---|---|
| Program ran but no output (first attempt, `basic_vitis` workspace) | Project used only the chip, no board, so UART/board preset wasn't applied | Selected the ZedBoard board and rebuilt everything |
| ZedBoard not in the Boards list | Board files not installed | Copied Digilent board files into Vivado's `board_files` folder |
| `cannot open /dev/ttyUSB1` | That port doesn't exist on ZedBoard | UART is `/dev/ttyACM0` |
| picocom: `read zero bytes` / `Input/output error` | Opened `ttyUSB0` (JTAG), or the board was reconnecting | Use `/dev/ttyACM0`; restart picocom after replugging |
| `ttyACM0` missing once | Board still reconnecting | Checked with `ls`, retried |
| Red errors in `main.c` (`xil_printf.h` / `xil_io.h` not found, `u32` undeclared) | Editor checker (clangd) only, before the first build | Ignored; the real build succeeded |
| "could not load cache" | Clean run before any build existed | Harmless |
| Couldn't exit picocom | Keys pressed together | Ctrl+A, release, then Ctrl+X |
| `.xpr` opened in the web browser | Ubuntu treats it as an XML/web file | Open from Vivado (Open Project) or `vivado <path>.xpr` |
| Accidentally working in the backup project | Vivado's Save As switches to the copy | Close Project, reopen `vitis_helloladdu.xpr`; always check the title bar |
| Built `my_app` instead of `gpio_app` | Flow panel Component was still `my_app` | Always set **Component** before Build/Run |
| `Could not find ARM device on the board for connection 'Local'` | JTAG/hw_server stuck | Board power on, `pkill hw_server`, unplug/replug PROG cable, Run again |
| `lsusb: undefined symbol: libusb_get_port_numbers` | Terminal had Vitis `settings64.sh` sourced (wrong libusb) | Run `lsusb` in a fresh terminal |
| Dragging stream wires in the block design didn't work | Must start on the pin stub, not the text | Used `connect_bd_intf_net` in the Tcl Console |
| `invalid command name "ps7_init"` when running `dma_app` | Vitis 2024.1 picked `_ide/psinit/adder_ip.tcl` (custom IP helper) instead of `ps7_init.tcl` | In `dma_app` → Settings → `launch.json`, set init file to `${workspaceFolder}/dma_app/_ide/psinit/ps7_init.tcl`. Check this for every new app |
| Validation warnings PSU-1..PSU-4 (negative DQS delay) | ZedBoard DDR preset | Normal, ignored |
| `ps7_init.c: In function 'ps7_config'` during platform build | Xilinx-generated FSBL code | Harmless warning |

---

## 10. Concepts (for the last checklist item)

### The three AXI types

| Type | Used for | In this milestone |
|---|---|---|
| **AXI4-Lite** | A few control/status registers, one 32-bit access at a time | GPIO, adder IP, DMA control port (`0x4040_0000`) via `M_AXI_GP0` |
| **AXI4 (memory-mapped)** | Bulk reads/writes of memory with addresses and bursts | DMA `M_AXI_MM2S` / `M_AXI_S2MM` → `axi_mem_intercon` → `S_AXI_HP0` → DDR |
| **AXI4-Stream** | Continuous data flow, **no addresses** (data + valid/ready + `TLAST`) | DMA `M_AXIS_MM2S` → FIFO → DMA `S_AXIS_S2MM` (later: pixels into the CNN) |

### DMA channels

- **MM2S** (memory-mapped to stream): DDR → FPGA
- **S2MM** (stream to memory-mapped): FPGA → DDR
- Start S2MM (receive) first, then MM2S (send), then poll both with `XAxiDma_Busy()`.

### Why the cache flush and invalidate

The ARM keeps copies of memory in its data cache; the DMA reads and writes DDR directly and cannot see the cache.

- **`Xil_DCacheFlushRange` before the DMA reads:** pushes data the ARM wrote (still in cache) out to DDR, so the DMA sends the right bytes.
- **`Xil_DCacheInvalidateRange` before the ARM reads:** discards stale cached copies, so the ARM reads what the DMA actually wrote to DDR.
- Forgetting either gives "random" wrong or partly zero data — the most common DMA bug.

### Other rules learned

- Large buffers (1 MB) must be **global**, not local variables, or they overflow the stack.
- Buffers aligned to 64 bytes (`__attribute__((aligned(64)))`) to match cache lines.
- DMA **Width of Buffer Length Register** limits the max transfer size: 14 bits ≈ 16 KB, 26 bits = 64 MB.
- AXI GPIO registers: offset `0x0` = data, offset `0x4` = direction (0 = output, 1 = input; resets to all inputs).

---

## 11. Standard workflow after any hardware change

1. **Vivado:** edit the block design → Validate (F6) → Ctrl+S.
2. **Generate Bitstream** (Yes → OK; Cancel on the completion popup).
3. **File → Export → Export Hardware → Include bitstream** → overwrite `vitis/vitis_helloladdu/design_1_wrapper.xsa`.
4. **Vitis:** `zed_platform` → Settings → `vitis-comp.json` → **Switch XSA** → pick the new .xsa → Flow: Component = `zed_platform` → **Build**.
5. Create or rebuild the app (Flow: Component = app → Build). Check the app's `launch.json` init file is `ps7_init.tcl`.
6. `sudo picocom -b 115200 /dev/ttyACM0` → Vitis **Run**.
7. Before a new step, back up the Vivado project with **File → Project → Save As**, then reopen `vitis_helloladdu.xpr`.

---

## 12. Backups

| Backup project | Location | Contains |
|---|---|---|
| `m0_step1_hello` | `/home/sreevenkat/Desktop/venkat/vitis/m0_step1_hello/` | ZYNQ PS only (Hello World) |
| `m0_step2_gpio` | `/home/sreevenkat/Desktop/venkat/vitis/m0_step2_gpio/` | + AXI GPIO (LEDs, switches) |
| `m0_step3_adder` | `/home/sreevenkat/Desktop/venkat/vitis/m0_step3_adder/` | + custom `adder_ip` |
| `m0_complete` | `/home/sreevenkat/Desktop/venkat/vitis/m0_complete/` | + AXI DMA + FIFO (full M0), with run results/bitstream |
