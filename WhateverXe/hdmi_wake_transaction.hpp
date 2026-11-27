#pragma once
#include "hdmi_mmio_guard.hpp"
#include "hdmi_wake_plan.hpp"
namespace HdmiWake {
// Offline composition only. No MMIO access or hardware authorization.
struct Snapshot { size_t length, offset; bool powered; uint32_t value; };
inline bool prepare(const Snapshot &s, uint32_t mask, uint32_t bits, Change &out) {
    return HdmiMmio::readableSnapshot(s.length,s.offset,s.powered,s.value)
        && plan(s.value,mask,bits,out);
}
inline bool recover(const Snapshot &before, const Snapshot &now,
                    const Change &c, uint32_t &out) {
    if (before.length != now.length || before.offset != now.offset ||
        before.value != c.original ||
        !HdmiMmio::readableSnapshot(before.length,before.offset,before.powered,before.value) ||
        !HdmiMmio::readableSnapshot(now.length,now.offset,now.powered,now.value))
        return false;
    return restore(c,now.value,out);
}
}
