# WhateverXe Enhanced

[![Enhanced E4](https://img.shields.io/badge/Enhanced-E4-blue)](https://github.com/rodrigosalesf/WhateverXe-Enhanced/releases/tag/v0.8.5-enhanced-e4)
[![Metal workloads](https://img.shields.io/badge/Metal-40%2C000%20verified%20operations-brightgreen)](#real-hardware-validation)
[![Tested OS](https://img.shields.io/badge/Tested%20OS-Sequoia%2015.8.3-lightgrey)](#real-hardware-validation)
[![Status](https://img.shields.io/badge/status-experimental-orange)](#known-limits-and-next-steps)

An experimental extension of [b00t0x/WhateverXe](https://github.com/b00t0x/WhateverXe), a Lilu plugin derived from WhateverGreen for selected Intel Xe-LP integrated GPUs. Enhanced focuses on defensive kernel code, framebuffer reliability, hardware diagnostics and reproducible graphics validation while retaining upstream architecture and credits.

**Current published milestone: E4**, based on WhateverXe 0.8.5. **Development: E5** (experimental, not yet released).

[Download Enhanced E4](https://github.com/rodrigosalesf/WhateverXe-Enhanced/releases/tag/v0.8.5-enhanced-e4) · [E4 source](https://github.com/rodrigosalesf/WhateverXe-Enhanced/tree/v0.8.5-enhanced-e4) · [Installation guide (PT-BR)](https://github.com/rodrigosalesf/WhateverXe-Enhanced/blob/publish-e4/INSTALL-E4-PT-BR.md) · [Report your hardware results](https://github.com/rodrigosalesf/WhateverXe-Enhanced/issues/new)

> **Important:** The homepage is on the `main` branch; Enhanced E4 source and binaries are maintained under their own branch/tag and Releases. Use the E4 release or pinned source rather than building `main` to obtain these enhancements. This is an experimental fork, not an official upstream release.

## Implemented improvements — E1 to E4

The E4 source tag is 35 commits ahead of the upstream baseline `d965747f8814cd1eed381e1b50b96a6a0e2d074a`, with 40 changed files (including 16 kernel-source files and 20 test files), 1,052 inserted lines and 60 removed lines at the time of comparison on November 25, 2026. These are source-diff statistics, not performance measurements.

| Generation | Implemented changes | Validation |
| --- | --- | --- |
| **E1 — Core Stability** | Sleepable delay accounting; bounded display-clock/PCODE polling; eDP panel power-state checks before AUX writes. | Automated regression checks |
| **E2 — Hardware Intelligence** | Aligned and bounded MMIO access; DSM reservation validation and stale-state revocation; EDRAM preflight/output invalidation; physical PCI identity, mobile GT topology and framebuffer-gate diagnostics; explicit invalid-fuse/ownership rejection reasons. | Automated regression checks; Enhanced runtime properties observed |
| **E3 — Display & Diagnostics** | Defensive DVMT refresh; DDI/port decoding and receiver lane validation; reject inaccessible AUX reads and clear stale state; validate AUX backlight capabilities; preserve PWM behavior; framebuffer wake-input and IRQ checks; initial Metal compute probe. | Automated regression checks; compute workload passed on target |
| **E4 — Graphics Stability & Validation** | Invalidate stale GT capacity/EDRAM results; validate native GGTT allocation-slot consistency; avoid redundant render-context cache writes; reject invalid reset-poll input and bound waits; add vertex/fragment shader compilation, offscreen render, pixel readback, repeatable workloads and latency reporting. | Automated regression checks; compute and render workloads passed on target |

[Review the exact E4 source diff](https://github.com/rodrigosalesf/WhateverXe-Enhanced/compare/d965747f8814cd1eed381e1b50b96a6a0e2d074a...v0.8.5-enhanced-e4) · [Regression-test contracts and limits](https://github.com/rodrigosalesf/WhateverXe-Enhanced/blob/v0.8.5-enhanced-e4/tests/README.md) · [Metal Probe source](https://github.com/rodrigosalesf/WhateverXe-Enhanced/blob/v0.8.5-enhanced-e4/tools/metal_probe.swift)

Automated checks model selected kernel/driver behavior. Passing them does not by itself establish physical MMIO behavior, complete display compatibility or successful recovery from a real GPU hang. Metal Probe is a separate user-space diagnostic, not a modification to Apple's shader compiler.

## Real hardware validation

**Maintainer test report — November 25, 2026**

| Test platform | Configuration |
| --- | --- |
| Laptop | Acer Aspire A515-57 |
| CPU | Intel Core i5-12450H (Alder Lake-H) |
| GPU | Intel UHD Graphics, Xe-LP, 48 EUs, PCI ID `0x46A3` |
| Operating system | macOS Sequoia 15.8.3 |
| Internal display | 1920 × 1080 |
| Graphics memory | 1536 MB reported by macOS (shared memory) |

### 40,000 verified Metal operations

| Workload | Successful submissions | Observed failures |
| --- | ---: | ---: |
| Metal compute with output verification | 20,000 | 0 |
| Metal render with pixel verification | 20,000 | 0 |
| **Total** | **40,000** | **0** |

Twenty runs of 1,000 iterations per workload completed successfully. The probe verified changing compute outputs and every pixel of a 16 × 16 offscreen render after GPU-to-CPU readback. No timeout was reported in those runs.

| Validation item | Result |
| --- | --- |
| macOS boot and internal display | ✅ Observed working |
| Metal device enumeration / Metal 2 | ✅ Reported |
| Compute shader compilation and execution | ✅ Passed |
| Vertex/fragment shaders, render pipeline and readback | ✅ Passed |
| WindowServer Metal clients and nonzero accumulated GPU time | ✅ Observed in IORegistry |
| GPU recovery counter | ✅ Zero in captured snapshots |
| GART and texture accounting | ✅ Activity observed |
| H.264 / HEVC hardware decoding | 🟡 VideoToolbox reports support; real decode test pending |
| HEVC encoding | 🟡 Driver advertises capabilities; real encode test pending |
| OpenCL | 🟡 Platform available; GPU workload pending |
| VP9 / AV1 hardware decoding | ❌ Not advertised on this setup |
| HDMI audio | 🔴 Open issue: picture without sound reported; reproduction and fix pending |
| OpenGL, brightness, HDMI display validation, sleep/wake | ⏳ Pending hardware tests |

Median GPU command-buffer times across the 20 runs were approximately **0.004 ms (compute)** and **0.034–0.039 ms (render, including blit)**. These are small correctness/latency micro-workloads, not FPS, peak GPU throughput or sustained gaming benchmarks.

Enhanced-specific properties in the captured IORegistry included `WEXEnhancedFramebufferGate = hooks-installed`, `WEXEnhancedGTReadoutStatus = readout-complete`, `WEXEnhancedMobileTopologyStatus = capacity-decoded` and `WEXEnhancedIdentity = physical-backend`. Backlight profile readiness and ForceWake IRQ protection were also reported. These observations demonstrate Enhanced code paths are active; the loaded executable UUID has not yet been matched to the exact E4 release binary.

### Reproduce the Metal test

Download the [E4 Metal Probe source](https://raw.githubusercontent.com/rodrigosalesf/WhateverXe-Enhanced/c24d6d8bc8e3b98977eab4e146c8d26463a0d338/tools/metal_probe.swift) or check out the E4 tag. With Xcode command-line tools installed, from the E4 source directory:

```sh
xcrun swiftc -swift-version 5 tools/metal_probe.swift -o metal_probe
./metal_probe --iterations 1000
```

Select the target GPU with `--registry-id` when multiple devices are present. A complete pass requires both `compute-output-verified` and `render-pixels-verified` for that device. See the [E4 documentation](https://github.com/rodrigosalesf/WhateverXe-Enhanced/blob/v0.8.5-enhanced-e4/README.md#enhanced-e3-metal-diagnostics) for timing definitions and limits.

## Known limits and next steps

- **E5 highest priority — HDMI audio:** HDMI video without sound has been reported. E4 has no dedicated verified HDMI-audio fix. The affected configuration and root cause still need to be established; the report is not evidence that every HDMI configuration is affected.
- GPU utilization and active-frequency counters remained zero in sampled diagnostics despite evidence of graphical activity. Root cause and behavior under synchronized sustained load are still unverified.
- A texture-byte counter intermittently returned a near-uint64-limit value; investigate counter integrity without assuming memory corruption.
- RC6, DC6, RPS, ForceWake behavior under load, physical reset/recovery, sleep/wake, display brightness and HDMI need targeted hardware tests.
- Battery/AC-adapter reporting on the Acer is currently invalid; its displayed percentage and runtime estimates cannot be used to assess power efficiency. This is a separate platform issue, not an established WhateverXe defect.
- No controlled upstream-versus-Enhanced A/B benchmark has been performed. No claim of improved FPS, battery life, universal compatibility or global stability is made.
- Upstream hardware and OS coverage below is inherited documentation, not new Enhanced qualification.

## Enhanced roadmap

**Long-term objective:** a complete, reliable Intel Xe-LP graphics solution for the supported Hackintosh configurations, within the GPU's physical capabilities and the macOS driver interfaces. Completeness is defined by verified rendering, compute, media, display, power, recovery, application compatibility and safe deployment, not by a GPU name, reported VRAM or Metal label. Begin with the Acer Alder Lake-H reference configuration and expand only with evidence.

| Milestone | Focus | Status |
| --- | --- | --- |
| E1 | Core stability | Implemented |
| E2 | Hardware intelligence | Implemented |
| E3 | Display and diagnostics | Implemented |
| E4 | Graphics stability and Metal validation | Published; initial hardware validation |
| E5 | Graphics stability, power and diagnostics | Experimental release gate |
| E6 | **Metal 3 & Advanced Graphics** | Planned; revised 10-module sequence |
| E7 | HDMI audio and recovery; multimedia and hardware video acceleration | Planned |
| E8 | Advanced macOS Graphics Integration | Planned |
| E9 | Hardware Optimization & Reliability | Planned |
| E10 | Full Xe-LP Graphics Qualification | Planned |

### Development sequence and release gates

Maintainer decision, 2026-11-28: close E5 against the integrated graphics baseline and release checks, then begin E6. Retain working HDMI video as a regression check. Move HDMI audio, reconnection and HDMI wake recovery to E7. Preserve draft PR #27 and historical identifiers for traceability.

For each module: review exact source/donor and licensing, implement a scoped change, run mandatory CPU and regression tests and DEBUG/RELEASE builds on GitHub Actions, review the PR, integrate into the milestone branch, and record evidence and remaining hardware checks. Compile-only, simulated, and physical results must be distinguished. Never bypass failed checks to meet a schedule. Maintain the published E4 baseline and a bootable rollback.

### E5 — experimental graphics baseline

| Module | Engineering task |
| --- | --- |
| E5.4 | GPU Telemetry Intelligence — counter integrity and reliable activity observations |
| E5.5 | Dynamic Frequency Management — actual/requested clocks, RP limits, RPS |
| E5.6 | ForceWake & RC6 Optimization — ownership, bounded access, residency and evidence-based power changes |
| E5.7 | Display Power Management — display wells, DC5/DC6, framebuffer restoration |
| E5.8 | Advanced Metal Validation — textures, mipmaps, coherence and ordered GPU work |
| E5.9 | Frame Pacing Diagnostics — presentation timing, VBlank and long-frame gaps |
| E5.10 | GPU Memory Intelligence — resource accounting and validated ownership |
| E5.11 | GPU Flight Recorder — bounded optional event history and safe export |
| E5.12 | Safe Installation & ABI Validation — read-only preflight, provenance and rollback |

### Deferred to E7 — HDMI audio compatibility

Investigate the HDMI video-without-audio report before changing kernel behavior. Establish the PCI/HDA controller and codec identity, the framebuffer connector and audio routing, EDID audio capabilities and ELD availability where exposed, and AppleHDA/AppleALC integration on the affected setup. Compare upstream and Enhanced with equivalent configuration. Changes should be limited to the component responsible for the failure; WhateverXe alone may not resolve an ACPI, codec, or audio-driver issue.

Acceptance criteria on the affected hardware: an HDMI audio output is detected and selectable in macOS, actual stereo playback reaches the HDMI display/receiver while video remains stable, reconnect and sleep/wake behavior are tested, and internal audio and existing Metal/display functionality do not regress. Record results and limitations separately. No HDMI-audio fix or hardware qualification is claimed yet.

### E5 expanded scope: diagnostics, performance and safe deployment

HDMI audio remains the first priority. The following planned work extends the E5 telemetry, power and validation modules; it does not imply that these features are already implemented.

| Workstream | Planned scope | Acceptance criteria |
| --- | --- | --- |
| E5.4–E5.6 — GPU telemetry and power | Validate actual/requested GPU clocks and supported hardware limits, counter integrity and memory accounting; investigate RPS, ForceWake and RC6 with low-overhead, read-only measurements first. | Distinguish invalid or unavailable samples from zero; correlate with controlled GPU workloads; no unsafe polling, forced clock floor or power-policy changes without target-specific evidence. |
| E5.8 — Advanced Metal validation | Extend the existing compute/render probe with supported buffer-backed textures, mipmaps, shared-memory coherence, texture synchronization and representative image workloads. | Verify outputs, resource lifetimes and timeouts on the target GPU; unsupported APIs are reported separately; retain E4 regression coverage. |
| E5.9 — Frame pacing diagnostics | Measure presentation intervals, long frame gaps and, where exposed, VBlank timing; investigate CPU/GPU synchronization bottlenecks. | Reproducible E4/E5 comparison under equivalent display and workload settings; distinguish presentation metrics from offscreen command-buffer times. |
| E5.10 — GPU memory intelligence | Investigate per-client memory and queue/context accounting using validated ownership and supported counters. | Detect inconsistent or stale samples; avoid claiming per-process VRAM totals where the driver does not expose reliable data; no private identifiers in shared reports. |
| E5.11 — GPU flight recorder | Explore an optional, bounded event history for MMIO failures, ForceWake, timeouts, framebuffer transitions and recovery. | No unbounded buffers, interrupt-context file I/O or continuous disk synchronization; export diagnostics through a separate tool where feasible; verify disabled-path overhead and failure handling. |
| E5.12 — Safe installation and ABI validation | Plan a read-only preflight, EFI backup/rollback guidance, executable identity and Mach-O symbol/OS compatibility checks, and a recovery boot procedure. | Explicit compatibility checks, preserved AMFIAnchor trust model and bootable fallback; no silent EFI or security-setting changes. |

The [MeowXE3 findings](https://github.com/cuadra8998/MeowXE3/blob/main/docs/FINDINGS.md), [development notes](https://github.com/cuadra8998/MeowXE3/blob/main/docs/CONTINUING.md) and [regression tests](https://github.com/cuadra8998/MeowXE3/tree/main/tools/tests) are complementary research references. They describe a different Xe3/Linux-driver architecture, not a drop-in dependency or a demonstrated HDMI-audio fix. Their reported performance results are not Enhanced benchmarks. Preserve the existing Xe-LP driver architecture, AMFIAnchor security model and BSD-3-Clause licensing; independently implement ideas and review per-file license compatibility and attribution before incorporating any third-party code. Do not import Xe3 firmware, alternate accelerators, a fixed minimum clock or AMFI-disabling settings.

### E6 — Metal 3 & Advanced Graphics (revised development sequence)

Dedicate the whole generation to genuine Metal 3 research and advanced graphics on the existing Xe-LP architecture. Establish the accepted E5 integration baseline first. Preserve Metal 2 and never spoof capability flags or enable an unsupported path.

| Module | Planned work and exit evidence |
| --- | --- |
| E6.1 — Capability baseline | Inventory Metal families, device identity, OS/driver/Graphics package versions, resource limits and feature queries; reproduce the E4/E5 baseline with explicit unknowns. |
| E6.2 — Metal 3 feature mapping | Map applicable requirements against [Apple's Metal feature set tables](https://developer.apple.com/metal/Metal-Feature-Set-Tables.pdf); identify supported, missing, optional and unverified features and the owning driver layer. |
| E6.3 — Graphics stack, ABI & provenance | Audit WhateverXe, TGLCompat, kernel accelerator, Metal bundle, compiler bridge and signing chain; pin donor identities, symbols, ABI contracts and reproducible permitted inputs. Establish feasibility of a separate Graphics Enhanced workstream before modifying signed payloads. |
| E6.4 — Shader compiler compatibility | Investigate AIR/GPUCompiler, compiler adapter and Intel backend; validate shader stages, specialization and representative shader outputs; preserve backend identity and explicit failure paths. |
| E6.5 — Advanced resource management | Investigate applicable argument-buffer tiers, resource binding, heaps, residency, texture aliasing, memory coherence and lifetime; add positive and negative tests. |
| E6.6 — Advanced render pipeline | Validate applicable texture formats, compression, MSAA, blending, depth/stencil, tessellation and resource limits; distinguish hardware or API limitations from bugs. |
| E6.7 — Commands, scheduling & synchronization | Investigate indirect commands, fences/events, hazards, queue ordering and resource lifetime; maintain bounded waits and recovery contracts. |
| E6.8 — Framework & application compatibility | Investigate Metal Performance Shaders and MetalFX only where supported; exercise representative graphics/compute workloads and report optional feature support separately. |
| E6.9 — Metal 3 validation suite | Add feature-specific workloads, deterministic output/readback checks, sustained stress, failure reporting and Metal 2 regressions. CI verifies host logic/builds; target GPU execution must be recorded separately. |
| E6.10 — Experimental enablement & rollback | Enable a feature only on qualified configurations after its applicable requirements are demonstrated; retain the existing path elsewhere. If blocked, document missing requirements and preserve the verified Metal level. |

Metal 3 acceptance requires evidence of the applicable family requirements and successful feature-specific hardware workloads, not simply a positive supportsFamily query. MetalFX and other optional capabilities are not assumed to be mandatory. Study [WhateverXe Graphics source/provenance notes](https://github.com/b00t0x/WhateverXe-Graphics/blob/v0.4.5/docs/SOURCES.md). Its package builder consumes premodified signed payloads; it is not a complete binary modification/signing pipeline. A Graphics Enhanced research workstream must first establish lawful inputs, per-file licensing, reproducible patch contracts and a validated trust chain. Do not change the original backend identity or weaken AMFIAnchor. MeowXE3 remains a comparative reference, not a replacement driver architecture.

### E7 — HDMI audio, recovery and hardware video acceleration

Retain E7.1–E7.6 and add E7.7 (digital codec and route), E7.8 (audible stereo and hotplug) and E7.9 (HDMI wake recovery and regression on Acer 46A3).

| Module | Planned work |
| --- | --- |
| E7.1 | Quick Sync/media-engine and VideoToolbox baseline, capability versus execution |
| E7.2 | H.264 hardware decode and encode |
| E7.3 | HEVC 8/10-bit hardware decode and encode where supported |
| E7.4 | VP9 and AV1 decode feasibility; no promise of hardware AV1 encode on Xe-LP |
| E7.5 | VA/AppleGVA integration, IOSurface, pixel formats, color conversion and scaling |
| E7.6 | Safari, video playback, editing/export and sustained media workloads |

Require actual hardware-selected sessions, verified decoded/encoded outputs, and no unexplained software fallback; record unsupported codecs/profiles separately. DRM services are application/platform-dependent and not guaranteed. Reference [Intel media-driver](https://github.com/intel/media-driver) for hardware capabilities, not as a drop-in macOS driver.

### E8 — Advanced macOS Graphics Integration

| Module | Planned work |
| --- | --- |
| E8.1 | OpenGL execution, correctness and application compatibility |
| E8.2 | OpenCL GPU execution, kernels and verified output |
| E8.3 | WindowServer, composition, frame pacing and application responsiveness |
| E8.4 | eDP/HDMI/DP/USB-C display paths, brightness, HiDPI and multi-display |
| E8.5 | Color management, supported formats and HDR where supported |
| E8.6 | OS-specific ABI and Graphics payload compatibility, installation and upgrades |

Qualify each OS/build and connector combination independently. Existing upstream compatibility is not new Enhanced evidence. Do not promise unavailable ports or HDR/DRM features.

### E9 — Hardware Optimization & Reliability

| Module | Planned work |
| --- | --- |
| E9.1 | GGTT/PPGTT, resource lifetime, eviction and memory pressure |
| E9.2 | URB/cache and topology audits; device-specific limits |
| E9.3 | GPU scheduling, preemption, queue fairness and latency |
| E9.4 | RPS, RC6, ForceWake, display power and verified efficiency |
| E9.5 | Hang detection, bounded reset, display recovery and sleep/wake |
| E9.6 | Device-specific quirks, supported PCI IDs, regression and comparative benchmarks |

Optimize only after reproducible measurements; no unsafe clock forcing, indiscriminate MMIO or unsupported identity overrides. Compare equivalent workload, OS, power and display configurations. Separate GPU/package energy from whole-system battery consumption.

### E10 — Full Xe-LP Graphics Qualification

| Module | Planned work |
| --- | --- |
| E10.1 | Per-device/OS feature matrix: verified, limited, unsupported, not tested |
| E10.2 | Sustained graphics, compute, media and mixed-workload stress with output checks |
| E10.3 | Display/audio hotplug, multi-display, suspend/resume, recovery and internal audio regressions |
| E10.4 | Controlled upstream/E4/Enhanced comparisons; performance, stability and power evidence |
| E10.5 | Reproducible artifacts, ABI/security review, installation/rollback, documentation and community qualification |

A CI-approved build is experimental until qualified on real supported hardware. Stable qualification is configuration-specific and requires evidence of the supported feature set, no unresolved release-blocking regressions, repeatable results and a recovery path. Do not claim universal Intel Xe-LP support, Metal 3 compliance, native parity, or performance gains without evidence. Unsupported hardware capabilities remain out of scope.

### Community testing

If you have tested Enhanced, please [open an Issue](https://github.com/rodrigosalesf/WhateverXe-Enhanced/issues/new) with the release/tag, CPU, GPU PCI ID, macOS build, Graphics package version, display configuration, Metal Probe output and observed problems. Remove serial numbers, UUIDs associated with the machine, personal identifiers and other private data before attaching logs. Downloads do not prove successful installations; voluntary reports help establish real compatibility.

---

## Upstream reference documentation

[Original Japanese README](README_ja.md) · [Upstream changelog](CHANGELOG.md)

The following documentation retains upstream installation guidance, compatibility boundaries and attribution. For an Enhanced installation, use the [E4 release](https://github.com/rodrigosalesf/WhateverXe-Enhanced/releases/tag/v0.8.5-enhanced-e4) in place of the upstream WhateverXe binary, with the compatible [WhateverXe Graphics package](https://github.com/b00t0x/WhateverXe-Graphics/releases). Keep a bootable backup EFI.

## Compatibility

| macOS | Required version |
| --- | --- |
| Big Sur | 11.7.11 |
| Monterey | 12.7.6 |
| Ventura | 13.7.8 |
| Sonoma | 14.8.9 |
| Sequoia | 15.8.x |
| Tahoe | 26.7 or newer |

Sequoia and Tahoe accept compatible updates within their OS family. Future Apple changes may require an update to WEX or Graphics.

### Tested on hardware (upstream)

- Tiger Lake-U: 48- and 80-EU configurations.
- Alder Lake-N: 16- and 24-EU configurations.
- Twin Lake: 32-EU configurations.
- Alder Lake-H: 96-EU configurations, including single-channel operation.
- Alder Lake-S: UHD Graphics 770.
- Raptor Lake-U: 48-EU configurations.

See [tested features and known issues](#tested-features-and-known-issues) for OS coverage and display configurations. PCI IDs are listed in [device selection](docs/device-selection.md).

### Expected to work, not yet tested on hardware

- Other supported Tiger Lake-U/H35 configurations, including 96 EU, and Tiger Lake-H45.
- Other supported Alder Lake-N / Twin Lake configurations.
- Other supported Alder Lake-H/P/U and Raptor Lake-H/P/U configurations.
- Other supported Alder Lake-S/HX and Raptor Lake-S/HX configurations.
- Internal eDP on Alder Lake-N / Twin Lake and Alder Lake-H/P/U / Raptor Lake-H/P/U is implemented but has not been tested on hardware. Brightness supports PCH PWM and standard VESA AUX; panel-specific OLED/Intel HDR brightness remains unqualified.

### Further implementation required

- Rocket Lake-S: display control requires additional support.

### No support planned

- Xe-LPG, including Meteor Lake integrated graphics.
- Xe2 and later graphics architectures.

## Installation

1. Add Lilu 1.7.2 or later and `WhateverXe.kext` from the [Enhanced E4 **RELEASE** ZIP](https://github.com/rodrigosalesf/WhateverXe-Enhanced/releases/tag/v0.8.5-enhanced-e4) to OpenCore, with WEX after Lilu. Install [AMFIAnchor](https://github.com/b00t0x/AMFIAnchor/releases/latest) and [`AMFIAnchorInjector.kext`](https://github.com/b00t0x/AMFIAnchor/tree/main/Injectors) as described in the [OpenCore instructions](https://github.com/b00t0x/AMFIAnchor/blob/main/README.md#install-with-opencore).
2. Set `csr-active-config=03080000` (`0x803`) and apply the [configuration](#configuration).
3. Boot the target macOS, install the latest [WhateverXe Graphics pkg](https://github.com/b00t0x/WhateverXe-Graphics/releases), then restart. [Package installation and removal](https://github.com/b00t0x/WhateverXe-Graphics#install).

If upgrading from AMFIPass 1.4.1 Mod, remove its OpenCore entry. Keep AMFI enabled. WhateverGreen and WhateverXe must not be enabled together. `amfi=0x80` and `ipc_control_port_options=0` are unnecessary.

Graphics installs under `/Library` and rebuilds AuxKC without patching System files or snapshots. Restore an old Xe System patch before installing. If you use [OCLP](https://github.com/dortania/OpenCore-Legacy-Patcher) for other root patches, load OCLP's AMFIPass after AMFIAnchor and its injector.

## Configuration

### Required boot arguments

Add to OpenCore's `boot-args`:

```text
-allow3d -disablegfxfirmware
```

### DVMT

Set **DVMT Pre-Allocated to 96MB** in BIOS/UEFI where possible.
If it is fixed at **60MB**, also add `-igfxdvmt` and set these iGPU properties under `DeviceProperties > Add` (usually `PciRoot(0x0)/Pci(0x2,0x0)`):

| Property | Type | Value (hex) |
| --- | --- | --- |
| `framebuffer-patch-enable` | Data | `01000000` |
| `framebuffer-stolenmem` | Data | `0000C003` |

These settings are unnecessary at 96MB and do not increase firmware-allocated memory.

### Other settings

- Add `SSDT-PNLF` for internal-display brightness control.
- GPU selection is automatic; a `device-id` override is normally unnecessary.
- Alder Lake-N / Twin Lake and Alder Lake-H/P/U / Raptor Lake-H/P/U select tiling automatically. Do not use `-yTileDisable`; `AAPL,GfxYTile` is unnecessary.

## Tested features and known issues

The upstream common regression checks cover Metal, OpenGL, OpenCL, hardware H.264 encode/decode and HEVC decode. The table summarizes OS coverage and configuration-specific display features.

| Configuration | Verified coverage |
| --- | --- |
| Tiger Lake mini PCs | Big Sur–Tahoe: 80 EU, two 1080p60 displays, display off/on, Safari video and Widevine |
| Tiger Lake laptops | Big Sur–Tahoe: 48 EU, internal eDP and brightness, HDMI/USB-C, up to three displays and display off/on |
| Alder Lake-N mini PCs | Big Sur–Tahoe: 16/24 EU, two 1080p60 HDMI displays and display off/on |
| Alder Lake-N / Twin Lake laptops | MicroPC 2 and MiniBook X N100 on Big Sur/Tahoe: MIPI DSI, brightness, rotation, display off/on and HDMI/USB-C coexistence. MicroPC 2: HiDPI and up to three displays; MiniBook X N100: optional 60 Hz |
| Raptor Lake-U laptop | MiniBook X U300 on Big Sur/Tahoe: internal MIPI DSI, brightness, rotation, HiDPI and up to two USB-C displays. Internal panel: 50 Hz; optional 60 Hz also tested on Big Sur |
| Alder Lake-H | Big Sur–Tahoe: 96 EU, three displays using HDMI and a DP-to-HDMI adapter. Single-channel `4626` graphics acceleration checked on Big Sur |
| Alder Lake-S | Big Sur–Tahoe: UHD 770, HDMI/DP/USB-C and up to three displays; Safari video, with Widevine checked on Big Sur/Tahoe |

MIPI DSI support is **experimental**, limited to the tested GPD MicroPC 2 and CHUWI MiniBook X N100/U300 panels. Do not expect it to work on other devices.

System sleep/wake support is **experimental**. Tested configurations are MiniBook X N100/U300 (MIPI DSI) on Big Sur and Tahoe with model-specific ACPI settings, using the internal display alone or up to two external displays. Other models, OS versions and prolonged DarkWake cycles remain unverified.

### Known issues and limits

- DisplayPort reconnection can cause black screens or freezes. Tiger Lake USB-C reconnection is also unreliable; Alder Lake-S DP output/reconnection can be slow.
- Some image-conversion operations can crash applications.
- Safari video may occasionally drop frames. FairPlay-protected playback is unsupported.
- Up to three displays are supported. Resolutions beyond the tested configurations remain unverified.
- Some connector layouts and backlight methods, MST and Thunderbolt-managed outputs are unsupported.

### Roadmap

- Complete DisplayPort, USB-C and internal-display support on Alder Lake-N / Twin Lake and Alder Lake-H/P/U / Raptor Lake-H/P/U.
- Improve display reconnection reliability and extend system sleep/wake coverage.

## Build and test

Check out the [E4 tag](https://github.com/rodrigosalesf/WhateverXe-Enhanced/tree/v0.8.5-enhanced-e4) to build Enhanced rather than the upstream baseline on `main`.

Requires macOS, Xcode command-line tools, Python 3.9+, MacKernelSDK and Lilu 1.7.2 development headers/library. Place `MacKernelSDK/` and `Lilu.kext/` in the repository root, or pass `--sdk` and `--lilu`.

```sh
python3 tools/build.py --release
python3 tools/test.py
```

Output is under `build/`. AppleIntelTGLCompat is built here and distributed through Graphics. Optional exact-donor tests accept `--donor` and `--accelerator` paths.

## License and credits

WhateverXe retains WhateverGreen's copyright notices and BSD-3-Clause license.
See [LICENSE.txt](LICENSE.txt). Lilu and MacKernelSDK are separate dependencies.

Thanks to [JulioNectar/XPS13Plus](https://github.com/JulioNectar/Hackintosh-XPS13Plus-IrisXe-Tahoe) for sharing its Xe graphics work. Its compiler adapter and LLVM bridge informed the OS-native AIR conversion used in WhateverXe Graphics.

Internal-panel work also draws on [WhateverXe-RaptorLakeP](https://github.com/samranahmad09/WhateverXe-RaptorLakeP), [X1Carbon-G11](https://github.com/dssoftx/Hackintosh-X1Carbon-G11-IrisXe-Tahoe), XPS13Plus and the [Linux i915 display sources](https://github.com/torvalds/linux/tree/v6.12/drivers/gpu/drm/i915/display) for hardware behavior and implementation comparisons.

eDP boot-handoff and startup corrections also reference the reports and patches from [ann0see](https://github.com/ann0see/WhateverXe/tree/522c0a1bd60b9beac66e00dfd7414823680639dd), [belugaa-01](https://github.com/belugaa-01/WhateverXe-Patched), [Thatisjigen](https://github.com/Thatisjigen/WhateverXe), and [zsz-of](https://github.com/zsz-of/WhateverXe).

The optional MiniBook X 60 Hz panel timing also draws on the [minibookx-ctl display guide](https://github.com/ishad0w/minibookx-ctl/blob/main/docs/guide/display.md).

Display wake rearming and GGTT restoration were informed by [jkbuha/WhateverXe](https://github.com/jkbuha/WhateverXe). The AUX brightness investigation also referenced [JulioNectar](https://github.com/JulioNectar/Hackintosh-XPS13Plus-IrisXe-Tahoe); the VESA implementation uses protocol facts from Linux DRM, without copying NootedGreen code.
