# FPGA-Based Sparse Ray Tracing and AI 4K Reconstruction Accelerator
# Complete Software-Side Study and Implementation Guide

> **Purpose:** This document explains the complete software side of the project from the first scene description to the final 4K reconstructed image and FPGA/ARM software control.
>
> The software side is treated as the reference and control system for the hardware. The C++ renderer defines the rendering reference, Python/PyTorch develops the reconstruction model, the Python integer model defines exact quantized arithmetic for RTL, and ARM-side C/C++ controls the FPGA accelerators.

---

# 1. Big Picture

The complete software pipeline is:

```text
Scene Description
      |
      v
C++ Ray Tracer
      |
      +---- RGB
      +---- Depth
      +---- Normal
      |
      v
Dataset Generator
      |
      +-------------------+
      |                   |
      v                   v
Low-Resolution Input   High-Resolution Ground Truth
      |                   |
      +---------+---------+
                |
                v
        Bicubic Baseline
                |
                v
          FP32 CNN Training
                |
                v
          FP32 Reconstruction Model
                |
                v
          INT8 QAT
                |
                v
      INT8 Weights + Scales + Parameters
                |
                v
      Bit-Accurate Integer Python Model
                |
                v
       FPGA RTL Golden Reference
                |
                v
       ARM C/C++ Driver + DMA
                |
                v
        FPGA Ray Tracer + CNN
                |
                v
             DDR
                |
                v
          Final 4K Image
                |
                v
      Quality + Performance Analysis
```

## Main software languages

| Area | Language / Tool | Main purpose |
|---|---|---|
| Reference renderer | C++ | Golden ray-tracing implementation |
| Dataset generation | Python + C++ | Generate reproducible training data |
| Visualization | Python | Inspect RGB/depth/normal images |
| AI training | Python + PyTorch | Train FP32 reconstruction model |
| Quantization | Python + PyTorch | INT8 QAT |
| Integer reference | Python + NumPy | Bit-accurate hardware reference |
| ARM control | C/C++ | Configure and control FPGA |
| Benchmarking | C/C++ + Python | Measure latency, bandwidth, FPS, quality |

---

# 2. What the Software Side Is Responsible For

There are four major software responsibilities.

## 2.1 Rendering reference

The C++ renderer answers:

> For this exact scene and camera, what should every pixel contain?

It produces:

- RGB
- depth
- surface normals

This is the **golden rendering reference**.

---

## 2.2 AI reconstruction

The Python/PyTorch software answers:

> Given a low-resolution RGB/depth/normal representation, how can we reconstruct a higher-resolution RGB image?

It produces:

- trained FP32 model
- INT8 QAT model
- exported weights/scales/quantization parameters

---

## 2.3 Exact integer reference

The integer Python model answers:

> What exact integer operations must the FPGA CNN perform?

It reproduces:

```text
INT8 activation
      x
INT8 weight
      |
      v
INT32 accumulation
      |
      v
bias
      |
      v
requantization
      |
      v
rounding
      |
      v
clamp/saturation
      |
      v
INT8 output
```

This becomes the software golden model for the later RTL implementation.

---

## 2.4 FPGA control

ARM-side C/C++ answers:

> How do I configure the accelerator, start it, move image data, wait for completion, detect errors, and retrieve the output?

---

# 3. Software Development Philosophy

The most important rule is:

> **Never move to the next software stage until the current stage is correct, reproducible, and testable.**

The project should maintain a working baseline at every stage.

For example:

```text
Correct C++ renderer
        |
        v
Correct dataset
        |
        v
Correct bicubic baseline
        |
        v
Working FP32 CNN
        |
        v
Working INT8 model
        |
        v
Bit-accurate integer model
        |
        v
Working ARM driver
```

If an FPGA result is wrong later, we should be able to trace the problem backward through these references.

---

# 4. Software Step 1 — Define the Scene

## 4.1 What are we building?

We first need a software representation of a 3D scene.

A minimal scene contains:

```text
Camera
Objects
Materials
Lights
```

For version 1, the initial renderer can start with simple geometry such as spheres and a simple light.

Example:

```text
Sphere:
    center = (0, 0, -5)
    radius = 1
    color  = (255, 0, 0)

Camera:
    position = (0, 0, 0)
    direction = (0, 0, -1)
    FOV = 60 degrees

Light:
    position = (2, 4, 1)
    intensity = 1.0
```

---

## 4.2 Why do we need this?

A ray tracer cannot render without knowing:

- where the camera is
- where objects are
- what the objects look like
- where the light is

The scene is therefore the input to the renderer.

---

## 4.3 C++ representation

Conceptually:

```cpp
struct Vec3 {
    float x;
    float y;
    float z;
};

struct Sphere {
    Vec3 center;
    float radius;
    Vec3 color;
};

struct Camera {
    Vec3 position;
    Vec3 direction;
    float fov;
};

struct Light {
    Vec3 position;
    float intensity;
};
```

---

## 4.4 Input

```text
Scene parameters
```

## Output

```text
Scene object in memory
```

## Verification

Create one deterministic scene whose parameters never change.

---

# 5. Software Step 2 — Understand the Camera

Before generating rays, understand what the camera does.

An image is a 2D grid:

```text
          x
     0  1  2  3  ... W-1
   +---------------------
 y 0| .  .  .  .
   1| .  .  .  .
   2| .  .  .  .
   .|
   .|
H-1| .
```

For every pixel `(x,y)`, we need to determine which direction the camera is looking through that pixel.

---

## 5.1 Why?

Ray tracing works by asking:

> What object does the ray passing through this pixel hit?

Therefore:

```text
pixel (x,y)
     |
     v
camera model
     |
     v
ray origin + ray direction
```

---

# 6. Software Step 3 — Generate Camera Rays

For every pixel:

```text
(x,y)
  |
  v
Convert pixel coordinate to camera-space coordinate
  |
  v
Calculate ray direction
  |
  v
Normalize direction
```

Conceptually:

```text
Camera
   O
    \
     \
      \       Scene
       \        *
        \      /
         \    /
          \  /
           \/
```

A ray can be represented as:

```cpp
struct Ray {
    Vec3 origin;
    Vec3 direction;
};
```

The ray equation is:

```text
P(t) = O + tD
```

where:

- `O` = ray origin
- `D` = ray direction
- `t` = distance along the ray
- `P(t)` = point on the ray

---

## 6.1 Input

```text
pixel x
pixel y
camera parameters
image width
image height
```

## 6.2 Output

```text
Ray(origin, direction)
```

## 6.3 Verification

Test a few known pixels:

- image center
- corners
- left/right edges
- top/bottom edges

The center ray should point approximately along the camera viewing direction.

---

# 7. Software Step 4 — Sphere Intersection

Now we have:

```text
Ray + Sphere
```

and need to determine whether the ray hits the sphere.

Ray:

```text
P(t) = O + tD
```

Sphere:

```text
|P-C|² = r²
```

Substitute the ray equation:

```text
|O + tD - C|² = r²
```

This produces:

```text
at² + bt + c = 0
```

with discriminant:

```text
Δ = b² - 4ac
```

---

## 7.1 Cases

### Case 1 — No intersection

```text
Δ < 0
```

Ray misses the sphere.

### Case 2 — One intersection

```text
Δ = 0
```

Ray touches the sphere.

### Case 3 — Two intersections

```text
Δ > 0
```

Ray enters and exits the sphere.

We normally select the closest positive intersection.

---

## 7.2 Why?

This is the fundamental ray-tracing operation.

Without intersection:

```text
Ray
 |
 X
```

With intersection:

```text
Ray
 |
 v
Sphere
```

---

## 7.3 Verification

Test:

1. Ray directly through sphere center.
2. Ray missing sphere.
3. Tangent ray.
4. Ray starting inside sphere.
5. Sphere at different distances.

These tests should be deterministic.

---

# 8. Software Step 5 — Nearest-Hit Selection

A ray may intersect multiple objects.

Example:

```text
Camera
  |
  |---- Object A, t=3
  |
  |------------ Object B, t=8
```

The visible object is A.

Therefore:

```text
nearest_hit = minimum positive t
```

For many objects:

```cpp
for each object:
    test intersection
    if hit and t < nearest_t:
        nearest_t = t
        nearest_object = object
```

---

## Why?

Only the closest visible surface contributes to the pixel.

---

# 9. Software Step 6 — Calculate Hit Point

After finding:

```text
t = nearest intersection
```

calculate:

```text
P = O + tD
```

Example:

```text
O = (0,0,0)
D = (0,0,-1)
t = 4

P = (0,0,-4)
```

This point is required for:

- normal calculation
- depth
- lighting

---

# 10. Software Step 7 — Calculate Surface Normal

For a sphere:

```text
N = normalize(P - C)
```

where:

- `P` = hit point
- `C` = sphere center

The normal describes the direction in which the surface faces.

```text
          N
          ↑
          |
       ---*---
      /       \
     | Sphere  |
      \       /
       -------
```

---

## Why?

The normal is needed for lighting and is also useful as auxiliary information for the neural reconstruction network.

---

# 11. Software Step 8 — Calculate Depth

The intersection parameter `t` gives us distance along the ray.

We can store a depth value representing how far the visible surface is from the camera.

Example:

```text
Pixel A → depth = 2
Pixel B → depth = 5
Pixel C → depth = 10
```

A depth image might conceptually look like:

```text
near → dark/small value
far  → larger value
```

The exact visualization convention can be chosen later.

---

## Why depth matters to the CNN

Depth tells the network about scene geometry.

For example:

```text
RGB alone:
"What is this edge?"

RGB + depth:
"An object boundary occurs because depth changes here."
```

---

# 12. Software Step 9 — Calculate Lighting and RGB

The initial renderer uses simple Lambertian lighting.

Define:

```text
N = surface normal
L = direction from hit point to light
```

Diffuse contribution:

```text
diffuse = max(dot(N,L), 0)
```

Then combine it with object color and an ambient contribution as defined by the renderer.

Conceptually:

```text
Surface
   *
  /|
 / |
N  | L
   |
 Light
```

If the normal points toward the light:

```text
dot(N,L) → large
```

and the surface is brighter.

If the normal points away:

```text
dot(N,L) → 0
```

and diffuse illumination is low/zero.

---

# 13. Software Step 10 — Produce the G-Buffer-Like Output

For every pixel, we now have:

```text
RGB
Depth
Normal
```

Example:

```text
Pixel (100,50)

RGB    = [120, 80, 40]
Depth  = 3.72
Normal = [0.2, 0.8, 0.5]
```

For an entire image:

```text
RGB:
W × H × 3

Depth:
W × H × 1

Normal:
W × H × 3
```

---

## Why store all three?

The RGB image is the visible appearance.

Depth and normal provide geometric information.

Therefore the CNN gets:

```text
appearance + geometry
```

instead of only:

```text
appearance
```

---

# 14. Software Step 11 — Save the Renderer Output

The renderer should save:

```text
low_rgb
low_depth
low_normal
```

and the high-quality/high-resolution RGB target.

Recommended conceptual organization:

```text
scene_0001/
    low_rgb.png
    low_depth.npy
    low_normal.npy
    high_rgb.png
    scene.json
```

Use formats appropriate to the data:

- RGB → image format
- depth → numerical array
- normals → numerical array
- scene parameters → JSON

---

# 15. Software Step 12 — Python Visualization

Now Python loads the C++ output.

Example:

```text
C++ renderer
     |
     +--> RGB
     +--> depth
     +--> normal
             |
             v
       Python visualization
```

We should visualize:

```text
RGB image
Depth image
Normal X
Normal Y
Normal Z
```

---

## Why?

This catches bugs before AI training.

For example:

### Wrong camera

```text
Everything shifted
```

### Wrong normal

```text
Lighting appears inverted
```

### Wrong depth

```text
Depth changes unexpectedly
```

### Wrong RGB

```text
Sphere has incorrect shading
```

---

# 16. Software Step 13 — High-Resolution Ground Truth

We now need a target image for learning.

Example:

```text
Input:
960 × 540

Target:
3840 × 2160
```

The target should be generated using a higher-quality/high-resolution reference render.

The training pair becomes:

```text
INPUT
RGB + Depth + Normal
960 × 540

        +

TARGET
High-resolution RGB
3840 × 2160
```

---

# 17. Software Step 14 — Dataset Generation

One scene is not enough.

Generate many scene variants by changing:

```text
sphere position
sphere radius
sphere color
camera position
camera angle
light position
light intensity
geometry
```

Each scene gets a unique ID.

Example:

```text
scene_0001
scene_0002
...
scene_0500
```

The dataset generator should record the random parameters.

---

## Why?

The CNN must learn a general mapping:

```text
low-resolution representation
          ↓
high-resolution image
```

rather than memorizing one scene.

---

# 18. Software Step 15 — Dataset Manifest

Create a manifest such as:

```json
{
    "scene_id": 17,
    "camera": {...},
    "objects": [...],
    "lights": [...],
    "low_rgb": "...",
    "low_depth": "...",
    "low_normal": "...",
    "high_rgb": "..."
}
```

---

## Why?

The manifest gives us:

- reproducibility
- file locations
- scene parameters
- dataset bookkeeping
- deterministic regeneration

The project requires a versioned/reproducible dataset manifest.

---

# 19. Software Step 16 — Train/Validation/Test Split

Do not randomly split individual images from the same scene.

Prefer:

```text
TRAIN:
scene 1...800

VALIDATION:
scene 801...900

TEST:
scene 901...1000
```

The exact counts can change.

The important rule is:

> Split by scene.

---

## Why?

If the same scene appears in both training and testing, the network may see very similar geometry during training.

That can produce misleadingly strong metrics.

---

# 20. Software Step 17 — Bicubic Baseline

Before AI, resize the low-resolution RGB using bicubic interpolation.

```text
Low-resolution RGB
        |
        v
     Bicubic
        |
        v
High-resolution RGB
```

Then compare it against the ground truth.

---

## Why?

This answers:

> Is the CNN actually improving the reconstruction?

Bicubic is the baseline/floor.

We should record:

```text
Bicubic PSNR
Bicubic SSIM
```

before training the CNN.

---

# 21. Software Step 18 — PSNR

PSNR measures reconstruction error.

Conceptually:

```text
Ground Truth
     |
     | compare
     v
Prediction
```

Higher PSNR generally means lower pixel error.

Record:

```text
PSNR(dB)
```

for:

- bicubic
- FP32 CNN
- INT8 model
- FPGA model

---

# 22. Software Step 19 — SSIM

SSIM evaluates structural similarity.

It helps evaluate whether structures such as:

- edges
- shapes
- local contrast

remain similar.

Record:

```text
SSIM
```

alongside PSNR.

---

# 23. Software Step 20 — Build the FP32 CNN

The recommended lightweight model is inspired by ESPCN/FSRCNN.

Conceptually:

```text
RGB + Depth + Normal
          |
          v
       3×3 Conv
          |
         ReLU
          |
   Depthwise Conv
          |
         ReLU
          |
   Pointwise 1×1 Conv
          |
         ReLU
          |
      Final Conv
          |
          v
    Pixel Shuffle ×4
          |
          v
      4K RGB
```

The goal is to keep the model small enough for FPGA implementation.

---

# 24. Software Step 21 — Understand Convolution

A convolution applies a learned kernel to local input values.

Example:

```text
Input:

1 2 3
4 5 6
7 8 9

Kernel:

1 0 -1
1 0 -1
1 0 -1
```

The operation performs multiply-and-add operations.

This is important because FPGA CNN hardware will eventually implement many:

```text
multiply + accumulate
```

operations.

---

# 25. Software Step 22 — ReLU

ReLU:

```text
ReLU(x) = max(0,x)
```

Example:

```text
-5 → 0
-2 → 0
 0 → 0
 3 → 3
 8 → 8
```

This introduces nonlinearity into the network.

---

# 26. Software Step 23 — Depthwise Convolution

Depthwise convolution processes channels independently.

Conceptually:

```text
Channel 0 → 3×3 filter
Channel 1 → 3×3 filter
Channel 2 → 3×3 filter
...
```

It reduces computation compared with a full convolution.

This is valuable for a resource-constrained FPGA.

---

# 27. Software Step 24 — Pointwise Convolution

Pointwise convolution uses:

```text
1 × 1
```

kernels.

Its main role is to mix information between channels.

Conceptually:

```text
Many input channels
        |
       1×1
        |
        v
New feature channels
```

---

# 28. Software Step 25 — Pixel Shuffle

For 4× upscaling:

```text
RGB channels = 3

3 × 4 × 4 = 48
```

So the final convolution can generate:

```text
48 channels
```

at low resolution.

Pixel shuffle rearranges those channels into spatial positions:

```text
Low-resolution feature channels
              |
              v
       Pixel Shuffle ×4
              |
              v
      High-resolution RGB
```

The rearrangement itself is mostly address/control logic rather than multiplication.

---

# 29. Software Step 26 — FP32 Training

Training loop:

```text
Load input
   |
   v
CNN forward pass
   |
   v
Prediction
   |
   v
Compare with target
   |
   v
Loss
   |
   v
Backpropagation
   |
   v
Weight update
   |
   v
Repeat
```

Start with a simple L1 loss if needed.

The project proposes:

```text
Total Loss =
L1
+ 0.2 × (1 - SSIM)
+ 0.05 × Edge Loss
```

as the fuller training objective.

---

# 30. Software Step 27 — Evaluate FP32 Model

After training:

```text
Test scenes
     |
     v
FP32 CNN
     |
     v
Predicted high-resolution RGB
```

Measure:

```text
PSNR
SSIM
```

and optionally:

```text
LPIPS
```

Also inspect images visually.

Look for:

- blur
- color shifts
- checkerboard artifacts
- broken edges
- incorrect thin structures

---

# 31. FP32 Exit Criteria

Do not proceed to INT8 until:

```text
[ ] Bicubic PSNR/SSIM recorded
[ ] FP32 model trains successfully
[ ] FP32 beats bicubic on held-out scenes
[ ] No obvious reconstruction artifacts
[ ] Model checkpoint saved
[ ] Evaluation script is reproducible
```

This is important because otherwise INT8 debugging becomes confusing.

If FP32 itself is bad:

```text
Bad FP32
   ↓
INT8
   ↓
still bad
```

We won't know whether the problem is the network or quantization.

---

# 32. Software Step 28 — INT8 Quantization

FP32 uses values such as:

```text
0.1378
-0.2937
0.0083
```

INT8 uses approximately:

```text
-128 ... +127
```

Quantization maps real values to integer representations.

Conceptually:

```text
FP32 value
    |
    v
scale / zero-point
    |
    v
INT8 value
```

---

# 33. Software Step 29 — Quantization-Aware Training

QAT simulates quantization during training.

Conceptually:

```text
FP32 model
    |
    v
Fake Quantization
    |
    v
INT8-like behavior
    |
    v
Loss
    |
    v
Backpropagation
```

The model is fine-tuned so it becomes robust to quantization.

---

# 34. Software Step 30 — Export Quantization Parameters

After QAT, export:

```text
INT8 weights
bias
scale
zero point
requantization parameters
```

These parameters will eventually be consumed by the integer reference and RTL.

---

# 35. Software Step 31 — Compare FP32 and INT8

Run both:

```text
FP32 model
INT8 model
```

on the same test set.

Measure:

```text
FP32 PSNR
INT8 PSNR

FP32 SSIM
INT8 SSIM
```

The important result is the **actual measured degradation**.

Do not assume INT8 will be perfect.

---

# 36. Software Step 32 — Integer Python Reference

Create:

```text
ai/integer_reference.py
```

This model should use integer operations rather than relying on floating-point inference.

The intended arithmetic is:

```text
INT8 activation
       ×
INT8 weight
       |
       v
INT32 accumulation
       |
       v
bias
       |
       v
requantization
       |
       v
rounding
       |
       v
saturation
       |
       v
INT8 output
```

---

# 37. Why the Integer Reference Is Critical

The later RTL must match this model.

Therefore:

```text
Integer Python
      |
      | expected output
      v
RTL
      |
      | actual output
      v
Compare
```

If they differ:

```text
Python ≠ RTL
```

we debug the arithmetic before integrating the entire CNN.

---

# 38. Integer Arithmetic Details

The integer reference must define exactly:

## Multiplication

```text
INT8 × INT8 → wider result
```

## Accumulation

```text
multiple products → INT32 accumulator
```

## Bias

```text
accumulator + bias
```

## Requantization

Convert the larger accumulator back into the activation range.

## Rounding

Define exactly how fractions are rounded.

## Saturation

Clamp the final result:

```text
< -128 → -128
> 127   → 127
```

Then:

```text
output = INT8
```

---

# 39. Integer Reference Tests

Test extreme values:

```text
-128 × -128
-128 × 127
127 × 127
0 × anything
maximum accumulation
minimum accumulation
```

Also test:

```text
rounding boundaries
saturation boundaries
zero points
bias extremes
```

The goal is deterministic, bit-accurate behavior.

---

# 40. Software Step 33 — ARM Application

Now move to software running on the Zynq ARM processor.

Conceptually:

```text
+-----------------------------+
| ARM PS                      |
|                             |
| C/C++ application           |
|                             |
| scene configuration         |
| accelerator control         |
| DMA control                 |
| status/error handling       |
| benchmarking                |
+-------------+---------------+
              |
             AXI
              |
              v
+-----------------------------+
| FPGA PL                     |
|                             |
| Ray tracer                  |
| CNN                         |
+-----------------------------+
```

---

# 41. ARM Software Responsibilities

The ARM application should:

1. Configure the scene.
2. Allocate/identify buffers.
3. Configure accelerator registers.
4. Start the ray tracer.
5. Wait for completion.
6. Check errors/timeouts.
7. Start reconstruction.
8. Manage tiles.
9. Wait for CNN completion.
10. Retrieve/save final output.
11. Measure timing.

---

# 42. Software Step 34 — Configure Accelerator Registers

Example conceptual register map:

```text
0x00 CONTROL
0x04 STATUS
0x08 WIDTH
0x0C HEIGHT
0x10 SCENE_BASE
0x14 INPUT_BASE
0x18 OUTPUT_BASE
0x1C WEIGHT_BASE
0x20 TILE_CONFIG
0x24 CYCLE_COUNT
0x28 STALL_COUNT
0x2C ERROR_CODE
```

The exact final addresses must be kept in one shared register-map document.

Software should use named constants rather than scattered magic numbers.

---

# 43. Software Step 35 — Start the Accelerator

Conceptually:

```cpp
write_reg(CONTROL, START);
```

Then poll:

```cpp
while (!(read_reg(STATUS) & DONE)) {
    // wait
}
```

Later, interrupts can replace polling.

---

# 44. Software Step 36 — DMA

Large image buffers should be moved using DMA rather than inefficient CPU copying.

Conceptually:

```text
DDR
 |
 | AXI DMA
 |
 v
FPGA
```

DMA handles bulk transfers.

Software mainly manages:

```text
source address
destination address
transfer length
start
completion
error
```

---

# 45. Software Step 37 — DDR Buffers

The software must manage memory for:

```text
RGB buffer
Depth buffer
Normal buffer
CNN input
CNN output
Weights
Final framebuffer
```

Conceptually:

```text
DDR
+-------------------+
| RGB               |
+-------------------+
| Depth             |
+-------------------+
| Normal            |
+-------------------+
| CNN input         |
+-------------------+
| CNN output        |
+-------------------+
| Weights           |
+-------------------+
| Final image       |
+-------------------+
```

---

# 46. Software Step 38 — Tiled Reconstruction

A complete 4K frame is:

```text
3840 × 2160
= 8,294,400 pixels
```

Instead of processing everything at once:

```text
+----+----+----+----+
| T1 | T2 | T3 | T4 |
+----+----+----+----+
| T5 | T6 | T7 | T8 |
+----+----+----+----+
...
```

Software calculates the address of each tile.

---

# 47. What Is a Halo?

Convolution needs neighboring pixels.

Suppose a tile is:

```text
[ central tile ]
```

A 3×3 convolution needs one pixel of neighborhood around it.

Therefore we may load:

```text
+-------------------+
|       halo        |
|   +-----------+   |
|   |   tile    |   |
|   +-----------+   |
|       halo        |
+-------------------+
```

The halo provides neighboring information.

After processing, only the valid central region is retained.

This avoids visible seams between tiles.

---

# 48. Software Step 39 — Final Image Assembly

After every tile finishes:

```text
Tile 1 → output region 1
Tile 2 → output region 2
Tile 3 → output region 3
...
```

The software assembles them into:

```text
3840 × 2160 RGB
```

Then saves or transfers the final framebuffer.

---

# 49. Software Step 40 — End-to-End Application

The final software flow should eventually look like:

```text
load scene
    |
    v
configure FPGA ray tracer
    |
    v
start ray tracer
    |
    v
wait for completion
    |
    v
RGB/depth/normal in DDR
    |
    v
configure CNN
    |
    v
process tile 0
    |
    v
process tile 1
    |
   ...
    |
    v
assemble final framebuffer
    |
    v
save/transfer 4K image
    |
    v
benchmark
```

---

# 50. Software Step 41 — Benchmarking

Measure separately:

```text
Ray tracing time
DMA transfer time
CNN computation time
Tile processing time
Final image transfer time
End-to-end latency
```

Then derive:

```text
FPS
rays/sec
CNN pixels/sec
cycles/pixel
DMA bandwidth
memory stall cycles
energy/frame
```

---

# 51. Software Step 42 — Compare All Implementations

The project should eventually compare:

```text
Nearest-neighbour
Bicubic
FP32 software
INT8 software
FPGA INT8
FPGA optimized multiplier
```

For image quality:

```text
PSNR
SSIM
```

For hardware/system performance:

```text
latency
FPS
LUT
FF
DSP
BRAM
Fmax
power
bandwidth
energy/frame
```

---

# 52. Software Verification Pyramid

The software verification should look like:

```text
                  Full System
                      |
              ARM + FPGA + DDR
                      |
                FPGA CNN
                      |
            Integer Python Model
                      |
               INT8 QAT Model
                      |
                FP32 CNN
                      |
                Bicubic
                      |
              C++ Renderer
                      |
                 Unit Tests
```

Each level should be tested independently.

---

# 53. C++ Renderer Unit Tests

Test:

```text
Vec3 operations
ray generation
sphere intersection
nearest hit
normal calculation
depth
lighting
image output
```

---

# 54. Dataset Tests

Verify:

```text
manifest exists
all referenced files exist
scene IDs are unique
train/test scenes do not overlap
random seeds reproduce scenes
RGB dimensions are correct
depth dimensions are correct
normal dimensions are correct
```

---

# 55. AI Tests

Verify:

```text
dataset loads
tensor shapes are correct
CNN forward pass works
loss decreases
validation works
checkpoint saves
evaluation works
```

---

# 56. Quantization Tests

Verify:

```text
FP32 model works
QAT model works
weights exported
scales exported
zero points exported
INT8 output reasonable
PSNR/SSIM degradation measured
```

---

# 57. Integer Reference Tests

Verify:

```text
INT8 multiplication
INT32 accumulation
bias
rounding
requantization
saturation
boundary cases
deterministic output
```

---

# 58. ARM Software Tests

Verify:

```text
register writes
register reads
DMA transfer
timeout handling
error handling
buffer addresses
tile addresses
completion status
output framebuffer
```

---

# 59. Final Software Exit Criteria

The software side is considered mature when:

```text
[ ] C++ renderer produces reproducible images
[ ] RGB/depth/normal outputs are correct
[ ] Python visualization works
[ ] Dataset can be regenerated
[ ] Train/test split is scene-based
[ ] Bicubic PSNR/SSIM recorded
[ ] FP32 CNN trains
[ ] FP32 CNN evaluated on held-out scenes
[ ] INT8 QAT works
[ ] INT8 accuracy measured
[ ] Integer Python reference exists
[ ] Integer reference is deterministic
[ ] ARM driver can configure accelerator
[ ] DMA transfers work
[ ] Tile processing works
[ ] Final framebuffer is produced
[ ] End-to-end benchmark is reproducible
```

---

# 60. Recommended Software Repository

```text
software/
├── cpp-renderer/
│   ├── include/
│   │   ├── vec3.h
│   │   ├── ray.h
│   │   ├── camera.h
│   │   ├── sphere.h
│   │   ├── light.h
│   │   └── renderer.h
│   │
│   ├── src/
│   │   ├── vec3.cpp
│   │   ├── camera.cpp
│   │   ├── sphere.cpp
│   │   ├── renderer.cpp
│   │   └── main.cpp
│   │
│   └── tests/
│       ├── test_vec3.cpp
│       ├── test_ray.cpp
│       └── test_sphere.cpp
│
├── arm-driver/
│   ├── accelerator.cpp
│   ├── dma.cpp
│   ├── memory.cpp
│   └── main.cpp
│
└── benchmark/
    └── benchmark.cpp

ai/
├── dataset/
│   ├── generate.py
│   ├── dataset.py
│   └── manifest.json
│
├── models/
│   └── reconstruction.py
│
├── train.py
├── quantize.py
├── integer_reference.py
│
└── evaluation/
    ├── metrics.py
    ├── visualize.py
    └── compare.py
```

---

# 61. Important Data Flow

Keep this data flow in your mind:

```text
C++ Scene
    |
    v
Ray Tracing
    |
    +---------> RGB
    |
    +---------> Depth
    |
    +---------> Normal
                    |
                    v
              Dataset
                    |
          +---------+---------+
          |                   |
          v                   v
      Low-res              High-res
          |                   |
          +---------+---------+
                    |
                    v
                 CNN
                    |
                    v
             Reconstructed RGB
```

---

# 62. Most Important Four References

## Reference 1 — C++ Floating-Point Renderer

Answers:

> What is the correct rendering result?

```text
C++ renderer
    ↓
RGB/depth/normal
```

---

## Reference 2 — Bicubic

Answers:

> Does our learned reconstruction actually improve over a simple interpolation method?

```text
low-res RGB
    ↓
bicubic
    ↓
high-res RGB
```

---

## Reference 3 — PyTorch FP32/QAT

Answers:

> Can the neural network learn the reconstruction and survive INT8 quantization?

```text
FP32
 ↓
QAT
 ↓
INT8 model
```

---

## Reference 4 — Integer Python

Answers:

> What exact arithmetic should the FPGA perform?

```text
Integer Python
      ↓
expected hardware output
```

This fourth reference is the most important bridge from software AI to hardware RTL.

---

# 63. Complete Software Roadmap

```text
PHASE A — RENDERING
│
├── 1. Scene representation
├── 2. Camera
├── 3. Ray generation
├── 4. Sphere intersection
├── 5. Nearest hit
├── 6. Hit point
├── 7. Normal
├── 8. Depth
├── 9. Lighting
└── 10. RGB/depth/normal export
          |
          v
PHASE B — DATASET
│
├── 11. Python visualization
├── 12. High-resolution ground truth
├── 13. Scene randomization
├── 14. Dataset generation
├── 15. Manifest
└── 16. Train/test split
          |
          v
PHASE C — AI
│
├── 17. Bicubic baseline
├── 18. PSNR/SSIM
├── 19. FP32 CNN
├── 20. Convolution
├── 21. ReLU
├── 22. Depthwise convolution
├── 23. Pointwise convolution
├── 24. Pixel shuffle
├── 25. FP32 training
└── 26. FP32 evaluation
          |
          v
PHASE D — QUANTIZATION
│
├── 27. INT8 representation
├── 28. QAT
├── 29. Export weights
├── 30. Export scales/zero points
├── 31. FP32 vs INT8 comparison
└── 32. Integer Python reference
          |
          v
PHASE E — ARM SOFTWARE
│
├── 33. ARM application
├── 34. Register control
├── 35. DMA
├── 36. DDR buffers
├── 37. Tile management
├── 38. Halo handling
├── 39. Final image assembly
└── 40. End-to-end application
          |
          v
PHASE F — ANALYSIS
│
├── 41. Benchmark
├── 42. PSNR/SSIM comparison
├── 43. Latency
├── 44. Bandwidth
├── 45. FPS
└── 46. Final software/hardware comparison
```

---

# 64. Final Mental Model

Remember the project as six layers:

```text
                    FINAL IMAGE
                         ^
                         |
                 ARM APPLICATION
                         ^
                         |
                 FPGA ACCELERATOR
                         ^
                         |
              INTEGER PYTHON REFERENCE
                         ^
                         |
                   INT8 CNN
                         ^
                         |
                   FP32 CNN
                         ^
                         |
               DATASET + GROUND TRUTH
                         ^
                         |
                  C++ RAY TRACER
```

The direction of development is:

```text
C++ truth
   ↓
Dataset
   ↓
AI
   ↓
Quantization
   ↓
Integer truth
   ↓
Hardware
```

And the direction of final execution is:

```text
ARM software
   ↓
FPGA ray tracing
   ↓
RGB/depth/normal
   ↓
FPGA CNN
   ↓
4K framebuffer
```

---

# 65. The One Sentence You Should Remember

> **C++ tells us what the scene should look like, Python teaches the CNN how to reconstruct it, the integer Python model defines the exact arithmetic the FPGA must reproduce, and ARM C/C++ controls the complete accelerator system.**

---

# 66. Immediate Software Learning Order

Do not try to learn all of this at once.

We should now study it in this exact order:

```text
1. C++ renderer architecture
2. Vec3 mathematics
3. Camera and coordinate systems
4. Pixel-to-ray conversion
5. Ray-sphere intersection
6. Nearest-hit logic
7. Hit point + normal + depth
8. Lambertian shading
9. RGB/depth/normal image output
10. Python visualization
11. Dataset generation
12. Train/test split
13. Bicubic + PSNR + SSIM
14. CNN fundamentals
15. Our exact CNN architecture
16. FP32 training
17. QAT
18. INT8 representation
19. Integer CNN arithmetic
20. Bit-accurate Python reference
21. ARM C/C++ control
22. AXI register programming
23. DMA
24. DDR buffers
25. Tiling + halo
26. End-to-end software application
27. Benchmarking
```

**We should complete each item with code and a working output before moving to the next one.**
