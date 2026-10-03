# M0 — Zynq Basics: ARM, FPGA, AXI and DMA

**Time:** 1–1.5 weeks | **Where:** ZedBoard + Vivado/Vitis | **Depends on:** nothing

---

## 1. Why this milestone exists

Your RISC-V project lived entirely in the FPGA part ("PL"). This project needs the **ARM processor ("PS")** to talk to
the FPGA and move images through DDR memory. You have not done that yet. If you skip this, every later milestone fails
for reasons that look like "my CNN is broken" but are really "my AXI wiring is broken".

The goal is **not** super-resolution yet. The goal is to prove four things on a trivial design:

1. The ARM boots and prints text.
2. The ARM can read/write a register that lives in the FPGA.
3. You can make your **own** FPGA peripheral that the ARM controls.
4. You can push a block of data DDR → FPGA → DDR with DMA and get it back unchanged.

---

## 2. Concepts you must understand first

### PS and PL
The Zynq chip has two halves on one piece of silicon.

```
┌──────────────── Zynq XC7Z020 ────────────────┐
│  PS (Processing System)   │  PL (FPGA fabric) │
│  ARM cores, DDR controller│  Your Verilog     │
│  UART, SD, Ethernet       │  CNN accelerator  │
└───────────────┬───────────┴─────────┬─────────┘
                └──── AXI buses ──────┘
```

The DDR3 memory is wired to the **PS**. The PL can reach it only through AXI ports.

### Memory-mapped I/O
The ARM sees the FPGA peripherals as memory addresses. Writing to address `0x41200000` might turn on LEDs.
In C that is just: `*(volatile unsigned int*)0x41200000 = 0xFF;` (or `Xil_Out32(addr, value)`).

### The three AXI types (never mix them up)

| Type | Used for | In this project |
|---|---|---|
| **AXI4-Lite** | A few control/status registers | Start, done, width, height, addresses |
| **AXI4 (memory-mapped)** | Reading/writing DDR in bulk | The DMA does this for you |
| **AXI4-Stream** | A continuous flow of data, no addresses | Pixels flowing into and out of the CNN |

### What DMA is
**D**irect **M**emory **A**ccess: a small hardware block that copies data between DDR and an AXI-Stream, so the ARM
does not copy pixels one by one. The Xilinx **AXI DMA** IP has two channels:
- **MM2S** (memory-mapped → stream): DDR → FPGA
- **S2MM** (stream → memory-mapped): FPGA → DDR

---

## 3. Step-by-step

### Step 1 — Hello world on the ARM
1. In Vivado create a project for the ZedBoard (install the Digilent ZedBoard board files if it is not listed).
2. Create a Block Design. Add **ZYNQ7 Processing System**. Click **Run Block Automation** (it sets up DDR and clocks for the ZedBoard).
3. Create HDL wrapper → Generate Bitstream → **File → Export Hardware (include bitstream)**.
4. In Vitis create a platform from the exported `.xsa`, then a *Hello World* application (standalone / bare-metal).
5. Connect the micro-USB cable to the **UART** port, open a terminal at **115200 baud, 8N1**
   (`screen /dev/ttyACM0 115200`).
6. Run the app on the board. You should see `Hello World`.

**Why:** this is your `printf` debugging channel for the whole project.
**Output:** text in the serial terminal, every time you power-cycle.

### Step 2 — AXI GPIO (LEDs and switches)
1. In the block design add **AXI GPIO** (one channel, 8 bits output → LEDs; a second one 8 bits input → switches).
2. **Run Connection Automation**. Vivado adds the AXI interconnect and reset blocks.
3. Assign the pins to the ZedBoard LEDs/switches (the board preset usually provides this; otherwise an `.xdc` file).
4. Re-export hardware, then in C:

```c
#include "xparameters.h"
#include "xil_io.h"
#include "xil_printf.h"

int main() {
    while (1) {
        u32 sw = Xil_In32(XPAR_AXI_GPIO_1_BASEADDR);   // read switches
        Xil_Out32(XPAR_AXI_GPIO_0_BASEADDR, sw);       // show them on LEDs
    }
}
```
(The macro names depend on what Vivado named your blocks; look in `xparameters.h`.)

**Why:** this is the smallest possible "ARM talks to FPGA" example. Your accelerator's control registers will work the same way.
**Output:** flipping a switch turns on the matching LED.

### Step 3 — Your own AXI-Lite peripheral
1. In Vivado: **Tools → Create and Package New IP → Create a new AXI4 peripheral**. Choose **AXI4-Lite, Slave, 4 registers**.
   Vivado generates a Verilog file that already contains the AXI handshake. **Do not write AXI-Lite from scratch.**
2. Edit the generated file so that reading register 2 returns `reg0 + reg1`.
3. Add the IP to your block design, connect it, re-export.
4. In C:

```c
Xil_Out32(MYIP_BASEADDR + 0x00, 25);
Xil_Out32(MYIP_BASEADDR + 0x04, 17);
u32 sum = Xil_In32(MYIP_BASEADDR + 0x08);
xil_printf("sum = %d\r\n", sum);   // expect 42
```

**Why:** later your CNN accelerator gets exactly this kind of register block (start bit, width, height, base address…).
**Output:** `sum = 42` on the terminal.

### Step 4 — AXI DMA round-trip (the hardest part of M0)
1. Add **AXI DMA** (Simple mode: **disable Scatter Gather**), 32-bit width, 8-bit or 32-bit stream.
2. Add an **AXI4-Stream Data FIFO** and connect `M_AXIS_MM2S → FIFO → S_AXIS_S2MM`. (This loops data straight back.)
3. Connect DMA's memory-mapped master (`M_AXI_MM2S`, `M_AXI_S2MM`) to the PS **HP0** port (enable it in the Zynq settings).
   Connection Automation does most of this.
4. In C (bare-metal, polling), use Xilinx's `xaxidma` driver. The Vitis example *xaxidma_simple_poll* is a good starting point:

```c
#define N 256
u8 src[N] __attribute__((aligned(64)));
u8 dst[N] __attribute__((aligned(64)));

for (int i = 0; i < N; i++) { src[i] = i; dst[i] = 0; }
Xil_DCacheFlushRange((UINTPTR)src, N);          // make sure DDR has the data
XAxiDma_SimpleTransfer(&dma, (UINTPTR)dst, N, XAXIDMA_DEVICE_TO_DMA);
XAxiDma_SimpleTransfer(&dma, (UINTPTR)src, N, XAXIDMA_DMA_TO_DEVICE);
while (XAxiDma_Busy(&dma, XAXIDMA_DMA_TO_DEVICE) ||
       XAxiDma_Busy(&dma, XAXIDMA_DEVICE_TO_DMA)) {}
Xil_DCacheInvalidateRange((UINTPTR)dst, N);     // read fresh data, not stale cache
// compare src and dst byte by byte
```

**Cache warning (very common bug):** the ARM has a data cache. Flush before the DMA reads memory, invalidate before the
ARM reads what the DMA wrote. Forgetting this gives "random" wrong data.

**Why:** this exact mechanism will carry your image tiles in and out of the CNN.
**Output:** all 256 bytes match. Then repeat with 64 KB, then 1 MB.

---

## 4. Exit checklist (all must be true)

- [ ] Hello World prints after every power cycle.
- [ ] Switches control LEDs through AXI GPIO.
- [ ] Your own AXI-Lite IP returns the correct sum.
- [ ] DMA loopback of 256 B, 64 KB and 1 MB is byte-exact.
- [ ] You can explain, in your own words, AXI-Lite vs AXI4 vs AXI-Stream, and why you need `Xil_DCacheFlushRange`.

## 5. Common problems

| Symptom | Likely cause |
|---|---|
| Board not found in Vivado | Board files not installed |
| Nothing in terminal | Wrong serial port, wrong baud, or using the JTAG port instead of the UART port |
| ARM hangs when touching the peripheral | Peripheral not in the address map, bitstream not loaded, or wrong base address |
| DMA data wrong/partly zero | Cache flush/invalidate missing, buffer not aligned, DMA length wrong |
| DMA never finishes | Stream `TLAST` missing or FIFO not connected |
