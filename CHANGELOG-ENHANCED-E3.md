## WhateverXe Enhanced E3 — Display Intelligence (0.8.5)

Experimental prerelease based on upstream WhateverXe 0.8.5, with the E1/E2 changes carried forward.

### Enhanced changelog
- E3.1: fail closed on invalid or reserved DVMT reads, reset stale memory state, and guard missing devices.
- E3.2: validate physical DDI record identity, native port count and aligned record decoding.
- E3.3: reject unsupported DP lane counts, invalid status responses and stale receiver qualification.
- E3.4: validate VESA AUX capability probes and brightness ranges; preserve the existing PWM algorithm.
- E3.5: qualify wake caller size and reject inaccessible IRQ master readback during repeated enable.
- E3.6: add a standalone Metal compute probe with per-device registry ID, shader compilation, bounded command completion and output verification. The probe is available in source (tools/metal_probe.swift), not inside the kext packages.

### Validation
CI #9 through #14 reported success. The publisher reuses the verified DEBUG and RELEASE ZIPs from CI #14 on the exact E3 source commit and verifies their SHA256 checksums. CI compiles the Metal probe but does not execute GPU workloads. Optional native binary checks requiring external inputs are not claimed to have run.

No new physical hardware qualification, performance gain, complete Metal support or sleep/wake guarantee is claimed. Use the matching WhateverXe Graphics stack and Lilu, keep a recovery EFI, and do not load WhateverGreen alongside WhateverXe.

Source: 619b440c318b2577c357ceebb0e0f6b9dfeebe74
