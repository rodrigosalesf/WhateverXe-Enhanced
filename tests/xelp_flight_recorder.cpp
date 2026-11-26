#include "../WhateverXe/kern_xelp_flight_recorder.hpp"
#include <cassert>
#include <type_traits>

using namespace XELPFlightRecorder;

static void checkDisabledAndReset() {
    Recorder<3> recorder;
    Event event {};
    assert(!recorder.record(Kind::MMIOFailure, 10));
    assert(recorder.size() == 0 && recorder.overwritten() == 0);
    assert(!recorder.read(0, event));
    recorder.reset(true);
    assert(recorder.record(Kind::ForceWake, 10));
    assert(recorder.read(0, event));
    assert(event.sequence == 1 && event.kind == Kind::ForceWake && event.timestamp == 10);
    recorder.reset(false);
    assert(recorder.size() == 0 && !recorder.read(0, event));
    assert(!recorder.record(Kind::Recovery, 11));
    recorder.reset(true);
    assert(recorder.record(Kind::Recovery, 0));
    assert(recorder.read(0, event) && event.sequence == 1);
}

static void checkOverwriteAndOrdering() {
    Recorder<3> recorder;
    recorder.reset(true);
    assert(recorder.record(Kind::ForceWake, 1));
    assert(recorder.record(Kind::MMIOFailure, 2));
    assert(recorder.record(Kind::Timeout, 3));
    assert(recorder.overwritten() == 0);
    assert(recorder.record(Kind::Framebuffer, 4));
    assert(recorder.record(Kind::Recovery, 5));
    assert(recorder.size() == 3 && recorder.overwritten() == 2);
    Event event {};
    assert(recorder.read(0, event) && event.sequence == 3 && event.kind == Kind::Timeout);
    assert(recorder.read(1, event) && event.sequence == 4 && event.kind == Kind::Framebuffer);
    assert(recorder.read(2, event) && event.sequence == 5 && event.timestamp == 5);
    assert(!recorder.read(3, event));
    assert(event.sequence == 5);
}

static void checkFreeze() {
    Recorder<2> recorder;
    recorder.reset(true);
    assert(recorder.record(Kind::ForceWake, 1));
    assert(recorder.record(Kind::Timeout, 2));
    recorder.freeze();
    recorder.freeze();
    assert(!recorder.record(Kind::Recovery, 3));
    Event event {};
    assert(recorder.size() == 2 && recorder.overwritten() == 0);
    assert(recorder.read(1, event) && event.kind == Kind::Timeout && event.sequence == 2);
    recorder.reset(true);
    assert(recorder.record(Kind::Recovery, 3));
    assert(recorder.size() == 1 && recorder.read(0, event) && event.sequence == 1);
}

static void checkInvalidEvents() {
    Recorder<2> recorder;
    recorder.reset(true);
    assert(recorder.record(Kind::ForceWake, 10));
    assert(!recorder.record(Kind::Recovery, 9));
    assert(!recorder.record(static_cast<Kind>(0), 11));
    assert(!recorder.record(static_cast<Kind>(255), 11));
    assert(recorder.record(Kind::Recovery, 10));
    Event event {};
    assert(recorder.read(1, event) && event.sequence == 2 && event.timestamp == 10);
    assert(recorder.overwritten() == 0);
}

static void checkSingleSlotAndRepeatedWrap() {
    Recorder<1> one;
    one.reset(true);
    assert(one.record(Kind::Timeout, 0));
    assert(one.record(Kind::Recovery, 1));
    Event event {};
    assert(one.size() == 1 && one.overwritten() == 1);
    assert(one.read(0, event) && event.sequence == 2 && event.kind == Kind::Recovery);
    Recorder<7> many;
    many.reset(true);
    for (uint64_t i = 0; i < 10000; ++i)
        assert(many.record(Kind::Framebuffer, i));
    assert(many.size() == 7 && many.overwritten() == 9993);
    assert(many.read(0, event) && event.sequence == 9994 && event.timestamp == 9993);
    assert(many.read(6, event) && event.sequence == 10000 && event.timestamp == 9999);
}

int main() {
    static_assert(std::is_trivially_copyable<Event>::value, "value-only event");
    checkDisabledAndReset();
    checkOverwriteAndOrdering();
    checkFreeze();
    checkInvalidEvents();
    checkSingleSlotAndRepeatedWrap();
}
