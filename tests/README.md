# CPU test contracts

These tests check bounded CPU behavior, dependency metadata and selected driver
instructions. Passing them does not establish GPU execution, physical display,
firmware behavior or arbitrary kernel scheduling.
The same contracts apply to WhateverXe, AppleIntelTGLCompat and their connection;
separate source/bundle locations do not create a weaker quality boundary.

Run `python3 tests/xe_data_access.py <expanded-graphics-pkg>` against a
standard Graphics package expanded with `pkgutil --expand-full`. This follows
the mandatory local dependencies of each OS's actual VA driver and exercises
the production WebKit GPU access decision for their installed paths. The
kernel signing queries are modeled. Safari playback requires a separate test.

## Enhanced experimental checks

`sleepable_delay` extracts the three real thread-context delay methods from
`kern_xe.cpp`. Modeled IOSleep and IODelay must account for the complete
requested interval, including zero, sub-millisecond and remainder values.
No IRQ context, actual elapsed wall time or scheduler behavior is verified.
`display13_clock_set` additionally tests odd polling budgets and an existing
PCODE command completing at the deadline: no new command may be submitted
when that wait has spent the entire budget. Existing clock state transitions
remain covered. `display13_panel_runtime` checks that off/inaccessible PPS
status cannot authorize AUX brightness writes and releases temporary refs.
Its actual donor binary replay is separately optional. These checks preserve
hardware, donor and native ownership admission and are not qualification.

## Enhanced E2 regression checks

`device_selection` checks diagnostic categories independently of admission: a
physical backend, a known or unknown explicit override, rejected overrides,
unsupported identities and invalid PCI inputs. The selection policy and ABI3
layouts remain unchanged; this is not hardware qualification.
`xelp_memory_layout` checks complete aligned MMIO windows and a modeled DSM
high/low/high read, including inaccessible words, changed high words and no
register access after failed admission. A failed reservation refresh must revoke
allocator/recycle admission rather than retain a stale certificate; valid
reservation and pool cases remain covered. `alderlake_n` checks that an optional
EDRAM output is invalidated on early refusal and that an unmapped requested
EDRAM register prevents forcewake acquisition. Callers not requesting EDRAM
retain the existing path. Hardware MMIO, IOKit property publication and actual
GPU execution remain unverified.

The E2 follow-up extends `adlp_resources` and `alderlake_n` with explicit
mobile fuse rejection reasons and ownership-failure diagnostics. The decoder
retains its existing capacity admission and the GT readout layout is unchanged.
`framebuffer_common` checks the new diagnostic property on entry mismatch,
route failure, common/backend failure and hook installation, independently of
native startup success. These are CPU fixtures; neither successful sampling nor
hook installation demonstrates working acceleration or hardware qualification.

## Enhanced E5 HDMI audio preflight

Run `python3 tools/test.py --only hdmi_audio_probe --require hdmi_audio_probe`.
The CPU fixture calls the actual user-space collector with synthetic ioreg
plists and system_profiler JSON. CTA-861 audio evidence is independent of the
HDMI vendor block: basic audio and short audio descriptors are reported only
after complete EDID length, block checksums and CTA data-block bounds pass.
Fixtures cover multiple extensions, truncation, malformed lengths, checksum
failure after a positive block, missing commands and output redaction.
These are parser/collector checks, not an AppleHDA, ELD, HDA verb, MMIO or
hardware playback test.

On macOS run `python3 tools/hdmi_audio_probe.py` for a read-only JSON snapshot.
It reports selected properties and counts rather than raw EDID, device names,
serials or machine identifiers. Missing properties or classes are not proof
that audio is unsupported. The investigation is informed by
[jkbuha's contribution](https://github.com/b00t0x/WhateverXe/issues/150)
and [initial findings](https://github.com/b00t0x/WhateverXe/issues/124).
No codec wake, donor hooks or kernel changes are included.

### E5.2 offline ELD validation

The same registered `hdmi_audio_probe` test now also checks ELD v2 baseline
lengths, monitor-name and descriptor bounds, maximum descriptor counts,
connection type, and explicit stereo 16-bit LPCM rates. Layout reference:
[Linux v6.12 drm_eld.h](https://github.com/torvalds/linux/blob/v6.12/include/drm/drm_eld.h).
The collector does not combine channels, rates or bit depth from different
descriptors; a basic-audio flag is not treated as an explicit SAD. It rejects
truncated/malformed baseline structures and reports unsupported versions or
connection types separately. Optional vendor bytes are not interpreted.
Synthetic fixtures and a subprocess CLI check exercise the actual parser
and report consumer, including redaction and bounded input. This is not
a live ELD read, ELD generator, audio route selection, or codec programming test.

Offline binary fixtures can be analyzed on CI hosts with
`python3 tools/hdmi_audio_probe.py --eld-file eld.bin --edid-file edid.bin`.
The EDID is optional. Comparisons report intersection/differences in explicit
PCM rate evidence, not an association between physical displays or proof of
playback. No kernel changes or new boot arguments are included.

### E5.3 offline HDMI lifecycle replay

Run `python3 tools/test.py --only hdmi_hotplug_replay --require hdmi_hotplug_replay`.
The user-space replay consumes a bounded JSON event list for one modeled
connector. Each connect, disconnect, suspend or resume invalidates prior ELD
evidence and advances its epoch. ELD results must carry their acquisition
epoch; stale results do not overwrite current evidence, and current invalid
samples revoke it. Resume requires a fresh connection event. These are
conservative replay rules, not assertions about native Apple framebuffer or
HDA event delivery. Fixtures cover duplicate connect, different sink,
late completion, malformed current and stale samples, suspend/resume,
inactive samples, invalid input and CLI redaction. This uses the actual ELD
parser and report consumer. It does not implement kernel callbacks, real
multi-display ownership, locking, audio stream teardown or hardware recovery.

Replay an offline file with `python3 tools/hdmi_hotplug_replay.py events.json`.
Events are objects such as `{"event":"connect"}`, `{"event":"disconnect"}`,
`{"event":"suspend"}`, `{"event":"resume"}` or
`{"event":"eld","epoch":1,"hex":"..."}` (hex must be actual bytes).
Epochs begin at zero and advance on accepted lifecycle events. No raw ELD
or arbitrary input text is included in reports. Input is limited to 1 MiB,
1024 events and 4096 ELD bytes per sample.

### E5.4 accelerator telemetry snapshot

Run `python3 tools/test.py --only gpu_telemetry_probe --require gpu_telemetry_probe`.
The host-only test exercises the actual snapshot parser and offline CLI with
synthetic XML/binary IORegistry plists, including observed Intel counter names.
It distinguishes missing, observed zero, invalid unsigned/percentage values,
all-ones and suspicious high-bit texture byte values. A high-bit observation
does not prove signed underflow. GART used/size comparisons are reported only
within the same record and are not proof of memory corruption or physical VRAM.
Fixtures cover bounds, multiple accelerators, privacy, malformed input and
bounded offline files. No counter is rewritten or synthesized.

`python3 tools/gpu_telemetry_probe.py --snapshot snapshot.plist` parses offline
fixtures. Without that argument it performs a read-only IOAccelerator registry
query on macOS. The tool does not measure frequency or activity independently;
zero, missing and opaque values cannot establish GPU inactivity. No live
GPU execution, MMIO, RPS, RC6 or power changes are tested by CI.

### E5.5 Xe-LP frequency snapshot decoder

Run `python3 tools/test.py --only gpu_frequency_probe --require gpu_frequency_probe`.
The offline tool `python3 tools/gpu_frequency_probe.py snapshot.json` decodes
caller-supplied unsigned 32-bit register words with explicit layout
`intel-xe-lp-gen12`. Optional JSON fields are rp_state_cap (0x145998),
freq_info_rec (0x145ef0), rpstat1 (0x1381b4), and rpnswreq (0xa008).
The first two provide nominal RP0/RP1/RPn limits in 50 MHz units;
actual and request opcodes use 50/3 MHz units. RP1 comes from FREQ_INFO_REC,
not the legacy RP_STATE_CAP middle byte. Reference: Linux v6.12 i915
[intel_rps.c](https://github.com/torvalds/linux/blob/v6.12/drivers/gpu/drm/i915/gt/intel_rps.c),
[intel_gt_regs.h](https://github.com/torvalds/linux/blob/v6.12/drivers/gpu/drm/i915/gt/intel_gt_regs.h)
and [intel_mchbar_regs.h](https://github.com/torvalds/linux/blob/v6.12/drivers/gpu/drm/i915/intel_mchbar_regs.h).
The tests exercise the actual decoder and CLI with independent literal fixtures,
including conversion rounding, field width, invalid/missing/all-ones words,
zero, inconsistent limits and comparisons without clamping.
RP0 is a nominal non-overclocked limit; the request register is not proof of
the driver's software target or GuC policy. Input identity, actual register
mapping, access ownership, coherent sampling and physical clocks remain
unverified. This tool neither acquires forcewake nor performs MMIO or changes
frequency policy. No hardware power or performance improvement is claimed.

### E5.6 RC6 interval diagnostics

Run `python3 tools/test.py --only gpu_rc6_probe --require gpu_rc6_probe`.
The offline decoder accepts two caller-supplied observations with explicit
layout `intel-xe-lp-gen12-rc6`, unsigned monotonic time_ns, reset epoch,
and unsigned 32-bit rc6 words. The Gen12 RC6 register is 0x138108;
the 1280 ns tick and 32-bit wrap follow Linux v6.12
[intel_rc6.c](https://github.com/torvalds/linux/blob/v6.12/drivers/gpu/drm/i915/gt/intel_rc6.c)
and [intel_gt_regs.h](https://github.com/torvalds/linux/blob/v6.12/drivers/gpu/drm/i915/gt/intel_gt_regs.h).
The result is conditional on the caller's identity and counter continuity.
Reject invalid timestamps, reset epoch changes, inaccessible words and
windows that could include a full wrap (including one tick uncertainty).
Do not clamp inconsistent residency to 100%; sub-tick ambiguity is explicit.
Fixtures exercise real parser, output and bounded CLI. No register reads,
wake acquisition, RC6 enablement or power change is implemented.
The existing ForceWake IRQ protection and its tests are unchanged; the
optional native donor replay still requires the original accelerator binary.

### E5.7 display power diagnostics and shared restoration

Run `python3 tools/test.py --only display_power_probe --only display13_shared_restore --require display_power_probe --require display13_shared_restore`.
The production GGTT restore helper now rejects the ambiguous all-ones
requested word before writing and rejects all-ones posting reads explicitly.
The existing shared restoration fixture executes the production wrapper
with stopped/live consumers, invalid initial and posting values, and retry;
power-well restoration and native engine enable remain modeled leaves.
An ambiguous initial word must remain untouched, pending restoration must
remain set, and engine enable must not proceed until a valid retry.
This does not prove physical MMIO or sleep/wake behavior.

The offline `python3 tools/display_power_probe.py snapshot.json` accepts
layout `intel-display12-13-dmc`, before/after objects with time_ns, epoch,
and optional unsigned dc5/dc6 words. Register layout follows Linux v6.12
[intel_dmc_regs.h](https://github.com/torvalds/linux/blob/v6.12/drivers/gpu/drm/i915/display/intel_dmc_regs.h)
and [intel_dmc.c](https://github.com/torvalds/linux/blob/v6.12/drivers/gpu/drm/i915/display/intel_dmc.c).
DC5/DC6 are DMC entry event counts, not residency or current power state.
Missing, invalid, all-ones, decreasing and discontinuous samples remain
distinct; increasing counts are conditional differences, not a proof
against unseen wrap or reset. Seven host-only test methods exercise the
actual decoder and bounded CLI. No new DC policy, DMC firmware or live
counter collection is enabled. Hardware power savings are not established.

### E5.8 advanced Metal resource validation

The existing `tools/metal_probe.swift` keeps its standard compute/render
workload by default. On a suitable physical GPU, `metal_probe --suite advanced
--iterations 10` also checks a buffer-backed R32Uint texture: CPU writes to
aligned shared backing storage are read by a compute shader and verified
after command completion. A separate private RGBA8 texture is uploaded,
mipmaps generated, and all four levels read back and checked against a
constant per-iteration color. Both stages use bounded command completion
waits and changing patterns; allocation, compilation, timeout or output
failure is reported, not silently treated as a pass. Unsupported texture
configurations may fail the opt-in suite; no support claim is inferred.
The tests cover CPU-to-GPU alias visibility and ordered blit operations,
not all resource synchronization scenarios, presentation, or Metal 3
compliance. CI compiles the Swift program and exercises host-only expected
values, timing and invalid/duplicate CLI arguments. MSL runtime compilation,
GPU execution and resource compatibility remain deferred to real hardware.

### E5.9 frame pacing diagnostics

Run `python3 tools/test.py --only frame_pacing_probe --require frame_pacing_probe`.
The offline analyzer `python3 tools/frame_pacing_probe.py trace.json` accepts
one continuous trace with explicit source (presentation, vblank, or synthetic),
a rational nominal refresh rate and strictly increasing integer nanosecond
timestamps. Example synthetic input:
`{"source":"synthetic","refresh":{"numerator":60,"denominator":1},"timestamps_ns":[0,16666667,33333334,66666668]}`.
It reports event cadence, minimum/median/nearest-rank P95/maximum intervals,
and the fraction of intervals strictly longer than 1.5 nominal periods.
Integer arithmetic preserves fractional refresh thresholds (e.g. 60000/1001 Hz).
An optional `--reference baseline.json` compares matching source and nominal
refresh; equivalent capture conditions and workloads are not established.
The nine host-only test methods cover literal statistics, fractional thresholds,
large timestamp origins, invalid inputs, comparison and bounded CLI.
No live capture, variable-refresh interpretation, presentation hooks, actual
dropped-frame counts or performance gains are claimed. VBlank cadence is not
application FPS; Metal command-buffer timing must not be used as presentation
timing. Raw timestamps and unrelated metadata are not exported.

### E5.10 GPU memory ownership accounting

Run `python3 tools/test.py --only gpu_memory_probe --require gpu_memory_probe`.
The offline tool `python3 tools/gpu_memory_probe.py snapshot.json` uses
the normalized diagnostic schema `wex-memory-accounting-v1`, not an Apple
driver ABI. Supply a single coherent snapshot with local integer IDs:
clients [{id}], contexts [{id, client}], queues [{id, context, client}],
and allocations [{id, bytes, queues}] (queues is a list of queue IDs).
A queue is resolved only when its declared client agrees with its context
and the client is present. Each allocation is counted once; multiple queues
of one resolved client are grouped, multi-client allocations are shared,
and any unresolved link leaves the allocation unattributed. Duplicate IDs
and links, invalid schemas, excessive input and aggregate overflow fail
closed. Invalid byte sizes are counted separately. Client IDs are replaced
by local ordinals in the report; these are not stable across captures.

Nine host-only tests exercise the actual accounting and CLI, including
conflicts, missing links, shared allocations, bounds and redaction. These
are synthetic allocation graphs, not live IORegistry ownership evidence.
Observed bytes do not establish physical residency, GART usage or complete
per-process VRAM; shared bytes are not duplicated in exclusive totals.
No live queue collector, memory allocation policy, eviction or kernel
changes are included. Existing queue-trace and memory-layout guards remain
unchanged; native ownership/lifetime validation is still pending.

### E5.11 bounded flight recorder core

Run `python3 tools/test.py --require xelp_flight_recorder --require xelp_flight_recorder_mutants`.
The standalone C++ header uses compile-time fixed capacity (1–1024 entries),
value-only event kinds and caller-supplied monotonic timestamps. Disabled by
default; explicit reset enables and clears history. A full buffer overwrites
the oldest event and reports the number lost; indexed reads are chronological.
Freeze preserves the recent history until reset. Invalid event kinds and
backward timestamps cannot change the buffer. No dynamic allocation, I/O,
pointers or process identifiers are stored as event payloads.

The CPU test automatically discovered by the runner exercises the actual
header under address and undefined-behavior sanitizers, including disabled
state, reset, wrap, single-slot capacity, freeze and rejected input. The
registered semantic-mutant test requires real assertion failures when
chronological ordering or freeze protection is deliberately broken.
Conceptual references: [Linux tracing ring-buffer design](https://docs.kernel.org/trace/ring-buffer-design.html)
and [Mesa hang debugging](https://docs.mesa3d.org/graphics-debugging/debugging-misrenderings-crashes.html).
No third-party recorder implementation is copied.

This core is not installed or called by the kernel yet. It requires a
single owner or external serialization, a verified timestamp source and
an approved export contract before wiring any runtime producer/consumer.
No IRQ safety, concurrent writers, kernel dump persistence, live collection,
or performance overhead measurement is demonstrated. No additional boot
arguments or default driver behavior changes are introduced.

### E5.12 read-only installation preflight

Run `python3 tools/test.py --require install_preflight`.
The offline tool `python3 tools/install_preflight.py config.plist --darwin 24.6.0`
checks the standard post-install OpenCore configuration documented in the
README and [AMFIAnchor OpenCore instructions](https://github.com/b00t0x/AMFIAnchor#install-with-opencore).
The caller explicitly supplies the target Darwin version, within 20–25.
Enabled canonical top-level kext names are filtered by architecture and
inclusive kernel bounds. Report missing or duplicated required entries,
Lilu/anchor/injector ordering, incompatible WhateverGreen coexistence,
AMFIPass ordering and departures from the documented boot arguments and
SIP setting. These are configuration findings, not proof of boot failure.
Custom injectors, renamed bundles, installer profiles, NVRAM overrides and
actual bundle versions/identities are not validated. No personal config
fields, serial numbers, filenames or raw arguments are printed.

An optional `--backup-config backup.plist` checks a separate readable
configuration with the same policy; it rejects the same file (including
aliases). It does not create or validate a full EFI backup or restore it.
Exit 0 means no known findings in the supplied configuration(s), 1 means
findings, 2 means invalid or unavailable input. Eight host-only tests
exercise the actual parser and CLI. Input is bounded and no configuration
or EFI files are written. Before installation, separately verify the full
backup, matching OpenCore ocvalidate, bundle files, Lilu version, Graphics
payload, hardware identity and DVMT. Existing build-time Compat ABI/export
checks, x86_64 packaging and dSYM UUID checks remain mandatory and unchanged.
No new native ABI support or hardware bootability is established.

### Enhanced quality gate (initial scoped baseline)

The mandatory `Test and build` job runs Ruff 0.11.13 (F63/F7/F82: selected
Pyflakes correctness rules) on E5 Python probes and tests, actionlint 1.7.11
on ci.yml (workflow validation only; external shellcheck/pyflakes integrations
disabled), and the runner's Homebrew LLVM 18 Clang-Tidy on
tests/xelp_flight_recorder.cpp, including the recorder header. Clang-Tidy
uses the checked-in analyzer/bugprone subset with warnings as errors;
the same host fixture is compiled with strict warnings. Configuration files
provide formatting defaults; whole-tree formatting is not enforced or
applied automatically. Extend the scoped checks as new code is introduced.
The runner image is not a pinned compiler build; log actual tool versions.

The CPU test runner still executes its full default suite and explicitly
requires every E5 registered CPU contract (including shared restoration,
flight-recorder semantic mutants and installation preflight). Existing
ASan/UBSan host fixtures, Metal Swift compilation and self-test, DEBUG/RELEASE
builds, Compat ABI/export checks and packaging checks are retained.
Optional native donor modes still require exact inputs and report omissions.
The initial quality gate neither statically analyzes the complete kernel nor
validates Swift style, hardware behavior, native ABI execution or Metal 3.
Do not claim CodeQL, SwiftLint, Cppcheck, or other tooling is enabled until
its own configured workflow actually executes.

## Maintaining test contracts

`tgl_recovery` runs the production wrapper and helper against ABI-matched
reset, scheduler, event-machine, submit and wait callees. The exact TGL donor's
successful non-render branch provides the increment/submit/one-second wait
sequence; only Blit uses it here. For other engines and failed resets the ICL
single-pass ordering and accounting remain mandatory. The fixture checks the
real affected channel, two reload points, raw timeout polarity, no stamp on an
absent affected channel, bounded call counts and published outcomes. Semantic
mutants exercise lost or duplicated work, erroneous gating and failure effects.
This CPU check does not execute the donor's callback bodies, Lilu installation,
IOAccel locking, GPU execution or stamp retirement. The exact donor guards and
an observed live recovery are required at those boundaries.

`tgl_reset_poll_native` executes the production installer, naked bridge and
bounded full-width GDRST helper inside the fixed TGL reset body. It preserves
native scratch writes, forcewake release and context-replay/false exits, checks
the VECS bit above bit 7 and detects timeout, truncation and cleanup mutants.
MMIO acknowledgement, time/forcewake and the scheduler replay leaf are models;
this does not establish electrical reset or GPU progress.

`tgl_recovery_native` takes `--accelerator` and `--ioaccel`.
The accepted Big Sur through Tahoe originals execute eventTimeout, FIFO restart,
diagnosis selection, native stamp resubmission, stamp comparison/deduplication,
fence notifier/list retirement, the real BlockFence client payload callback and
the synchronous finish_fence_event caller. Native IOAccel owns the synchronous wait, its shared
cache writeback, interrupt deregistration and wait-time accounting. The replay
checks both an already-reached target (zero wait time) and a normal arrival
inside the wait (the same duration reaches both reporter channels). It also
checks late fence retirement once and a subsequent normal submission. For Compute, the native watchdog
progress check cancels a stale restart before the engine halt and admits a still-stalled channel.
The exact timeout routine returns the affected channel to FIFO while RESET_CTRL
indicates readiness. The device model clears that hold on an acknowledged
domain reset and retains it on an unacknowledged one. Neither readiness nor
the scheduler returning to the running state delivers a pending client fence.
Compute and media run the donor's beginReset, ring rebuild, updateRingTail,
endReset, descriptor selection and SQ/LOAD stores into RAM. The output records
both the command producer's tail and the context image tail after restart.
Dropping LOAD or clearing the force-restore flag must fail before any stamp
is supplied. CPU submission does not establish GPU execution.
The notification cases take hardware stamp arrival as an independent input,
using the address and value decoded from Compute PIPE_CONTROL or media
MI_FLUSH_DW. Kernel scheduling/locks, VM mappings, forcewake, interrupt
delivery, diagnostic report publication, idle accounting, DMA and normal
scheduler enqueue capacity remain modeled. An observer bounds the native
pending-wait case in a child. A permanently missing stamp can leave callers
waiting. The retained state does not establish recovery, safe teardown or idle.

Apply these rules to implementation changes and test additions, corrections,
merges and removals. An existing passing test is not an approved specification.
The [check inventory](#independent-expectations-and-boundaries) describes selected
checks; it is not certification of every assertion or of the entire suite.

Before a change, identify the intended behavior and retained behavior, then
choose the production paths and tests needed to protect them. Keep a short
description near the test, in this document or in the change description:

| Record | What to identify |
| --- | --- |
| Contract and basis | Accepted capabilities, required effects, owner/order/failure rules; specification, reference implementation, exact donor caller/consumer or immutable positive history |
| Tested path | Production entry, input producer, state propagation and consumer; explicitly modeled prerequisites and hardware/OS boundaries |
| Counterexamples | Invalid rejection, missing work, wrong delegation, duplicate effects or another plausible error that must fail; valid inputs and meaning-preserving variations that must still pass |
| Execution and limits | Required modes/inputs, tested source and result locations, omitted paths and conclusions the check cannot support |

Reuse an existing description when it still applies. Do not create a separate
form for every assertion or copy implementation conditions into an oracle.
Synthetic cases need a contractual basis; retained readouts need provenance.
Capacity, bit position, OS metadata and layout should vary independently where
the consumer contract allows it. Previous positive inputs remain independent
protections; previous negative inputs must not freeze an admission limit.

WEX owns the required adaptation for target Xe-LP devices, including reused
native paths. A branch declining work must reach another correct WEX handler
or a native path expected to work for a stated reason. Preserve shared handling
for the same contract and split confirmed differences. Test both responsibility
gaps and wrong backend selection. Mismatch with an observed configuration,
resource tuple, build metadata or fixture size alone is not a rejection reason.
Preserve actual ownership, input-safety, ABI and fixed-donor identity guards.
If a required operation or ABI cannot be established, keep the corresponding
consumer unready and record the missing capability. Refusal is not completed
support for that capability.

Use real production code for the dependency decisions and state propagation
being tested. A direct helper check does not prove its caller reaches it.
An explicit `true` prerequisite is still a model assumption: identify how the
real producer establishes it and test the connection where required. Do not
auto-enable fields or dependencies discovered in production source. Check the
effect at the consumer, including failure, retry, reentry and missing events
where relevant. A successful return or internal ready flag need not mean that
the requested work occurred. For shared notifications, model native ownership
and delivery as well as WEX calls.

On failure, compare both the test model and production against the independent
contract. Fix the incorrect side, which can be both. Distinguish fixture API
updates from changes to expected behavior; record the basis for the latter.
Do not delete a valid input, add a success stub or skip a mode to make a known
defect pass. Do not restore an obsolete candidate policy merely for an old test;
establish whether its original requirement was valid and where it is protected.
If the contract remains unresolved, keep that uncertainty visible.

Before deleting or merging tests, identify each useful contract, boundary and
counterexample and where its protection remains. Move unique protection first.
Keep useful structural lint labeled as such; neither test counts nor source
spelling can substitute for behavior checks.
For important contract changes, demonstrate a relevant semantic fault failing
at the intended behavior assertion. Reuse suitable existing counterexamples;
extraction/compile failures are not evidence of detecting the intended defect.
Do not require a global mutation score or a new framework.

Register new scripts and modes in `tools/test.py`, with distinct job names,
required inputs and correct kinds. Shared helpers need registered callers.
Run the modes required by the affected contract with `--require`; the default
CI command does not supply optional original inputs. Registration completeness
does not prove requirement coverage. Keep per-run failures and omissions,
including when a later run resolves them. Combine complementary runs only when
their source, fixtures and input contracts correspond; do not select passing
fragments to hide unresolved failures. Update the relevant descriptions when
contracts, boundaries or modes change. Report those boundaries, required-mode
results and limits before aggregate counts, and keep build and hardware claims
separate from CPU assertions.

## Selecting and requiring checks

```sh
python3 tools/test.py --list
python3 tools/test.py --only profile_admission --only display13_power_dispatch
python3 tools/test.py --accelerator /path/to/AppleIntelTGLGraphics --only tgl_gt2_urb_native --require tgl_gt2_urb_native
```

`--list` includes modes whose inputs are absent. `--only` is repeatable and
accepts shell-style patterns; quote patterns to keep the shell from expanding
them. `--require` also selects its matches and makes missing inputs a failure.
Default CPU checks can succeed with optional binary checks skipped. The result
records those omissions; that success must not be described as binary replay.
The `binary-check` kind means an original input was supplied. Individual
checks may validate bytes, execute selected instructions, or both; it does not
mean that the complete original driver executed.

Each invocation creates a new directory under `build/tests/run-*`, or uses the
new directory supplied with `--output`. Each job has its own `test.log`.
`results.json` records passed, failed, skipped and not-selected jobs. Core C++
jobs with the same stem as a Python adapter have an explicit `_cpp` suffix;
both run and neither result overwrites the other. `fully_executed` refers only
to this job inventory, never to hardware/function coverage.

Compile and execute stages are distinct for direct C++ jobs. Python replay jobs
report a script stage; their inner extraction/compiler/runtime diagnostics are
in the log, rather than being classified from a return code alone.

The original Apple inputs are optional, local and untracked. Use the exact
inputs accepted by each replay. Kernel and host modes also need Lilu HDE via
`--hde-source`. Do not put Apple driver files in this repository or public CI.
Additional modes declare their inputs explicitly: `--linux-tables` accepts
`intel_ddi_buf_trans.c` for the DKL coefficient oracle; `--ccs-records` accepts
retained JSON `records` with `after.aux` and sixteen `after.words` for an aux-state
reproduction; `--pcode-donor` supplies the distinct original required by the
eDRAM diagnostic. Its audit copy stays in that job's output and is not deployable.
The outer-ring check uses current production source unless `--outer-source` is
explicitly supplied. These input identities do not restrict runtime OS updates.

Every standalone Python script has an enumerated mode. `production_source.py`,
`pmap_kernel_contract.py` and `compat_test_support.py` are shared helpers exercised by registered callers.
The registry contract checks that newly added scripts are not silently omitted.

## Independent expectations and boundaries

| Check | Expectation and source | Boundary and exclusions |
| --- | --- | --- |
| `compat_exports.py` | Fixed `c004fc1a` donor imports, native DSB caller/field producers, mapped-memory extent, contiguous Gen12 PTE address encoding, DSB manager dispatch and zero-success return | Compiles the complete Compat translation unit with kernel/IOKit boundary mocks, retaining export asm names. Executes MMIO, DSB allocation/zeroing/PTE installation/publication, failure/retry, clock and lifecycle. Hardware DMA, the system mapper and actual DSB queue execution are outside this check |
| Graphics activation (`compat_exports.py`, `host_publication.py`) | Either component alone must preserve firmware graphics; native drivers may start only with an active, compatible WEX plugin. Activation ABI 1 is a runtime registry token, independent of EFI/AuxKC linking | Executes the actual accepted pluginStart body, token publisher and complete Compat start consumer. Missing, malformed and incompatible tokens reject start. The early callback may copy read-only firmware facts after PCI publication; it must not initialize/configure the GPU. Actual host dispatch ignores unrelated notifications until a Graphics image arrives, then initializes once. Lilu's shouldLoad decision, OSKext dependency failure propagation, AuxKC construction and GOP scanout require separate loader/hardware validation |
| `firmware_readout.py`, `firmware_panel_identity.cpp` | Intel OpRegion mailbox 5 and Linux v6.12 `intel_bios.c` BDB 41/42 PNP identity: exact-date match precedes an undated match; no blind profile-zero fallback. Identical child records have the same ownership; conflicting records do not | Actual early acquisition, inline/external VBT, owner cache, wiring, PPS delay and PWM consumers. Explicit indices and LFP2 are retained. Equivalent consumed facts remain usable without claiming an index; divergent candidates, malformed pointers/EDID and conflicting children cannot supply panel routing. Mapping and MMIO are modeled. Snapshot loss, foreign ownership and disconnected EDID mutations fail. Physical mailbox availability and output remain hardware boundaries |
| ADL-S initial panel mode (`adls_panel_pwm.py`) | Fixed donor reset starts Combo mode0 before mode1 publication. The bound internal panel, controller/access association and PG1 witness independently establish PWM ownership | Production LightUpEDP wrapper captures PWM in mode0/1, then delegates once. Native mode checks the reset producer and executes the PWM tail for the first mode0 cycle and subsequent mode1 cycles. Restoring mode1-only admission fails semantically. No claim of a complete ADL-S cold engine reset or physical panel training |
| Deferred Display13 clock (`display13_training_frontend.py`) | Exact donor stop caller defers clock removal until DDI buffer/transcoder stop. Reentry with the same owner/value is the same pending operation | Actual deferred request and stop consumer with the real power bridge and mocked MMIO. Identical repetition stays pending without a fault; conflicting values stay suppressed without overwriting the request; running DDI prevents clock removal. Physical disable timing remains outside the model |
| `compat_producer.py` | Immutable ABI3 binding and port modes from the exact donor/Compat contract. Legacy ABI3 rejects a nonzero Alt mask | Real WEX bind, port state, direct HAL mode and both HPD dispatchers. A mixed eDP/TC board retains its panel path when a TC hook is absent and uses the same pinned provider after the TC path becomes available. A pre-Alt provider gets the representable subset. Complete Compat is executed. Native state/HPD leaves, hook installation and hardware are boundaries |
| `display13_tiling.py` | Shared IRQ/power/clock and multi-output retirement precede native startup. The firmware transcoder identifies the boot output | Actual start prelude, provider properties and deferred boot selector. A missing TC hook permits eDP boot and blocks fixed TC boot before TC capture; restoring it reaches the existing handoff. DP-alt GOP stays unqualified. Readout, final boot-memory preparation and native start are boundary models |
| Display13 boot link depth (`display13_linear_dp.cpp`, `display13_fb_memory.cpp`, `display13_boot.cpp`) | Linux v6.12 `i915_reg.h` TRANS_DDI_BPC encodes 8/10/6/12 bpc as 0/1/2/3; lane width is a different field. The four-byte RGB plane does not require an 8-bpc output link | Actual source readout, plane conversion, GGTT backing inspector and multi-output parking retain the firmware depth. Reserved depths fail before writes/PTE reads; drift is refused. This preserves a firmware link, not HDR or native deep-color modeset support |
| `display13_boot_handoff.py`, `display13_training_frontend.py`, `display13_sst.py` | Fixed donor `resetSoftwareState` initializes Combo mode to 0 before `setPortMode`; exact physical config, access owner and TC modes remain required | Production setup-workloop -> SST selection -> boot AUX adoption -> port stop/re-enable, and training wrappers. Prequalified framebuffer memory and provider IRQ registration are boundaries. `display13_sst_native` checks producer bytes and replays existing native port operations; full native startup and physical link training are outside the model |
| `display13_boot_handoff_native`, `display13_boot_resource_native`, `dsi_aperture_adapter` | Same wired port, matching or incompatible stream. Same GPU base, initial linear or subsequent tiled owner. Partial last page must belong to the pool and BAR. | Workloop adoption, actual mode decision, donor comparator and plane setup, accelerator layout producer and destroy, exact-length descriptor and balanced references. `dsi_aperture_adapter_native` returns the actual stolen-pool slot with a peer slot active and a client still retaining the descriptor. AUX replies, allocation and register transitions are modeled. Physical panel and WindowServer output need separate evidence. |
| `display13_boot_handoff` and `display13_boot_handoff_native` | Native DSC teardown can skip the sink or ignore a failed write. The next plain eDP link needs decompression off before training. An unreadable DSC register permits writing zero only on a direct panel, with the source stopped and an AUX ACK. | Physical Combo-panel adoption owns the next stopped plain-link DSC check independently of fastset eligibility. Source expiry, config/lock/alignment loss, AUX failure, ownership loss and a port stopped before comparison retain that duty. A stable firmware CMTG A secondary on a single internal eDP A may remain enabled when the source scanout and DSC blocks have stopped and the receiver positively advertises no DSC. Tests retain the stop requirement for an unknown or DSC-capable receiver. A fresh post-stop capability read prevents optional DSC access on non-supporting sinks; unknown identity refuses training without writing. Native DSC training retains its own consumer and the plain-link duty. The full-mode decision reaches the production training wrapper. Native mode also replays the final connector dispatch in `hwSetMode`, patched `LightUpEDP`, `disableDisplay`, sink DSC writes, and the native port and Combo clock bodies through their production adapters. It checks failure before scanout, ordered shutdown, restored power reference counts and clock allocation, a live peer PLL, and retry through the scanout and brightness calls. The fixture models MMIO completion, power callback environment, AUX replies and electrical training. |
| `display13_clock_runtime.py` | Cold CDCLK has no live consumers; all powered planes/cursors/DSB/transcoders must be stopped under the display owner lock and IRQ guard. A caller-owned FB mutex must not wait for a potentially dependent workloop gate | Actual dual-clock dispatcher, IRQ guard and clock state machine with MMIO/mailbox/locks modeled. Gate contention, clock publication, no-write refusals and partial-write IRQ containment are checked. Active-clock success certificates and real scheduler races are outside this fixture |
| `display13_panel_runtime.py` | Fixed donor `LightUpEDP` powers the panel before clock setup/training. Linux `intel_pps.c` and CNP PWM use PCH rawclk, independent of CDCLK | Actual panel power/brightness wrappers run with CDCLK stopped or running, retain PG1 and owner/fault guards. Native mode replays patched `LightUpEDP` into the real power wrapper; clock/training leaves are mocked there. Physical PPS timing, brightness and panel link remain unqualified |
| `provider_binding.py` | Physical owner/ABI identity, immutable binding lifetime, port record ownership and semantic transport classification | Complete Compat translation unit; preserves physical ID/spoof and ABI1 history, pinning/idempotence and foreign/stale rejection. Replaces a mirrored capability truth table and tuple-bit rejection loop with consumer capability checks and named semantic violations/positive flag variation. Does not model arbitrary kernel scheduling |
| `profile_admission.py` | Physical PCI family classifications from Linux `i915_pciids.h`, supported Darwin families and documented opt-outs; fixed mobile identities also preserve prior selections | Executes the complete production selector using real `Profile` values; checks selected backend/driver and noaccel behavior. Does not qualify physical fuses or native start |
| `xelp_video_irq_native` | Gen11+ shared bank1 DATA_VALID/W1C and locked bank snapshot (Linux v6.12 `intel_gt_irq.c`); fixed TGL donor event tables and class-enable mask writes | Installs the production parent bank owner, executes the exact native `processInterrupts` and `serviceInterrupts`, and runs the production timer/lifecycle wrappers on boundary models. Checks VCS masks 1/4/5, VECS and bank0 peers, delayed/stalled/foreign identities, late peer dispatch, native fuse-driven enumeration rejecting an absent foreign consumer, bounded quarantine/retry, mask restoration, timer delivery after detach/rebind, a retry crossing stop during forcewake, late bank0/bank1 IRQs during disable, and installation failure. Semantic mutants detect lost obligations, wrong or absent consumers, missing ACK, an unmasked storm, lost retry delivery, a disabled timer after rebind, retry/IRQ admission after stop, and acquisition of the native accelerator gate during lifecycle. The latter is forbidden by the native stop/GART-collector lock order; retry uses a private WEX loop. Lilu byte routing, electrical IRQ/mask behavior, workloop scheduling and GPU waiter/recovery results require hardware qualification; no completion is inferred from a timeout. |
| `adlp_video_route_native` | TGL GT2 (48 EU) and ADL-P/U (64 EU), both 6 L3 banks, with VCS masks 1, 4 and 5; invalid fuse words and mismatched donor bytes | Uses the production GT readout, admission and patch installer with a bounded Lilu stand-in. Runs original x86 blocks from the media fuse load through enumeration, system/media selection, ring preparation, scheduler binding and EL descriptor stores into RAM. Allocation, interrupts, stamp retirement and hardware execution are outside this replay. |
| `gen12_resource_cases.hpp`, `adlp_resources.cpp`, `tgl_gt2_urb.py` | Positive resource capacities and Gen12 SSEU bit meanings; Intel TGL PRM Vol. 4 and Linux `intel_sseu.c` | Separate EU/DSS/L3 populations and position permutations; native URB stores use independent expected capacities, including eight native subslices. Unlisted encodings are not automatically negative specifications |
| `accelerator_resources.py` | Explicit capacities, forcewake ownership/readout prerequisites, resource failure visibility and refusal of native probe | Complete production profile selection, qualification, reporting and probe on the same object. Readout acquisition and other installers are explicit fixture prerequisites; their producers and the remainder of native start are outside this check |
| `host_publication.py` | Loader callback deadline, actual consumer dependency roles, IOSurface getter fields and consumer-specific use | Production host dispatch plus real surface ABI setter. Includes missing notifications, long valid lists, caller read windows and independent getter corruption. Other installers and symbol lookup are modeled boundaries |
| `display13_power_dispatch.py` | Fixed framebuffer donor `c004fc1a`: Sleep exit owns DidWake, Wake entry owns DidPowerOn, Doze exit has no DidWake | Production native power wrapper, ownership check and common notifier together; every subscriber state/order without DSI. Hardware restore and donor leaves are modeled, not a kernel scheduler |
| `display13_wake_notifications.py` | The same donor notification ownership, subscriber paging activation, retry and reference balance | Direct notifier behavior. Its no-DSI case alone is not proof of production reachability |
| `dsi_update_dispatch.py` | DSI wrapper serialization, real notification completion, delivered paging state and retry without a second panel restart | Executes the real wrapper and notifier together. Panel stop/resume and shared restore generation are boundary models; notification success without delivery remains incomplete |
| DSI framebuffer depth (`dsi_presentation.py`, `dsi_native_mode.py`, `dsi_apple_adapter.py`) | Fixed donor `validateModeDepth` maps indices 0/1 to four-byte RGB8/RGB10; `getPixelInformation` supplies independent component masks and native `configurePlane` selects the corresponding plane format | Production mode request through presentation, current-mode/pixel callbacks during allocation, depth-only changes, transformed source reallocation and failed-change rollback. Detailed validation and mode enumeration expose maximum depth index 1; panel timing stays RGB8. Native mode requires `--donor` to replay real pixel descriptors and plane configuration; memory/string, scaler/color and packet-submission leaves are mocked. Actual CoreDisplay selection, GPU conversion, MMIO latch and dithering require hardware validation |
| `framebuffer_common.py` | Common installation precedes backend/native start; incomplete installation prevents native start; repeated entry does not add trampolines | Executes installers/start gate, including partial failure. Source spelling or symbol occurrence counts are not used as behavior expectations |
| `display_contract_adapter.py` | Explicit fixture capabilities and route-specific missing operations | Dependency bookkeeping, not proof that every capability producer is connected. A new production field cannot be silently auto-enabled |
| `released_physical_admission.py`, `released_topology.py` | Immutable earlier release inputs and assertions | Retains earlier positive selections/caller behavior independently of the current table. Does not make earlier negative inputs permanently unsupported |
| `test_runner_contract.py` | Missing required work fails, all modes are visible, failure stops execution, results cannot be overwritten | Exercises the actual runner's registration, omissions and stage handling |
| AUX parent/observer replays | Reference ownership, inaccessible MMIO and memory-only telemetry retention, including quiet training | Old fixture declarations and qualification have been updated without changing the reference-balance expectation. Added PG telemetry is not required to occupy old record indices |
| DKL and outer-ring replays | Linux coefficient tables and Gen12 PIPE_CONTROL bit meanings, respectively | Actual donor code runs with boundary leaves. Outer-ring comparison uses original bytes as baseline, not a candidate with one bit cleared |

Compat's fixed donor identity is
`c004fc1ac9ee4157e2e12736f40fa6639bde025a279326beeb9dd48c9b445731`.
Its `FBMemMgr_Init` at `0x42e18` produces the 18-page DSB size, independently
of observed machines. Native start at `0x3f903..0x3f938` produces a 1/8 MiB
PTE window at BAR0+8 MiB and records its extent at controller+CEC. The DSB
caller at `0x4050f..0x40534` requires zero success and then maps the requested
GGTT subrange. Tests check every PTE and neighboring word, zeroed backing,
publication after validation, failure release and retry. The final complete
word belongs to a mapping; the donor's own off-by-one comparisons are not an
oracle overriding that memory extent contract.

Probe binding's 2/16/32 MiB variations test an honest map/manager pair, not new
native hardware support. Per-register read bounds determine probe readiness;
the observed 16 MiB map size is not a probe ABI requirement. The donor's nine
records and fixed class-layout offsets remain ABI guards. Generic Display12
register/DSB access remains separate from Display13 binding. Explicit-base
64-bit access preserves native manager dispatch for MMIO and direct stores for
other bases; the caller still owns the external allocation's actual extent.
The builder checks defined global symbols against the donor's eight retained
imports and the current/ABI1 WEX binding exports, as well as the existing bundle compatibility floor. Synthetic plist
unit cases alone do not establish loadability or full ABI correctness.

The resource fixture distinguishes a retained raw readout from a synthetic
encoding of a capacity. A patched driver field is not a physical fuse value.
Resource count formulas copied from the decoder are not acceptance oracles.
Sanitizers, explicit invalid-input checks and positive history remain separate
protections; removing a mirrored acceptance formula does not remove them.
The obsolete L3 data-bypass candidate check was removed: it required a policy
that is absent from current production. Unreferenced transmitter fixture copies
were also removed; current transmitter, mode, PHY-gating and AUX-lifetime replays
retain those active contracts. Neither deletion changes a runtime admission rule.

Useful primary references include
[Linux v6.12 SSEU](https://github.com/torvalds/linux/blob/v6.12/drivers/gpu/drm/i915/gt/intel_sseu.c)
and [PCI classifications](https://github.com/torvalds/linux/blob/v6.12/include/drm/i915_pciids.h).
These sources specify hardware facts, not Apple private ABI compatibility.

### Display13 deferred IRQ, GGTT resume and AUX backlight

`display13_irq_rearm` executes the production enable/disable/VBL wrappers and
real IRQ bank logic. The donor calls VBL after PIPECONF (0x49193/0x491ad).
Disabled pipes defer without permanent fault, then rearm on actual activation;
quiescing, blocked pipes and foreign owners cannot arm interrupts. Association
validation and kernel lock primitives are modeled leaves, not GPU IRQ timing.
Combo DP/HDMI, TC DP-alt, eDP plus external, and DSI plus external also resume
in two stages across pipes A/B/C. A later peer must preserve pending pipe/DSB
completions and peer masks; both native lock conventions execute. Replacing
incremental activation with a global rearm must fail at that external effect.
`display13_shared_restore` executes the actual shared restore wrapper and stopped
consumer checks. Power-well restore/publication are modeled leaves. Linux v6.12
`intel_dpt_configure` specifies GGTT selection. No engine enable may occur after
unreadable/failed GGTT readback or with active consumers; pending state survives.
Retry keeps the lost-power generation for normal and DSI transcoder bindings.
A retained, running engine accepts peer wake without reprogramming GGTT or
re-enabling the engine, even when a new GGTT transaction would fail.

`display13_panel_runtime` now covers VBT-selected VESA AUX, the PPS wrapper,
brightness/enable/disable callbacks and real PG/AUX leases. Native AUX replies
and serialization are modeled; `display13_aux` separately tests the transport.
The native mode executes `processDisplay13Panel` against the exact donor and
replays its generated period-call bridge in LightUpEDP, with the real outer
LightUpEDP wrapper and health result. It retains original-donor counterexamples,
checks partial installation/mismatched bytes, and restores a lost period on the
existing PWM path as well as exercising AUX. Common native panel installers
remain explicit prerequisites; patcher memory writes/routes and OS locks are
modeled. The test must not assemble a substitute period bridge.
Linux DRM eDP capability, byte ordering and PWMGEN bit count define the level
oracle. 8/16-bit sinks, AUX/pin enable, zero PWM availability, transaction failure,
foreign owner, power-off and restoration preserve normalized brightness without
writing absent PWM registers. `display13_panel` retains PWM-only callers and
adds AUX panel wiring for Combo A/B across Display13 families. Its former
PWM-absent rejection becomes a positive AUX-probe case; unknown VBT backlight
facts remain rejected. OLED-specific nits calibration and physical panel
brightness are not demonstrated by any CPU mode. Require these modes and the
native panel/AUX modes when changing this path.

Shared firmware identity checks also run inline/external capture and cached facts
for TGL, ADL/RPL-S, ADL/RPL-P and ADL-N. Consumers follow their physical mapping:
TGL internal eDP stays on the native panel route, and ADL-S HDMI-B is TC1 rather
than Combo-B. Optional panel damage must preserve external HDMI wiring. The
ADL/RPL-S PWM replay preserves level/polarity and native non-panel delegation;
entering a Display13 helper in that fixture fails. These are CPU routing and
lifecycle protections, not new Display12 AUX support or hardware qualification.

For non-eDP regression isolation, `display13_panel_runtime_native` additionally
calls the real eDP installer with DP-only, HDMI-only and DSI-plus-external wiring
while stale panel firmware facts remain present. Neither donor bytes nor common
panel hook setup may change. Removing the non-eDP guard must fail at this no-write
boundary. The existing Display13 PWM branch also makes no AUX calls and preserves
the modeled sink. `profile_admission` and `framebuffer_common[_native]` separately
protect Display12 backend selection and installation dispatch; their combination
is not a full kernel startup replay.
