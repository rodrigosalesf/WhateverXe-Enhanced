// Native HDMI audio payload preparation; no IOKit, hooks, MMIO or codec writes.
// Inspired by Julian Buhagiar (@jkbuha), WhateverXe-contrib commit
// 94b8fb60da84079d33e33ace2134d4a9d28cc88a (BSD-3-Clause; see upstream import).
// Wire layouts cross-checked against Linux DRM ELD and HDMI InfoFrame definitions.
// This standalone contract is not yet wired to the kernel audio path.
#ifndef KERN_HDMI_AUDIO_PAYLOAD_HPP
#define KERN_HDMI_AUDIO_PAYLOAD_HPP

#include "hdmi_route_selection.hpp"
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

// Require complete EDID and explicit HDMI VSDB. Basic Audio alone permits
// baseline stereo LPCM only when no audio descriptors are supplied.
// Never publish partial ELD or override explicit/malformed descriptors.
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
    bool hdmi = false, pcm = false, basicAudio = false;
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
        basicAudio = basicAudio || (cta[3] & 0x40U);
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
    if (!hdmi)
        return {};
    if (!count && basicAudio) {
        // CTA Basic Audio: 2-channel LPCM, 32/44.1/48 kHz, 16-bit.
        sad[0] = 0x09;
        sad[1] = 0x07;
        sad[2] = 0x01;
        count = 1;
        pcm = true;
    }
    if (!pcm)
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
// Require an explicit stereo LPCM rate/depth pair in ONE valid ELD SAD.
// This checks the supplied payload, not monitor presence or a live codec.
inline bool supportsStereoPcm(const Eld &eld, unsigned rate, unsigned bits) {
    if (eld.length < 20 || eld.length > sizeof(eld.bytes) ||
        (eld.length & 3U) || (eld.bytes[0] >> 3) != 2 ||
        size_t(eld.bytes[2]) * 4 + 4 != eld.length ||
        ((eld.bytes[5] >> 2) & 3U) != 0)
        return false;
    const unsigned name = eld.bytes[4] & 31U;
    const unsigned count = eld.bytes[5] >> 4;
    const unsigned start = 20 + name;
    if (name > 16 || start + count * 3 > eld.length)
        return false;
    constexpr unsigned rates[] {32000, 44100, 48000, 88200, 96000, 176400, 192000};
    unsigned rateMask = 0;
    for (unsigned i = 0; i < 7; ++i)
        if (rates[i] == rate)
            rateMask = 1U << i;
    const unsigned depthMask = bits == 16 ? 1U : bits == 20 ? 2U : bits == 24 ? 4U : 0U;
    if (!rateMask || !depthMask)
        return false;
    bool supported = false;
    for (unsigned i = 0; i < count; ++i) {
        const auto *d = eld.bytes + start + i * 3;
        if (((d[0] >> 3) & 15U) != 1)
            continue;
        if ((d[0] & 0x80U) || (d[1] & 0x80U) || (d[2] & 0xf8U) ||
            !(d[1] & 0x7fU) || !(d[2] & 7U))
            return false;
        if ((d[0] & 7U) >= 1 && (d[1] & rateMask) && (d[2] & depthMask))
            supported = true;
    }
    return supported;
}

inline InfoFrame prepareStereoPcmInfoFrame(const Eld &eld, unsigned rate,
                                           unsigned bits, unsigned channels) {
    if (channels != 2 || !supportsStereoPcm(eld, rate, bits))
        return {};
    return stereoInfoFrame(channels);
}

// Offline packet-0 image for the HDA DIP byte-index window (5 bits).
// A live adapter must independently establish the target codec's layout and
// reported capacity. In particular, do not infer the layout from size alone.
enum class DipLayout { unknown, fullHdmi14, compactHdmi9 };

struct DipImage {
    uint8_t bytes[32] {};
    size_t length {};
};

inline DipImage buildStereoDipImage(const InfoFrame &frame, DipLayout layout,
                                   size_t capacity) {
    // Only the exact stereo LPCM frame produced by this contract is admitted.
    // Both encodings retain its checksum; bytes omitted by compact layout are 0.
    const auto expected = stereoInfoFrame(2);
    if (frame.length != expected.length)
        return {};
    for (size_t i = 0; i < expected.length; ++i)
        if (frame.bytes[i] != expected.bytes[i])
            return {};

    size_t required = 0;
    switch (layout) {
        case DipLayout::fullHdmi14:
            required = 14;
            break;
        case DipLayout::compactHdmi9:
            required = 9;
            break;
        default:
            return {};
    }
    DipImage image {};
    if (capacity < required || capacity > sizeof(image.bytes))
        return {};
    // The bounded image is zero-padded so old packet tail bytes are not reused.
    // This is a desired image, not a sequence of hardware commands.
    for (size_t i = 0; i < required; ++i)
        image.bytes[i] = frame.bytes[i];
    image.length = capacity;
    return image;
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
        !(expected.codecId & 0xffffU) || expected.codecAddress > 14 ||
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
// One connector, externally serialized by its future owner. No callbacks,
// hardware IO or persistence. Tokens are meaningful only within this object.
enum class LinkEvent { connect, disconnect, modeChange, suspend, resume };
enum class LinkState { disconnected, connected, suspended, exhausted };

class LinkAudioSession {
    const uint64_t connector_;
    uint64_t epoch_ {};
    LinkState state_ {LinkState::disconnected};
    RouteEvidence route_ {};
    Eld eld_ {};

    void revoke() {
        route_ = {};
        eld_ = {};
    }

public:
    explicit LinkAudioSession(uint64_t connector) : connector_(connector) {}
    LinkAudioSession(const LinkAudioSession &) = delete;
    LinkAudioSession &operator=(const LinkAudioSession &) = delete;

    uint64_t epoch() const { return epoch_; }
    LinkState state() const { return state_; }
    bool hasEvidence() const { return eld_.length != 0; }

    bool transition(LinkEvent event) {
        if (!connector_ || state_ == LinkState::exhausted)
            return false;
        LinkState next = state_;
        switch (event) {
            case LinkEvent::connect:
                if (state_ == LinkState::suspended)
                    return false;
                next = LinkState::connected;
                break;
            case LinkEvent::disconnect:
                if (state_ == LinkState::suspended)
                    return false;
                next = LinkState::disconnected;
                break;
            case LinkEvent::modeChange:
                if (state_ != LinkState::connected)
                    return false;
                break;
            case LinkEvent::suspend:
                next = LinkState::suspended;
                break;
            case LinkEvent::resume:
                if (state_ != LinkState::suspended)
                    return false;
                // Resume alone is not proof of the previous connection.
                next = LinkState::disconnected;
                break;
            default:
                return false;
        }
        revoke();
        if (epoch_ == UINT64_MAX) {
            state_ = LinkState::exhausted;
            return false;
        }
        ++epoch_;
        state_ = next;
        return true;
    }

    // The caller must capture the epoch at acquisition, not completion.
    // Stale results must not replace or revoke current-generation evidence.
    bool observe(const RouteEvidence &expected, const RouteEvidence *candidates,
                 size_t count, const uint8_t *edid, size_t size) {
        if (state_ != LinkState::connected || expected.epoch != epoch_ ||
            expected.connector != connector_)
            return false;
        revoke();
        if (admitRoute(candidates, count, expected) != RouteAdmission::unique)
            return false;
        const auto payload = buildEld(edid, size);
        if (!payload.length)
            return false;
        route_ = expected;
        eld_ = payload;
        return true;
    }

    InfoFrame prepare(uint64_t acquisitionEpoch, const RouteEvidence *candidates,
                      size_t count, unsigned rate, unsigned bits, unsigned channels) {
        if (state_ != LinkState::connected || acquisitionEpoch != epoch_ || !hasEvidence())
            return {};
        if (admitRoute(candidates, count, route_) != RouteAdmission::unique) {
            revoke();
            return {};
        }
        return prepareStereoPcmInfoFrame(eld_, rate, bits, channels);
    }

    DipImage prepareDip(uint64_t acquisitionEpoch, const RouteEvidence *candidates,
                        size_t count, unsigned rate, unsigned bits, unsigned channels,
                        DipLayout layout, size_t capacity) {
        return buildStereoDipImage(prepare(acquisitionEpoch, candidates, count,
                                           rate, bits, channels), layout, capacity);
    }

    // The serialized owner supplies a reader bound to this controller and
    // connector generation, and a pin independently mapped to the display.
    template<class Reader>
    DipImage prepareCodecDip(Reader &reader, uint64_t acquisitionEpoch,
                             const RouteEvidence *candidates, size_t count,
                             unsigned pin, unsigned rate, unsigned bits,
                             DipLayout layout, size_t capacity) {
        const auto image = prepareDip(acquisitionEpoch, candidates, count, rate, bits,
                                      2, layout, capacity);
        if (!image.length)
            return {};
        HdmiRoute::Route selected {};
        HdmiRoute::PcmCaps pcm {};
        if (!HdmiRoute::discover(reader, route_.codecAddress, route_.codecId,
                                 pin, selected, pcm))
            return {};
        // HDA supported PCM rates occupy bits 0..11 starting at 8 kHz.
        constexpr unsigned rates[] {8000, 11025, 16000, 22050, 32000, 44100,
                                    48000, 88200, 96000, 176400, 192000, 384000};
        unsigned rateMask = 0;
        for (unsigned i = 0; i < sizeof(rates) / sizeof(rates[0]); ++i)
            if (rates[i] == rate)
                rateMask = 1U << i;
        const unsigned depthMask = bits == 16 ? 1U << 17 :
                                   bits == 20 ? 1U << 18 : 1U << 19;
        unsigned widget = 0;
        if (!(pcm.ratesAndDepths & rateMask) || !(pcm.ratesAndDepths & depthMask) ||
            !reader.get(selected.address, selected.converter, 0xF00, 9, widget) ||
            widget == 0xFFFFFFFFU || !(widget & 1U))
            return {};
        return image;
    }

};
} // namespace HDMIAudioPayload

#endif
