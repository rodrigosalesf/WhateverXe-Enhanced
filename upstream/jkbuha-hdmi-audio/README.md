# Upstream HDMI/DP audio reference import

Original implementation by **Julian Buhagiar (@jkbuha)**, from [WhateverXe-contrib](https://github.com/jkbuha/WhateverXe-contrib), commit [94b8fb60da84079d33e33ace2134d4a9d28cc88a](https://github.com/jkbuha/WhateverXe-contrib/commit/94b8fb60da84079d33e33ace2134d4a9d28cc88a). The upstream commit also credits Claude Opus 5.5 as co-author and cites Linux i915 and snd-hda-intel as technical references.

The original C++ and header are copied without modifications; LICENSE.txt retains the original BSD-3-Clause copyright and conditions. The integration.patch records the four remaining upstream file changes for review, not automatic application. This is a reference import only; it is not compiled or registered by WhateverXe Enhanced.

Upstream validation: Dell XPS 17 9720, GPU 0x46A6, iDisp codec 0x8086281C, macOS 26 with SimpleHDA, audible output over USB-C/DP and display sleep/wake. Upstream reports a reboot is required after display disconnect/reconnect.

Target: Acer Aspire A515-57, GPU 0x46A3, macOS Sequoia 15.8.3, native HDMI. Before enabling -wex-hdmi-audio, validate the codec identity, AppleHDA and framebuffer ABI/offsets, MMIO bounds and lifetime, native HDMI pin routing and HDMI (not DP) InfoFrame semantics, atomic hook installation and rollback. Keep activation opt-in and require host tests, Debug/Release builds and physical HDMI/video/Metal tests. No target-hardware validation is claimed. No endorsement by upstream is implied.

Base: RC2.6 diagnostics HEAD 022c91beae4443a3771034f26455dd1815500572. Existing PR #22 is unchanged.
