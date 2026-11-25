## WhateverXe Enhanced E4 — Metal & Rendering Engine (0.8.5)

Experimental prerelease based on WhateverXe 0.8.5, incorporating Enhanced E1–E3. Use the original compatible WhateverXe Graphics 0.4.5 package; this release does not replace or modify it.

### Enhanced changelog
- E4.1 — Revoke decoded GT capacities after unsuccessful hardware sampling or ForceWake release; preserve raw observations for diagnostics.
- E4.2 — Add vertex/fragment shader compilation, offscreen rendering and pixel-by-pixel GPU readback verification to the standalone Metal probe.
- E4.3 — Validate native framebuffer allocation bitmaps and reject ownership changes detected during GGTT inspection.
- E4.4 — Avoid redundant writes to already configured RCS context fields; test idempotence and GGTT boundaries.
- E4.5 — Reject inaccessible all-ones MMIO reads and empty reset domains before reporting successful reset polling; retain bounded recovery and cleanup.
- E4.6 — Add 1–1000 repeated compute/render micro-workloads, changing inputs, output verification and host/GPU latency statistics (min, median, p95, max when available). Add host-only statistics and argument checks in CI.

### Assets
- DEBUG and RELEASE ZIPs: the exact CI #21 packages, with symbols and original bundle identity.
- metal_probe.swift: standalone diagnostic source from the exact approved commit; not an additional kext or a precompiled executable.
- SHA256SUMS: ZIP and diagnostic-source checksums.

### Diagnostic usage
On the target macOS with Xcode command-line tools:
```sh
xcrun swiftc -swift-version 5 metal_probe.swift -o metal_probe
./metal_probe --iterations 100
```
For multiple GPUs, use --registry-id with the target GPU's actual registry ID. The probe measures small workloads, not FPS or peak throughput. Stop testing on errors or hangs; keep a separate recovery EFI.

### Validation and limits
CI #16–#21 reported success. The publisher verifies CI #21's exact source commit and package checksums before creating the prerelease. CI compiles the Metal probe and exercises host-only logic, not real GPU workloads. Optional native binary tests requiring external inputs are not claimed to have run. No physical hardware qualification, measured performance improvement, complete Metal support, video codec improvement, or Tahoe runtime guarantee is claimed. Do not load WhateverGreen together with WhateverXe.

Source: c24d6d8bc8e3b98977eab4e146c8d26463a0d338
