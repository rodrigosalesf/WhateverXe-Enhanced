# Enhanced E5 finalization — experimental release candidate

**Maintainer decision (2026-11-27):** close E5 on reviewed engineering deliverables and a successful integrated CI, without requiring new physical hardware tests; defer unresolved functional fixes and hardware qualification. This is not authorization to activate unverified audio, power or Metal paths. E6 may begin after the E5 experimental release gate, not after a claim of full physical qualification.

## Scope and evidence

- Base: WhateverXe 0.8.6; compatible Graphics companion 0.4.5 as documented upstream.
- Integrated diagnostic work: HDMI preflight/ELD/hotplug replay, GPU telemetry, frequency and RC6 decoders, display power/restore guards, advanced Metal probe, frame pacing, memory accounting/time series, bounded flight recorder and installation preflight. See PRs #4–#21 and the E5 roadmap in main README.
- PR #22: read-only HDMI hotplug pair, CI #77 successful, integrated as b254155. PR #23: native HDMI payload/ABI/route/lifecycle/DIP preparation, CI #83 successful. PR #24: host-only transactional DIP and rollback with readback, CI #84 successful, integrated into audio branch as eb3f4d6. PR #25: reference ABI CI, CI #85 successful as a job, but the ABI result itself is incomplete (AppleHDA/controller unavailable or unsupported; three framebuffer symbols present).
- Prior individual successes are not a substitute for combined integration CI. Record final head and CI run before publishing.

## Explicitly unresolved / deferred

| Area | Engineering disposition | Required future evidence |
|---|---|---|
| HDMI audio stream and hotplug | Native payloads and rollback are standalone; upstream reference is attributed and not compiled/registered. Keep active path unchanged. No functional fix claimed. | Target AppleHDA ABI/layout, exact loaded framebuffer identity, digital codec and pin/transcoder ownership, DIP semantics, hook/rollback integration, audible playback, reconnect and internal audio regression. |
| Suspend/resume and display power | Existing E5.7 scoped restoration guards and diagnostics retained; no additional unverified power writes or sleep workaround. | Controlled sleep/wake, panel and external display restoration, power-state and assertion captures. |
| GPU clocks/RC6/telemetry | Read-only decoders and diagnostics, not a new clock or power policy. | Synchronized workloads, verified counters, residency and power measurements. |
| Memory accounting | Detect anomalous values and temporal gaps without changing allocation accounting. | Live captures, ownership and root-cause analysis. |
| Metal/graphics | Preserve existing Metal path; CPU/compile checks are not GPU tests. No new Metal 3 claims. | Feature-specific and prolonged GPU workloads, E4/E5 comparison, internal/external display and brightness. |
| Multimedia, performance, battery | No new measured improvement or hardware video decode claim. | Repeatable benchmarks, decode/encode and energy measurements. |

## Release gate

Review combined changes and licensing, run all required CPU/static checks and DEBUG/RELEASE builds on Intel macOS, verify packaged artifacts and checksums, prepare installation/rollback guidance and publish only as experimental after the final integrated commit passes. Preserve E4 as a bootable fallback; do not install alongside WhateverGreen or change EFI/security settings automatically. Do not release failed checks or claim physical qualification. No new kernel audio hooks, MMIO writes or codec commands are introduced by the HDMI prep. E6 is dedicated to Metal 3 research; track every deferred E5 item without marking it resolved.
