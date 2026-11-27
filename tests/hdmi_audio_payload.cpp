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
    puts("PASS native HDMI ELD and stereo InfoFrame payloads (CPU only).");
}
