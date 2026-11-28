// Read-only AppleALC user-client adapter. Scalar protocol and verb encoding:
// acidanthera/AppleALC ff01db2, alc-verb/main.c and ALCUserClientProvider.cpp.
#include "../WhateverXe/hdmi_route_selection.hpp"
#include <CoreFoundation/CoreFoundation.h>
#include <IOKit/IOKitLib.h>
#include <cerrno>
#include <cstdio>
#include <cstdlib>
#include <cstdint>

static bool number(const char *s, uint64_t &value) {
    if (!s || *s < '0' || *s > '9') return false;
    char *end = nullptr;
    errno = 0;
    value = std::strtoull(s, &end, 0);
    return !errno && end != s && !*end;
}

static bool property(io_registry_entry_t service, CFStringRef key, unsigned &value) {
    CFTypeRef raw = IORegistryEntryCreateCFProperty(service, key, kCFAllocatorDefault, 0);
    if (!raw) return false;
    int64_t n = 0;
    const bool ok = CFGetTypeID(raw) == CFNumberGetTypeID() &&
        CFNumberGetValue(static_cast<CFNumberRef>(raw), kCFNumberSInt64Type, &n) &&
        n >= 0 && n <= UINT32_MAX;
    CFRelease(raw);
    if (ok) value = static_cast<unsigned>(n);
    return ok;
}

struct Reader {
    io_connect_t connection;
    unsigned address;
    bool get(unsigned cad, unsigned nid, unsigned verb, unsigned param, unsigned &out) {
        if (cad != address || nid > 127 || param > 255 ||
            (verb != 0xF00 && verb != 0xF01 && verb != 0xF02)) return false;
        uint64_t input[] {nid, verb == 0xF00 ? 0xFU : verb, param};
        uint64_t response = 0;
        uint32_t count = 1;
        if (IOConnectCallScalarMethod(connection, 0, input, 3, &response, &count) !=
            kIOReturnSuccess || count != 1 || response >= UINT32_MAX ||
            response == static_cast<uint32_t>(kIOReturnError)) return false;
        // AppleALC does not forward executeVerb's status. A zero response
        // cannot prove index zero on a pin with multiple connections.
        if (verb == 0xF01 && response == 0) return false;
        out = static_cast<unsigned>(response);
        return true;
    }
};

int main(int argc, char **argv) {
    uint64_t providerID = 0, pin = 0;
    if (argc != 3 || !number(argv[1], providerID) || !providerID ||
        !number(argv[2], pin) || !pin || pin > 127) {
        std::fprintf(stderr, "Usage: hdmi_codec_reader ALC_PROVIDER_REGISTRY_ID DISPLAY_PIN_NID\n");
        return 2;
    }
    auto provider = IOServiceGetMatchingService(kIOMainPortDefault, IORegistryEntryIDMatching(providerID));
    if (!provider) return 1;
    io_registry_entry_t codec = IO_OBJECT_NULL;
    io_connect_t connection = IO_OBJECT_NULL;
    unsigned address = 0, vendor = 0;
    const bool bound = IOObjectConformsTo(provider, "ALCUserClientProvider") &&
        IORegistryEntryGetParentEntry(provider, kIOServicePlane, &codec) == kIOReturnSuccess &&
        IOObjectConformsTo(codec, "IOHDACodecDevice") &&
        property(codec, CFSTR("IOHDACodecAddress"), address) && address <= 14 &&
        property(codec, CFSTR("IOHDACodecVendorID"), vendor) && (vendor >> 16) == 0x8086 &&
        IOServiceOpen(provider, mach_task_self(), 0, &connection) == kIOReturnSuccess;
    HdmiRoute::Route route {};
    HdmiRoute::PcmCaps caps {};
    Reader reader {connection, address};
    const bool found = bound && HdmiRoute::discover(reader, address, vendor,
        static_cast<unsigned>(pin), route, caps);
    if (connection) IOServiceClose(connection);
    if (codec) IOObjectRelease(codec);
    IOObjectRelease(provider);
    if (!found) {
        std::fprintf(stderr, "Display codec route unavailable or ambiguous.\n");
        return 1;
    }
    std::printf("vendor=0x%08x address=%u pin=%u converter=%u pcm=0x%x formats=0x%x\n",
                vendor, address, route.pin, route.converter, caps.ratesAndDepths, caps.formats);
    return 0;
}
