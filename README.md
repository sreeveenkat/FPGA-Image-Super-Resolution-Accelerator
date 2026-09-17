# FPGA-Based Sparse Ray Tracing and AI 4K Reconstruction Accelerator

A hardware-software co-designed FPGA accelerator that combines **low-resolution ray tracing** with **quantized neural image reconstruction** to generate high-resolution images efficiently on a Xilinx Zynq-7020 platform.

> **Project status:** Active development / research prototype
> **Target platform:** Digilent ZedBoard — Zynq-7020
> **HDL:** Verilog / SystemVerilog
> **Software:** C++, Python
> **FPGA Tools:** Xilinx Vivado, Vitis / Bare-metal SDK
> **AI:** PyTorch, ONNX
> **Verification:** cocotb, pytest
> **CI:** GitHub Actions

---

## Overview

The project explores a complete FPGA-based rendering and reconstruction pipeline:

```text
                 ┌──────────────────────┐
                 │       Host PC        │
                 │   C++ / Python       │
                 └──────────┬───────────┘
                            │
                            ▼
                 ┌──────────────────────┐
                 │   Zynq ARM Processor │
                 │ Control / DMA / DDR  │
                 └──────────┬───────────┘
                            │
                 ┌──────────▼───────────┐
                 │ FPGA Ray Tracing Core│
                 │                      │
                 │ Ray Generation       │
                 │ Intersection         │
                 │ Nearest Hit          │
                 │ Shading              │
                 └──────────┬───────────┘
                            │
                            ▼
                RGB + Depth + Normals
                            │
                            ▼
                 ┌──────────────────────┐
                 │ INT8 Reconstruction  │
                 │      Accelerator     │
                 │                      │
                 │ Convolution          │
                 │ Depthwise/Pointwise  │
                 │ Pixel Shuffle        │
                 └──────────┬───────────┘
                            │
                            ▼
                       4K Frame
                    3840 × 2160
```

The main idea is to render a scene at a lower resolution and use a lightweight quantized neural network to reconstruct a higher-resolution image.

The initial target is approximately:

* **Input:** 960 × 540 = 518,400 pixels
* **Output:** 3840 × 2160 = 8,294,400 pixels
* **Upscaling:** 4× horizontally and 4× vertically
* **Pixel-count expansion:** 16×

The project is intended as an FPGA proof of concept covering **RTL design, computer architecture, AI acceleration, AXI/DMA integration, verification, memory systems, and hardware/software co-design**.

---

# Objectives

## Primary Objectives

* Develop a C++ software ray-tracing reference model.
* Implement ray generation and geometric intersection in FPGA RTL.
* Generate low-resolution:

  * RGB
  * Depth
  * Surface normals
* Train a lightweight neural reconstruction model using PyTorch.
* Quantize the model to INT8.
* Develop a streaming FPGA convolution accelerator.
* Integrate FPGA accelerators with the Zynq ARM processor.
* Use AXI4-Lite, AXI4 memory-mapped, and AXI4-Stream interfaces.
* Use DMA for frame and feature-buffer movement.
* Reconstruct a 4K image using tiled processing.
* Investigate low-cost / sparsity-aware multiplier architectures.
* Evaluate image quality, FPGA resources, timing, bandwidth, power, and latency.

---

# Feasibility and Scope

The project is intentionally scoped around what is practical on a Zynq-7020-class FPGA.

### Initial targets

* Simple scenes containing spheres and triangles.
* Low-resolution rendering.
* Fixed-point ray generation and intersection.
* Lightweight INT8 reconstruction CNN.
* Tiled high-resolution reconstruction.
* DDR-based 4K frame storage.
* Hardware resource and performance analysis.

### Not initial targets

* Real-time 4K ray tracing at 30/60 FPS.
* Large production-scale neural networks.
* Complex scenes containing millions of triangles.
* Full global illumination.
* Full commercial graphics APIs.
* Storing an entire 4K RGB frame in BRAM.

The first major success criterion is a **correct 4K reconstructed image from an FPGA-generated low-resolution ray-traced input**, accompanied by reproducible quality and hardware measurements.

---

# System Architecture

The system is divided into five major components.

| Component             | Responsibility                                           |
| --------------------- | -------------------------------------------------------- |
| Host Python           | Dataset generation, training, quantization, evaluation   |
| Host C++              | Golden renderer, reference inference, benchmarking       |
| Zynq ARM              | Accelerator control, DMA, interrupts, configuration      |
| FPGA Ray-Tracing Core | Ray generation, intersection, traversal and shading      |
| FPGA AI Core          | Quantized convolution and image reconstruction           |
| DDR                   | Scene data, weights, frame buffers and intermediate data |

---

# FPGA Ray-Tracing Pipeline

The ray-tracing datapath is planned as:

```text
Pixel Coordinate
       │
       ▼
Camera Ray Generator
       │
       ▼
Sphere / Triangle Intersection
       │
       ▼
Nearest-Hit Selection
       │
       ▼
Depth + Normal Calculation
       │
       ▼
Basic Material / Lighting
       │
       ▼
RGB + Depth + Normal
       │
       ▼
AXI Stream / DMA
       │
       ▼
DDR
```

## Ray Generation

The ray generator receives:

* Pixel coordinates
* Camera origin
* Camera orientation
* Field of view

and generates:

* Ray origin
* Ray direction
* Pixel identifier

The initial implementation uses fixed-point arithmetic where practical.

## Sphere Intersection

Sphere intersection is implemented before triangle intersection because it provides a simpler way to validate the rendering pipeline.

The unit calculates:

* Quadratic intersection terms
* Discriminant
* Nearest positive intersection
* Hit position
* Depth

## Triangle Intersection

Triangle intersection uses the **Möller-Trumbore algorithm**.

The implementation handles:

* Edge-vector calculation
* Determinant
* Barycentric coordinates
* Parallel-ray rejection
* Out-of-triangle rejection
* Nearest positive intersection

## Nearest-Hit Selection

The nearest-hit stage selects the closest valid intersection and preserves:

* Object ID
* Depth
* Surface normal
* Material ID

## Shading

The initial shader supports:

* Constant material colour
* Ambient lighting
* Lambertian diffuse lighting
* Background colour

Future extensions may include:

* Hard shadows
* One-bounce reflection
* Material lookup
* Texture sampling

---

# G-Buffer

The ray-tracing stage produces auxiliary rendering information in addition to RGB.

### Current planned channels

| Channel | Purpose                                  |
| ------- | ---------------------------------------- |
| RGB     | Base rendered colour                     |
| Depth   | Geometry and object boundaries           |
| Normals | Surface orientation and edge information |

Optional future inputs include:

* Albedo
* Confidence/sample count
* Motion vectors
* Previous frame

The initial reconstruction model focuses on **RGB + Depth + Normals**.

---

# AI Reconstruction

The reconstruction network is designed as a lightweight FPGA-friendly architecture.

### Planned structure

```text
RGB + Depth + Normals
        │
        ▼
3×3 Convolution
16/24 Channels
        │
        ▼
ReLU
        │
        ▼
3×3 Depthwise Convolution
        │
        ▼
ReLU
        │
        ▼
1×1 Pointwise Convolution
        │
        ▼
ReLU
        │
        ▼
3×3 Convolution
        │
        ▼
Pixel Shuffle ×4
        │
        ▼
4K RGB Output
```

The network is inspired by lightweight **ESPCN/FSRCNN-style architectures** and is intended to reduce FPGA computation through depthwise-separable convolution.

---

# Quantization

The AI pipeline follows:

```text
FP32 Training
      │
      ▼
FP32 Evaluation
      │
      ▼
INT8 Quantization-Aware Training
      │
      ▼
Integer Weights / Scales / Zero Points
      │
      ▼
Bit-Accurate Python Reference
      │
      ▼
FPGA RTL Implementation
```

INT4 is considered an optional optimization after the INT8 implementation is stable.

---

# FPGA AI Accelerator

The planned convolution engine contains:

* BRAM-based line buffers
* Sliding-window generation
* INT8 multipliers
* Higher-precision accumulators
* Bias addition
* Requantization
* Saturation
* Activation
* Weight reuse

The baseline implementation will use DSP-based multiplication before evaluating custom multiplier architectures.

---

# Tiled Reconstruction

A complete 4K frame is not intended to be stored entirely in BRAM.

Instead, reconstruction is performed using tiles.

Example tile sizes:

```text
64 × 64
128 × 64
```

Each tile includes halo pixels required by the convolution window.

```text
        Halo
    ┌───────────────┐
    │ ┌───────────┐ │
    │ │   Tile    │ │
    │ │           │ │
    │ └───────────┘ │
    └───────────────┘
        Halo
```

The implementation must:

* Load tile data from DDR.
* Include convolution halo regions.
* Process the tile.
* Remove overlapping borders.
* Write the valid output region back to DDR.
* Avoid visible seams between tiles.

---

# AXI and Hardware/Software Interface

The accelerator is designed around standard Zynq AXI interfaces.

### AXI4-Lite

Used for:

* Control
* Configuration
* Status
* Error reporting

### AXI4 Memory-Mapped

Used for:

* Scene data
* Frame buffers
* Neural-network weights
* Intermediate buffers

### AXI4-Stream

Used for:

* Pixel streams
* Internal accelerator data
* DMA data paths

### Interrupts

Used for:

* Frame completion
* Tile completion
* Errors
* Timeout handling

---

# Example Register Map

| Offset | Register    | Purpose                    |
| -----: | ----------- | -------------------------- |
| `0x00` | CONTROL     | Start/reset/interrupt      |
| `0x04` | STATUS      | Busy/done/error            |
| `0x08` | WIDTH       | Input width                |
| `0x0C` | HEIGHT      | Input height               |
| `0x10` | SCENE_BASE  | Scene memory address       |
| `0x14` | INPUT_BASE  | Input/G-buffer address     |
| `0x18` | OUTPUT_BASE | Output framebuffer address |
| `0x1C` | WEIGHT_BASE | Neural weights address     |
| `0x20` | TILE_CONFIG | Tile dimensions/halo       |
| `0x24` | CYCLE_COUNT | Accelerator cycle count    |
| `0x28` | STALL_COUNT | Memory/backpressure stalls |
| `0x2C` | ERROR_CODE  | Diagnostic status          |

The register map will be maintained as a separate document and mirrored in the software driver.

---

# Verification Strategy

Verification is performed at three abstraction levels.

```text
Floating-Point Reference
          │
          ▼
Bit-Accurate Integer Reference
          │
          ▼
       RTL Design
```

The RTL should primarily be compared against the bit-accurate reference.

## RTL Unit Tests

Planned verification includes:

* Fixed-point arithmetic
* Ray generator
* Sphere intersection
* Triangle intersection
* Nearest-hit reducer
* Shader
* AXI-stream packer
* Line-buffer/window generator
* MAC engine
* Quantizer
* Pixel shuffle

## System Tests

Important corner cases include:

* Empty scene
* Single sphere
* Single triangle
* Overlapping objects
* Parallel rays
* Near-zero intersections
* Maximum/minimum fixed-point values
* Tile boundaries
* Odd image dimensions
* DMA backpressure
* Reset during operation
* Invalid register configuration
* Timeout and recovery

## Verification Tools

* Python
* pytest
* C++ unit tests
* cocotb
* RTL simulation
* GitHub Actions

---

# Repository Structure

```text
fpga-ai-ray-reconstruction/
│
├── README.md
├── LICENSE
│
├── docs/
│   ├── architecture.md
│   ├── requirements.md
│   ├── register-map.md
│   ├── verification-plan.md
│   └── results.md
│
├── software/
│   ├── cpp-renderer/
│   ├── arm-driver/
│   ├── benchmark/
│   └── tests/
│
├── ai/
│   ├── dataset/
│   ├── models/
│   ├── train.py
│   ├── quantize.py
│   ├── integer_reference.py
│   └── evaluation/
│
├── rtl/
│   ├── common/
│   ├── ray_generator/
│   ├── intersection/
│   ├── shader/
│   ├── reconstruction/
│   ├── axi/
│   └── top/
│
├── verification/
│   ├── cocotb/
│   ├── vectors/
│   ├── reference/
│   └── coverage/
│
├── fpga/
│   ├── vivado/
│   ├── constraints/
│   └── scripts/
│
├── results/
│   ├── images/
│   ├── synthesis/
│   ├── timing/
│   ├── power/
│   └── benchmarks/
│
└── .github/
    └── workflows/
```

Generated Vivado build directories should **not** be committed. Commit source files, constraints, scripts, reports, small test vectors, and reproducible build instructions.

---

# Development Roadmap

| Phase | Deliverable                               |
| ----: | ----------------------------------------- |
|     1 | Requirements and repository setup         |
|     2 | C++ camera and sphere renderer            |
|     3 | Triangle intersection, depth and normals  |
|     4 | Dataset generation pipeline               |
|     5 | FP32 reconstruction model                 |
|     6 | INT8 quantization and integer reference   |
|     7 | RTL ray generator and sphere intersection |
|     8 | RTL triangle intersection                 |
|     9 | AXI/DMA and ARM integration               |
|    10 | Streaming INT8 convolution                |
|    11 | Full reconstruction network               |
|    12 | Tiled DDR processing                      |
|    13 | End-to-end FPGA pipeline                  |
|    14 | Custom multiplier integration             |
|    15 | Benchmark and hardware analysis           |
|    16 | Documentation and final demonstration     |

The project should maintain a working baseline after each phase rather than adding advanced features before the previous stage is validated.

---

# Performance Evaluation

The final system will be evaluated at three levels.

## Image Quality

* PSNR
* SSIM
* LPIPS
* Edge error
* Temporal error for future temporal reconstruction

## FPGA Hardware

* LUT utilization
* Flip-flop utilization
* BRAM utilization
* DSP utilization
* Maximum frequency
* Worst setup slack
* Power
* Energy per frame

## Performance

* Rays/second
* Intersections/second
* CNN pixels/second
* Cycles/pixel
* DMA bandwidth
* Memory stall cycles
* End-to-end latency
* Frames/second

---

# Multiplier Optimization

A major research direction is evaluating a lower-cost multiplier inside the neural-network MAC array.

Candidate approaches include:

* Exact INT8 multiplication
* Exact INT4 multiplication
* Zero-detection bypass
* Leading-zero-based computation reduction
* Configurable 4×4 / 8×8 operation
* Error-bounded approximate multiplication

The multiplier will be evaluated at three levels:

```text
Multiplier
    │
    ├── Unit Level
    │     ├── Area
    │     ├── Delay
    │     ├── Power
    │     └── Functional Error
    │
    ├── CNN Level
    │     ├── Layer Error
    │     ├── PSNR
    │     └── SSIM
    │
    └── System Level
          ├── FPS
          ├── Energy/Frame
          ├── Bandwidth
          └── Final Image Quality
```

This allows the optimization to be evaluated as part of the complete accelerator rather than only as an isolated arithmetic block.

---

# Results

Results will be added as the implementation progresses.

| Configuration        | Resolution | Frequency | LUTs | FFs | BRAM | DSP | Latency | PSNR | SSIM |
| -------------------- | ---------: | --------: | ---: | --: | ---: | --: | ------: | ---: | ---: |
| Software baseline    |        TBD |         — |    — |   — |    — |   — |     TBD |  TBD |  TBD |
| FPGA ray tracer      |        TBD |       TBD |  TBD | TBD |  TBD | TBD |     TBD |    — |    — |
| FPGA INT8 baseline   |        TBD |       TBD |  TBD | TBD |  TBD | TBD |     TBD |  TBD |  TBD |
| Optimized multiplier |        TBD |       TBD |  TBD | TBD |  TBD | TBD |     TBD |  TBD |  TBD |

> Performance numbers will only be added after they are generated and reproducibly verified.

---

# Current Status

### Completed

* [ ] Project specification
* [ ] Repository structure
* [ ] C++ golden renderer
* [ ] Sphere intersection
* [ ] Triangle intersection
* [ ] RGB/depth/normal generation
* [ ] Dataset pipeline
* [ ] FP32 reconstruction model
* [ ] INT8 quantization
* [ ] Integer reference model
* [ ] FPGA ray-tracing RTL
* [ ] AXI integration
* [ ] DMA integration
* [ ] FPGA convolution engine
* [ ] 4K tiled reconstruction
* [ ] Custom multiplier
* [ ] End-to-end demonstration
* [ ] Hardware benchmark

This checklist will be updated as each milestone is completed.

---

# Definition of Done

The project is considered complete when:

* The complete pipeline can be launched reproducibly.
* FPGA generates the low-resolution rendering buffers.
* FPGA reconstruction processes the required tiles.
* A complete high-resolution output image is produced.
* RTL matches the integer reference within the documented tolerance.
* Synthesis, timing, power and image-quality results are available.
* The optimized multiplier is compared against a standard baseline.
* Verification tests are automated where practical.
* Performance claims have supporting logs or reports.
* Build and test instructions are documented.

---

# Hardware and Software Requirements

### Hardware

* Digilent ZedBoard
* Xilinx Zynq-7020
* Host PC
* DDR memory available through the Zynq processing system

### Software

* Xilinx Vivado
* Vitis / bare-metal SDK
* C++ compiler
* Python
* PyTorch
* ONNX
* pytest
* cocotb
* Git
* Optional open-source RTL simulator

---

# Reproducibility

The project follows a reproducibility-first approach.

Source code, scripts, configuration files, test vectors, synthesis reports, benchmark results, and documentation should be committed where appropriate.

Large generated files and Vivado build directories should not be committed unnecessarily.

---

# Future Work

Potential future extensions include:

* BVH acceleration
* Parallel ray-intersection lanes
* Shadow rays
* One-bounce reflections
* Temporal reconstruction
* Motion vectors
* INT4 inference
* Zero-skipping
* Double-buffered DMA
* Clock/power optimization
* Additional multiplier architectures

These features will be added only after the baseline pipeline is stable.

---

# Disclaimer on Performance Claims

This repository distinguishes between:

1. **Planned architecture**
2. **Implemented functionality**
3. **Measured results**

Terms such as **real-time**, **4K accelerator**, percentage improvements, FPS, latency, power reduction, and hardware savings will only be used when supported by reproducible measurements.

---

# License

Add the project's license here once selected.

---

# Author

**Sreevenkat Eluva**
B.Tech — Electronics and Communication Engineering (VLSI)
IIIT Manipur

---

## Project Focus

**FPGA | RTL Design | Computer Architecture | Ray Tracing | AI Acceleration | Verilog/SystemVerilog | AXI | DMA | Fixed-Point Arithmetic | CNN Quantization | Hardware/Software Co-Design | Verification**

