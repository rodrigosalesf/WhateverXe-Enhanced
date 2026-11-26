// Bounded, value-only flight recorder core. Not yet wired into kernel callbacks.
#ifndef kern_xelp_flight_recorder_hpp
#define kern_xelp_flight_recorder_hpp

#include <stddef.h>
#include <stdint.h>

namespace XELPFlightRecorder {

enum class Kind : uint8_t {
    MMIOFailure = 1,
    Timeout,
    ForceWake,
    Framebuffer,
    Recovery
};

struct Event {
    uint64_t sequence {};
    uint64_t timestamp {};
    Kind kind {};
};

// Single-owner/external-serialization contract. No internal locks, allocation,
// device access, clock calls, or I/O. Do not call from IRQ or concurrent contexts
// until the owning integration establishes the required synchronization.
template <size_t Capacity>
class Recorder {
    static_assert(Capacity > 0 && Capacity <= 1024, "bounded event capacity");
    Event events_[Capacity] {};
    size_t next_ {};
    size_t count_ {};
    uint64_t sequence_ {};
    uint64_t lastTimestamp_ {};
    bool enabled_ {};
    bool frozen_ {};

    static bool valid(Kind kind) {
        switch (kind) {
            case Kind::MMIOFailure:
            case Kind::Timeout:
            case Kind::ForceWake:
            case Kind::Framebuffer:
            case Kind::Recovery:
                return true;
            default:
                return false;
        }
    }

public:
    void reset(bool enable) {
        for (auto &event : events_)
            event = {};
        next_ = count_ = 0;
        sequence_ = lastTimestamp_ = 0;
        frozen_ = false;
        enabled_ = enable;
    }

    bool record(Kind kind, uint64_t timestamp) {
        if (!enabled_ || frozen_ || !valid(kind) ||
            sequence_ == UINT64_MAX ||
            (count_ != 0 && timestamp < lastTimestamp_))
            return false;

        events_[next_] = {++sequence_, timestamp, kind};
        lastTimestamp_ = timestamp;
        next_ = (next_ + 1) % Capacity;
        if (count_ < Capacity)
            ++count_;
        return true;
    }

    void freeze() {
        frozen_ = true;
    }

    size_t size() const {
        return count_;
    }

    uint64_t overwritten() const {
        return sequence_ - count_;
    }

    // Oldest-to-newest; copy values only. On failure, leave output unchanged.
    bool read(size_t index, Event &event) const {
        if (index >= count_)
            return false;
        const auto position = (next_ + Capacity - count_ + index) % Capacity;
        event = events_[position];
        return true;
    }
};

} // namespace XELPFlightRecorder

#endif
