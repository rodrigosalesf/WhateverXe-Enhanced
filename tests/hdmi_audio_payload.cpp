#include "kern_hdmi_audio_payload.hpp"
#include <cassert>
#include <cstdio>
#include <cstring>

using namespace HDMIAudioPayload;

static void checksum(uint8_t *block) {
    unsigned sum = 0;
    for (unsigned i = 0; i < 127; ++i)
        sum += block[i];
    block[127] = uint8_t(0U - sum);
}
static void fixture(uint8_t *edid) {
    memset(edid, 0, 256);
    memset(edid + 1, 255, 6);
    edid[8] = 0x12;
    edid[9] = 0x34;
    edid[10] = 0x56;
    edid[11] = 0x78;
    edid[54 + 3] = 0xfc;
    memcpy(edid + 54 + 5, "Test \n", 6);
    edid[126] = 1;
    // CTA rev3: LPCM stereo, rates 32/44.1/48 kHz, 16-bit;
    // HDMI OUI and speaker allocation FL/FR.
    const uint8_t cta[] {2, 3, 14, 0x40, 0x23, 0x09, 0x07, 0x01,
                         0x63, 0x03, 0x0c, 0, 0x81, 1};
    memcpy(edid + 128, cta, sizeof(cta));
    checksum(edid);
    checksum(edid + 128);
}

int main() {
    uint8_t edid[384] {};
    fixture(edid);
    const auto e = buildEld(edid, 256);
    // Independent expected wire bytes: ELD v2, baseline length 6 dwords,
    // CEA rev3, name length 4, one SAD, HDMI connection, FL/FR.
    const uint8_t expected[] {0x10, 0, 6, 0, 0x64, 0x10, 0, 1,
                              0, 0, 0, 0, 0, 0, 0, 0,
                              0x12, 0x34, 0x56, 0x78,
                              'T', 'e', 's', 't', 9, 7, 1, 0};
    assert(e.length == sizeof(expected));
    assert(memcmp(e.bytes, expected, sizeof(expected)) == 0);
    assert(!buildEld(nullptr, 256).length);
    assert(!buildEld(edid, 255).length);
    assert(!buildEld(edid, 384).length);
    edid[140] ^= 1;
    assert(!buildEld(edid, 256).length);
    fixture(edid);
    edid[130] = 10; // vendor block crosses CTA collection boundary
    checksum(edid + 128);
    assert(!buildEld(edid, 256).length);
    fixture(edid);
    edid[137] = 4; // wrong HDMI OUI
    checksum(edid + 128);
    assert(!buildEld(edid, 256).length);
    fixture(edid);
    edid[133] = 0x11; // non-LPCM descriptor, despite Basic Audio
    checksum(edid + 128);
    assert(!buildEld(edid, 256).length);
    // Reserved bits or empty rate/depth fields in LPCM are invalid.
    const uint8_t invalidLpcm[][3] {
        {0x89, 7, 1}, {9, 0x87, 1}, {9, 7, 0x81},
        {9, 0, 1}, {9, 7, 0}
    };
    for (const auto &sad : invalidLpcm) {
        fixture(edid);
        memcpy(edid + 133, sad, sizeof(sad));
        checksum(edid + 128);
        assert(!buildEld(edid, 256).length);
    }
    fixture(edid);
    edid[133] = 8; // mono LPCM does not qualify for stereo preparation
    checksum(edid + 128);
    assert(!buildEld(edid, 256).length);
    fixture(edid);
    edid[135] = 4; // valid 24-bit LPCM remains admissible
    checksum(edid + 128);
    assert(buildEld(edid, 256).length == sizeof(expected));

    fixture(edid);
    edid[132] = 0x22; // malformed two-byte SAD
    checksum(edid + 128);
    assert(!buildEld(edid, 256).length);
    fixture(edid);
    edid[0] = 1;
    checksum(edid);
    assert(!buildEld(edid, 256).length);
    fixture(edid);
    edid[126] = 2;
    checksum(edid);
    edid[256] = 0x70; // other valid extension must not invalidate CTA
    checksum(edid + 256);
    assert(buildEld(edid, 384).length == sizeof(expected));
    edid[257] ^= 1; // later invalid checksum must revoke positive evidence
    assert(!buildEld(edid, 384).length);
    memset(edid + 256, 0, 128);
    edid[256] = 2;
    edid[257] = 3;
    edid[258] = 3; // malformed later CTA despite earlier valid audio
    checksum(edid + 256);
    assert(!buildEld(edid, 384).length);

    const uint8_t packet[] {0x84, 1, 10, 0x70, 1, 0, 0, 0, 0, 0, 0, 0, 0, 0};
    const auto frame = stereoInfoFrame(2);
    assert(frame.length == sizeof(packet));
    assert(memcmp(frame.bytes, packet, sizeof(packet)) == 0);
    for (unsigned channels = 0; channels <= 16; ++channels)
        if (channels != 2)
            assert(!stereoInfoFrame(channels).length);
    // Stream parameters must be supported by a single valid LPCM SAD.
    assert(prepareStereoPcmInfoFrame(e, 48000, 16, 2).length == sizeof(packet));
    assert(!prepareStereoPcmInfoFrame(e, 96000, 16, 2).length);
    assert(!prepareStereoPcmInfoFrame(e, 48000, 24, 2).length);
    assert(!prepareStereoPcmInfoFrame(e, 48000, 16, 6).length);
    assert(!prepareStereoPcmInfoFrame(e, 48000, 32, 2).length);
    Eld invalid = e;
    invalid.bytes[5] |= 4; // DP instead of HDMI.
    assert(!supportsStereoPcm(invalid, 48000, 16));
    invalid = e;
    invalid.bytes[2] -= 1;
    assert(!supportsStereoPcm(invalid, 48000, 16));
    invalid = e;
    invalid.bytes[5] = 0xf0; // SAD list exceeds baseline.
    assert(!supportsStereoPcm(invalid, 48000, 16));
    invalid = e;
    invalid.length = 85;
    assert(!supportsStereoPcm(invalid, 48000, 16));

    // Two SADs: 44.1 kHz/16-bit, 48 kHz/24-bit. Never combine fields.
    Eld split {};
    split.length = 28;
    split.bytes[0] = 0x10;
    split.bytes[2] = 6;
    split.bytes[4] = 0x60;
    split.bytes[5] = 0x20;
    const uint8_t splitSads[] {9, 2, 1, 9, 4, 4};
    memcpy(split.bytes + 20, splitSads, sizeof(splitSads));
    assert(supportsStereoPcm(split, 44100, 16));
    assert(supportsStereoPcm(split, 48000, 24));
    assert(!supportsStereoPcm(split, 48000, 16));
    assert(!supportsStereoPcm(split, 44100, 24));
    split.bytes[25] = 0x84; // Malformed later LPCM invalidates prior evidence.
    assert(!supportsStereoPcm(split, 44100, 16));

    // Synthetic IDs only: no claim that these describe the Acer.
    const RouteEvidence route {1, 7, 3, 0x8086281c, 2, 1, true, true, true};
    RouteEvidence candidates[] {route, route};
    assert(admitRoute(candidates, 1, route) == RouteAdmission::unique);
    assert(admitRoute(candidates, 2, route) == RouteAdmission::rejected);
    assert(admitRoute(nullptr, 1, route) == RouteAdmission::rejected);
    assert(admitRoute(candidates, 0, route) == RouteAdmission::rejected);
    assert(admitRoute(candidates, 17, route) == RouteAdmission::rejected);
    candidates[1].connector = 2;
    assert(admitRoute(candidates, 2, route) == RouteAdmission::rejected);
    candidates[1].transcoder = 2;
    assert(admitRoute(candidates, 2, route) == RouteAdmission::unique);
    candidates[1].transcoder = 1;
    candidates[1].connected = false;
    assert(admitRoute(candidates, 2, route) == RouteAdmission::unique);
    candidates[0].epoch = 2;
    assert(admitRoute(candidates, 1, route) == RouteAdmission::rejected);
    candidates[0] = route;
    candidates[0].codecId = 0x10ec0256;
    assert(admitRoute(candidates, 1, route) == RouteAdmission::rejected);
    candidates[0] = route;
    candidates[0].controller = 8;
    assert(admitRoute(candidates, 1, route) == RouteAdmission::rejected);
    candidates[0] = route;
    candidates[0].ownershipVerified = false;
    assert(admitRoute(candidates, 1, route) == RouteAdmission::rejected);
    candidates[0] = route;
    candidates[0].nativeHdmi = false;
    assert(admitRoute(candidates, 1, route) == RouteAdmission::rejected);
    candidates[0] = route;
    candidates[0].codecAddress = 3;
    assert(admitRoute(candidates, 1, route) == RouteAdmission::rejected);
    candidates[0] = route;
    candidates[0].connected = false;
    assert(admitRoute(candidates, 1, route) == RouteAdmission::rejected);
    auto invalidExpected = route;
    invalidExpected.codecId = 0x10ec0256;
    assert(admitRoute(candidates, 1, invalidExpected) == RouteAdmission::rejected);

    // Lifecycle tests use only the software session, never a live codec.
    LinkAudioSession session {route.connector};
    auto live = route;
    fixture(edid);
    assert(!session.observe(live, &live, 1, edid, 256));
    assert(!session.transition(LinkEvent::resume));
    assert(session.transition(LinkEvent::connect));
    live.epoch = session.epoch();
    const auto first = live;
    assert(session.observe(live, &live, 1, edid, 256));
    assert(session.hasEvidence());
    assert(session.prepare(live.epoch, &live, 1, 48000, 16, 2).length == sizeof(packet));
    assert(!session.prepare(live.epoch, &live, 1, 96000, 16, 2).length);
    assert(session.hasEvidence()); // Unsupported format does not invalidate EDID.
    assert(session.transition(LinkEvent::disconnect));
    assert(!session.hasEvidence());
    assert(!session.prepare(first.epoch, &first, 1, 48000, 16, 2).length);
    assert(session.transition(LinkEvent::connect));
    live.epoch = session.epoch();
    assert(!session.observe(first, &first, 1, edid, 256));
    assert(!session.hasEvidence());
    edid[134] = 2; // Reconnected sink advertises only 44.1 kHz.
    checksum(edid + 128);
    assert(session.observe(live, &live, 1, edid, 256));
    assert(!session.prepare(live.epoch, &live, 1, 48000, 16, 2).length);
    assert(session.prepare(live.epoch, &live, 1, 44100, 16, 2).length);
    assert(!session.observe(first, &first, 1, nullptr, 0));
    assert(session.hasEvidence());
    auto other = live;
    other.connector = 99;
    assert(!session.observe(other, &other, 1, nullptr, 0));
    assert(session.hasEvidence());
    auto conflict = live;
    conflict.controller += 1;
    assert(!session.prepare(live.epoch, &conflict, 1, 44100, 16, 2).length);
    assert(!session.hasEvidence());
    assert(!session.prepare(live.epoch, &live, 1, 44100, 16, 2).length);
    assert(session.observe(live, &live, 1, edid, 256));
    assert(!session.observe(live, &live, 1, nullptr, 0));
    assert(!session.hasEvidence());
    assert(session.observe(live, &live, 1, edid, 256));
    assert(session.transition(LinkEvent::modeChange));
    assert(!session.hasEvidence());
    assert(!session.observe(live, &live, 1, edid, 256));
    live.epoch = session.epoch();
    assert(session.observe(live, &live, 1, edid, 256));
    assert(session.transition(LinkEvent::suspend));
    assert(!session.hasEvidence());
    assert(!session.transition(LinkEvent::connect));
    assert(!session.observe(live, &live, 1, edid, 256));
    assert(session.transition(LinkEvent::resume));
    assert(session.state() == LinkState::disconnected);
    assert(!session.hasEvidence());
    assert(!session.transition(LinkEvent::modeChange));
    assert(session.transition(LinkEvent::connect));
    live.epoch = session.epoch();
    assert(session.observe(live, &live, 1, edid, 256));
    assert(session.prepare(live.epoch, &live, 1, 44100, 16, 2).length);
    LinkAudioSession unidentified {0};
    assert(!unidentified.transition(LinkEvent::connect));

    puts("PASS native HDMI ELD, stereo InfoFrame, route and lifecycle (CPU only).");
}
