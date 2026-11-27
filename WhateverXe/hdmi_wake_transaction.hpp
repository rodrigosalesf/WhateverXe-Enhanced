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

// Register semantics cross-checked against Linux i915 intel_audio_regs.h.
// Experimental macOS wake approach credited to jkbuha/WhateverXe-contrib.
// These are plans only; powered must come from an independent audio lease.
constexpr size_t PinBufferOffset = 0x48414;
constexpr size_t CodecWakeOffset = 0x65f10;
constexpr uint32_t PinBufferMask = 1U << 31;
constexpr uint32_t CodecWakeMask = 1U << 15;
constexpr unsigned WakeMinimumDelayUs = 1000;
inline bool preparePinBuffer(const Snapshot &s, Change &out) {
    return s.offset == PinBufferOffset && prepare(s, PinBufferMask, PinBufferMask, out);
}
inline bool prepareCodecWake(const Snapshot &s, bool enable, Change &out) {
    return s.offset == CodecWakeOffset &&
        prepare(s, CodecWakeMask, enable ? CodecWakeMask : 0U, out);
}

// Backend contract: acquire/release serialize an independent audio power lease.
// update performs a verified masked RMW under that lease, preserving other bits.
// A failed update may have modified hardware; backend must quarantine on fault.
// No production backend is admitted here.
enum class WakeResult { Complete, Unavailable, Fault };
template<class Backend> WakeResult executeCodecWake(Backend &io, bool enable) {
    if (!io.acquire()) return WakeResult::Unavailable;
    bool ok = io.update(PinBufferOffset, PinBufferMask, PinBufferMask)
        && io.update(CodecWakeOffset, CodecWakeMask, 0U)
        && io.delay(WakeMinimumDelayUs);
    if (ok && enable)
        ok = io.update(CodecWakeOffset, CodecWakeMask, CodecWakeMask)
            && io.delay(WakeMinimumDelayUs);
    // Fault handling belongs to the lease owner, not a blind MMIO rollback.
    if (!ok) io.quarantine();
    const bool released = io.release();
    return ok && released ? WakeResult::Complete : WakeResult::Fault;
}
}
