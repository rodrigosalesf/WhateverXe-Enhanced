# Upstream HDMI/DP audio reference import

Original implementation by **Julian Buhagiar (@jkbuha)**, from [WhateverXe-contrib](https://github.com/jkbuha/WhateverXe-contrib), commit [94b8fb60da84079d33e33ace2134d4a9d28cc88a](https://github.com/jkbuha/WhateverXe-contrib/commit/94b8fb60da84079d33e33ace2134d4a9d28cc88a). The upstream commit also credits Claude Opus 5.5 as co-author and cites Linux i915 and snd-hda-intel as technical references.

The original C++ and header are copied without modifications; LICENSE.txt retains the original BSD-3-Clause copyright and conditions. The integration.patch records the four remaining upstream file changes for review, not automatic application. This is a reference import only; it is not compiled or registered by WhateverXe Enhanced.

Upstream validation: Dell XPS 17 9720, GPU 0x46A6, iDisp codec 0x8086281C, macOS 26 with SimpleHDA, audible output over USB-C/DP and display sleep/wake. Upstream reports a reboot is required after display disconnect/reconnect.

Target: Acer Aspire A515-57, GPU 0x46A3, macOS Sequoia 15.8.3, native HDMI. Before enabling -wex-hdmi-audio, validate the codec identity, AppleHDA and framebuffer ABI/offsets, MMIO bounds and lifetime, native HDMI pin routing and HDMI (not DP) InfoFrame semantics, atomic hook installation and rollback. Keep activation opt-in and require host tests, Debug/Release builds and physical HDMI/video/Metal tests. No target-hardware validation is claimed. No endorsement by upstream is implied.

Base: RC2.6 diagnostics HEAD 022c91beae4443a3771034f26455dd1815500572. Existing PR #22 is unchanged.

## Enhanced offline route admission

The reference implementation chooses the first matching AppleHDAController and its first codec, and holds a single global EDID for writes to active transcoders. These assumptions are not carried into an active patch. The standalone `admitRoute` model requires explicitly verified connector/controller/codec identity, codec address, connection epoch, and a unique native HDMI transcoder claim. It rejects stale or conflicting claims, unverified ownership, non-Intel codec IDs and non-HDMI routes. The bounded CPU fixture uses synthetic identities; none establish the actual Acer codec, pin, transcoder, ownership or epoch source. No IOKit registration, hardware enumeration, codec commands, MMIO writes, or activation are added. The range 0–3 is the model's current admitted transcoder index range, not a verified target mapping.

## Stereo LPCM stream preparation

The standalone `prepareStereoPcmInfoFrame` checks the requested sample rate, sample depth and stereo channel count against a single explicit LPCM SAD in a structurally bounded HDMI ELD. It refuses malformed LPCM descriptors, cross-SAD capability combinations, unsupported formats, DP ELDs and malformed baselines. It emits a logical HDMI InfoFrame only; it does not select a codec, program a DIP buffer or authorize transmission. Independent implementation informed by the Linux HDA HDMI codec's per-pin capability and InfoFrame design (https://code.googlesource.com/linux/torvalds/linux/+/425af483523b76bc78e14674a430579d38b2a593/sound/pci/hda/patch_hdmi.c). No Linux code copied. The real connector's ELD and converter constraints remain unverified.

## Connector-scoped audio lifecycle

The standalone `LinkAudioSession` composes route admission, EDID-to-ELD and stereo payload validation. Connect, disconnect, mode change, suspend and resume revoke cached evidence and advance the local generation. Resume returns to disconnected until explicitly re-observed. Old-generation or unrelated-connector results cannot overwrite current evidence; a current invalid EDID or failed route revalidation revokes it. The caller must serialize operations, supply a verified connector identity and associate every observation with its acquisition epoch. Epochs are local to one non-copyable session; delayed callbacks must not outlive the session. The returned InfoFrame is a value, not an authorization for a later asynchronous hardware write. This model has no IOKit registration, hardware discovery, MMIO, codec commands or active suspend/resume hooks. Actual physical sleep/wake and reconnect remain pending.

## Bounded DIP buffer preparation

The independent `buildStereoDipImage` contract prepares an offline, zero-padded packet image within a 32-byte HDA byte-index window. It requires a caller-selected layout and reported capacity; neither can be inferred from the other's value. The full 14-byte logical HDMI frame and compact 9-byte representation (the meaningful bytes used by the reference Linux HDMI audio structure) are deliberately separate. Unknown layout, capacity outside its admitted bounds, corrupted frame, stale lifecycle or unsupported PCM produce no image. The compact form only omits known zero bytes. The resulting image does not establish actual hardware buffer capacity, auto-increment behavior, packet index ownership, DIP layout or transmit state. No hardware operation is performed. References: Linux HDA HDMI driver at 425af483523b76bc78e14674a430579d38b2a593, and Intel High Definition Audio Specification sections 7.3.3.36–7.3.3.39. No GPL source copied. The target must verify its layout and per-pin ownership before any adapter can write or restore data.

## Reference ABI audit on the Intel CI runner

An independent macOS 15 Intel job audits the public Sequoia framebuffer donor from WhateverXe-Graphics v0.4.5 at exact commit a558c561e06b2f78d675d16dd8f4303bf1c33fad. The downloaded file must match Git blob 74baffa1f0ba577ae1c22345fd6011c1ca2d3863 before inspection. It also attempts the standard AppleHDA and AppleHDAController paths on the CI host, recording the actual host version/build. The auditor reports only hashes, symbol outcomes and provenance; downloaded binaries remain temporary and no Apple binaries are uploaded, committed, installed or loaded. Unsupported/missing images and unmatched signatures remain explicit. Exit 1 is a negative/incomplete audit result rather than a successful ABI match. CI success means the audit executed, not that the target Acer or its exact loaded images were verified. No kernel activation is authorized.
