# Paper prep: first novelty search and venue shortlist (2026-10-16)

First pass with a web search only (no IEEE Xplore / Scholar login, abstracts and snippets only). **Every paper below must be read in full before
it is cited or compared with; every deadline must be checked on the official page before planning around it.**

## 1. Closest related work found

| Work | What it does | Why it matters for us |
|---|---|---|
| PKU, "FPGA-based Real-Time Super-Resolution System for Ultra High Definition Videos" ([pdf](https://ceca.pku.edu.cn/docs/20181030012447954751.pdf)) | FSRCNN-s, **each layer is a pipeline stage**, multipliers per stage balanced for throughput | The layer pipeline itself is **not new**. Our redesign must be framed as "on a low-cost Zynq-7020, measured, bit-exact", not as a new dataflow idea. Read it for buffer sizing and per-stage balancing. |
| Chang et al. / "A Real-Time CNN for Super-Resolution on FPGA with Applications to 4K UHD 60 fps" ([ResearchGate](https://www.researchgate.net/publication/326906972_A_Real-Time_Convolutional_Neural_Network_for_Super-Resolution_on_FPGA_with_Applications_to_4K_UHD_60_fps_Video_Services)) | real-time 4K SR, lightweight network, large FPGA | Speed reference on a big device; comparison-table row. |
| "A High-Performance Accelerator for Real-Time Super-Resolution on Edge FPGAs", ACM 2024 ([DOI](https://dl.acm.org/doi/10.1145/3652855)) | real-time SR on **edge** FPGAs | Probably the closest competitor: read first. |
| "Real-Time Super-Resolution System of 4K-Video Based on Deep Learning" ([arXiv 2107.05307](https://arxiv.org/pdf/2107.05307)) | 4K SR system | Comparison-table row. |
| "An Energy-Efficient FPGA-based Deconvolutional NN Accelerator for SISR" ([arXiv 1801.05997](https://arxiv.org/pdf/1801.05997)) | energy-focused SR accelerator | Energy comparison (GOPS/W). |
| ACNPU, 1080p@30 fps SR accelerator, 4.75 TOPS/W ([arXiv 2308.15807](https://arxiv.org/pdf/2308.15807)) | SR accelerator, platform not confirmed (likely ASIC) | Check platform; if ASIC, cite but do not put in the FPGA table. |
| ScaleLUT ([arXiv 2609.16508](https://arxiv.org/pdf/2609.16508)) | LUT-based SR, 5 line buffers | Line-buffer reference; different method (LUT, not CNN). |
| Already cited in the M7 report: NIT Calicut QFSRCNN (VDAT 2024, ZCU104, 24.12 fps, 1,114 DSP), URSI 2024 Zynq SRCNN | | Keep. |

**Verification angle:**
* CGRA4ML ([arXiv 2408.15561](https://arxiv.org/pdf/2408.15561)) already targets 100 % bit parity with a golden model at layer and model level, including over AXI DMA. So
  "bit-exact golden-model verification" alone is **not new** either.
* Mutation testing of HDL exists in general ([IP Paris](https://researchportal.ip-paris.fr/en/publications/mutation-testing-for-effective-verification-of-digital-components/)),
  and model mutation across accelerators exists ([ICST 2025 Mutation](https://conf.researchr.org/details/icst-2025/mutation-2025-papers/2/Exploring-Robustness-of-Image-Recognition-Models-on-Hardware-Accelerators)).
  This search did **not** find a CNN-accelerator paper that reports an RTL mutation score next to bit-exact board results. That combination
  (mutation-tested RTL + seam test + 119/119 byte-exact on the board) is the most likely real novelty of the verification part. Not proven by one search.
* Our own public GitHub repo shows up in searches. With double-blind review, use an anonymized link.

**What this means for the claims:** do not claim the layer pipeline or bit-exactness as new ideas. Plausible contributions: (1) a measured
utilization-gap analysis and its closure on a ~$100-class FPGA, (2) a verification flow with quantified test strength (mutation catch rate) and
board-level byte-exactness on standard benchmarks, (3) measured energy vs the embedded ARM on the same chip (T7) and vs a desktop GPU.

## 2. Venue shortlist (dates from the web, 2026-10-16; check before relying on them)

| Venue | Deadline | Fit | Realistic for us? |
|---|---|---|---|
| **ARC 2027** (Applied Reconfigurable Computing, Berlin, 31 Mar-2 Apr 2027, Springer LNCS; selected papers to ACM TRETS) ([site](https://amor.cms.hu-berlin.de/~hubnermi/index.html), [EasyChair](https://easychair.org/cfp/arc2027)) | **25 Oct 2026** (preliminary call; past editions extended) | very good (FPGA applications) | Only option A (current design + gap analysis + cycle model) in 9 days; tight. |
| **ISCAS 2027** (Bordeaux, 6-9 Jun 2027) ([CFP](https://2027.ieee-iscas.org/call-for-papers)) | **22 Oct 2026** (extended from 13 Oct) | OK (circuits & systems, broad) | 6 days: only option A, very tight. |
| **FPL 2027** | not announced; FPL 2026 was 20/27 Mar 2026 ([FPL 2026 CFP](https://2026.fpl.org/calls/call-for-papers/)) -> expect ~Mar 2027 | best FPGA venue on the list | Fits the **redesign** (about 5 months). |
| **GLSVLSI 2027** | not announced; 2026 was ~Mar 2026 ([site](https://www.glsvlsi.org/)) | OK (VLSI / systems) | Fits the redesign. |
| **VDAT 2027** (India) | not announced; VDAT 2026 was 30 Apr 2026 ([listing](https://ci2s-enterprise.com.ar/2026/04/09/30th-international-symposium-on-vlsi-design-and-test-vdat-2026-20th-22nd-august-2026-at-jiit-sector-62-noida-u-p-india/)) | good (student-friendly; the NIT Calicut SR paper was VDAT 2024) | Fits the redesign. |
| VLSID 2028 | 2027 deadline was ~Aug 2026 ([CFP](https://vlsid.org/call-for-papers/)) | good | Later option. |
| Closed for this cycle | ACM FPGA 2027 (1/8 Oct 2026), VLSID 2027, iSES 2026 (general track; special sessions 20 Oct 2026), FPL 2026, VDAT 2026, ISVLSI 2026 | | |

Page limits and review type (single/double blind) were not checked yet: read each call.
