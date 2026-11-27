// Native HDMI audio payload preparation; no IOKit, hooks, MMIO or codec writes.
// Inspired by Julian Buhagiar (@jkbuha), WhateverXe-contrib commit
// 94b8fb60da84079d33e33ace2134d4a9d28cc88a (BSD-3-Clause; see upstream import).
// Wire layouts cross-checked against Linux DRM ELD and HDMI InfoFrame definitions.
// This standalone contract is not yet wired to the kernel audio path.
#ifndef KERN_HDMI_AUDIO_PAYLOAD_HPP
#define KERN_HDMI_AUDIO_PAYLOAD_HPP

#include <stddef.h>
#include <stdint.h>

namespace HDMIAudioPayload {
struct Eld {
    uint8_t bytes[84] {};
    size_t length {};
};

inline bool checksumValid(const uint8_t *block) {
    unsigned sum = 0;
    for (size_t i = 0; i < 128; ++i)
        sum += block[i];
    return (sum & 0xffU) == 0;
}

// Require a complete EDID and an explicit HDMI VSDB plus a usable LPCM SAD.
// Never publish a partial ELD if a later extension is malformed. This first
// native-HDMI contract intentionally does not synthesize SADs from Basic Audio.
inline Eld buildEld(const uint8_t *edid, size_t size) {
    static constexpr uint8_t magic[] {0, 255, 255, 255, 255, 255, 255, 0};
    if (!edid || size < 256 || size != (size_t(edid[126]) + 1) * 128)
        return {};
    for (size_t i = 0; i < sizeof(magic); ++i)
        if (edid[i] != magic[i])
            return {};
    for (size_t off = 0; off < size; off += 128)
        if (!checksumValid(edid + off))
            return {};

    uint8_t sad[45] {};
    unsigned count = 0, revision = 0, speakers = 0;
    bool hdmi = false, pcm = false;
    for (size_t off = 128; off < size; off += 128) {
        const auto *cta = edid + off;
        if (cta[0] != 2)
            continue;
        if (cta[1] < 3 || cta[1] > 7)
            return {};
        if (cta[1] > revision)
            revision = cta[1];
        const unsigned end = cta[2];
        if (!end)
            continue;
        if (end < 4 || end > 127)
            return {};
        for (unsigned i = 4; i < end;) {
            const unsigned tag = cta[i] >> 5, len = cta[i] & 31U;
            ++i;
            if (len > end - i)
                return {};
            if (tag == 1) {
                if (!len || len % 3 || count + len / 3 > 15)
                    return {};
                for (unsigned j = 0; j < len; j += 3) {
                    const auto *d = cta + i + j;
                    // Reject reserved bits or empty capabilities in LPCM SADs.
                    // A malformed descriptor must not become positive ELD evidence.
                    if (((d[0] >> 3) & 15U) == 1) {
                        if ((d[0] & 0x80U) || (d[1] & 0x80U) ||
                            (d[2] & 0xf8U) || !(d[1] & 0x7fU) || !(d[2] & 7U))
                            return {};
                        pcm = pcm || (d[0] & 7U) >= 1;
                    }
                    for (unsigned k = 0; k < 3; ++k)
                        sad[count * 3 + k] = d[k];
                    ++count;
                }
            } else if (tag == 3 && len >= 3) {
                hdmi = hdmi || (cta[i] == 3 && cta[i + 1] == 12 && cta[i + 2] == 0);
            } else if (tag == 4 && len >= 1) {
                speakers |= cta[i] & 0x7fU;
            }
            i += len;
        }
    }
    if (!hdmi || !pcm)
        return {};

    Eld result {};
    unsigned name = 0;
    for (unsigned off = 54; off <= 108; off += 18) {
        const auto *d = edid + off;
        if (d[0] || d[1] || d[2] || d[3] != 0xfc || d[4])
            continue;
        for (; name < 13 && d[5 + name] && d[5 + name] != 10; ++name)
            result.bytes[20 + name] = d[5 + name];
        while (name && result.bytes[19 + name] == ' ')
            result.bytes[20 + --name] = 0;
        break;
    }
    result.bytes[0] = 2U << 3;
    result.bytes[4] = uint8_t((revision << 5) | name);
    result.bytes[5] = uint8_t(count << 4); // HDMI connection type = 0, not DP.
    result.bytes[7] = uint8_t(speakers);
    for (unsigned i = 0; i < 4; ++i)
        result.bytes[16 + i] = edid[8 + i];
    for (unsigned i = 0; i < count * 3; ++i)
        result.bytes[20 + name + i] = sad[i];
    result.length = (20 + name + count * 3 + 3) & ~size_t(3);
    result.bytes[2] = uint8_t((result.length - 4) / 4);
    return result;
}

struct InfoFrame {
    uint8_t bytes[14] {};
    size_t length {};
};

// HDMI stereo LPCM, channel allocation 0, format details from stream.
// This is the logical HDMI packet (HB0..2, checksum, DB1..10), not the
// hardware-specific HDA DIP buffer layout. Refuse other channel counts until
// their speaker allocation and stream binding are implemented.
inline InfoFrame stereoInfoFrame(unsigned channels) {
    if (channels != 2)
        return {};
    InfoFrame result {};
    result.bytes[0] = 0x84;
    result.bytes[1] = 1;
    result.bytes[2] = 10;
    result.bytes[4] = 1;
    unsigned sum = 0;
    for (auto byte : result.bytes)
        sum += byte;
    result.bytes[3] = uint8_t(0U - sum);
    result.length = sizeof(result.bytes);
    return result;
}
// Offline admission model, not a hardware discovery or write interface.
// IDs and connection epochs must come from a separately verified mapping.
// A vendor ID alone, enumeration order or equal hda-gfx is not that mapping.
struct RouteEvidence {
    uint64_t connector {};
    uint64_t controller {};
    uint64_t epoch {};
    uint32_t codecId {};
    uint8_t codecAddress {};
    uint8_t transcoder {};
    bool nativeHdmi {};
    bool connected {};
    bool ownershipVerified {};
};

enum class RouteAdmission { rejected, unique };

inline RouteAdmission admitRoute(const RouteEvidence *candidates, size_t count,
                                 const RouteEvidence &expected) {
    if (!candidates || !count || count > 16 || !expected.connector ||
        !expected.controller || !expected.epoch ||
        (expected.codecId >> 16) != 0x8086U ||
        !(expected.codecId & 0xffffU) || expected.codecAddress > 15 ||
        expected.transcoder > 3 || !expected.nativeHdmi ||
        !expected.connected || !expected.ownershipVerified)
        return RouteAdmission::rejected;
    size_t matches = 0;
    for (size_t i = 0; i < count; ++i) {
        const auto &r = candidates[i];
        if (r.connector != expected.connector) {
            // A second live claim on the same transcoder is ambiguous.
            if (r.connected && r.transcoder == expected.transcoder)
                return RouteAdmission::rejected;
            continue;
        }
        if (r.controller != expected.controller || r.epoch != expected.epoch ||
            r.codecId != expected.codecId || r.codecAddress != expected.codecAddress ||
            r.transcoder != expected.transcoder || !r.nativeHdmi ||
            !r.connected || !r.ownershipVerified)
            return RouteAdmission::rejected;
        ++matches;
    }
    return matches == 1 ? RouteAdmission::unique : RouteAdmission::rejected;
}
} // namespace HDMIAudioPayload

#endif
