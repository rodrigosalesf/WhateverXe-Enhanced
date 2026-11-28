#pragma once
#include <stdint.h>
namespace HdmiWake {
// Pure register transaction planning; no MMIO, no hardware offsets.
struct Change { uint32_t original, desired, mask; };
inline bool plan(uint32_t original, uint32_t mask, uint32_t bits, Change &out) {
    if (!mask || (bits & ~mask)) return false;
    out = {original, (original & ~mask) | bits, mask};
    return true;
}
// Reject concurrent changes to owned bits; preserve unrelated bits.
inline bool restore(const Change &c, uint32_t current, uint32_t &out) {
    if (!c.mask || ((current ^ c.desired) & c.mask)) return false;
    out = (current & ~c.mask) | (c.original & c.mask);
    return true;
}
}
