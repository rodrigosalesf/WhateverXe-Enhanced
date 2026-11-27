#include "../WhateverXe/hdmi_wake_transaction.hpp"
#include <cassert>
struct FakeBackend {
    unsigned calls {}, fail {}, delays {}, updates {};
    bool owned {}, quarantined {}, available {true};
    uint32_t pin {0x1234}, wake {0x8123};
    bool acquire() { owned = available; return owned; }
    bool update(size_t offset, uint32_t mask, uint32_t bits) {
        assert(owned);
        ++updates;
        if (++calls == fail) return false;
        assert(offset == HdmiWake::PinBufferOffset || offset == HdmiWake::CodecWakeOffset);
        auto &v = offset == HdmiWake::PinBufferOffset ? pin : wake;
        v = (v & ~mask) | bits;
        return true;
    }
    bool delay(unsigned us) {
        assert(owned && us == 1000);
        assert(wake == (delays == 0 ? 0x123U : 0x8123U));
        ++delays;
        return ++calls != fail;
    }
    void quarantine() { assert(owned); quarantined = true; }
    bool release() { assert(owned); owned = false; return true; }
};
int main() {
    using HdmiWake::executeCodecWake;
    using HdmiWake::WakeResult;
    FakeBackend good;
    assert(executeCodecWake(good,true) == WakeResult::Complete);
    assert(good.pin == 0x80001234U && good.wake == 0x8123U);
    assert(good.delays == 2 && good.updates == 3 && !good.owned);
    FakeBackend disable;
    assert(executeCodecWake(disable,false) == WakeResult::Complete);
    assert(disable.wake == 0x123U && disable.delays == 1);
    for (unsigned i=1;i<=5;++i) {
        FakeBackend fault;
        fault.fail=i;
        assert(executeCodecWake(fault,true) == WakeResult::Fault);
        assert(fault.quarantined && !fault.owned && fault.calls == i);
    }
    FakeBackend unavailable;
    unavailable.available=false;
    assert(executeCodecWake(unavailable,true) == WakeResult::Unavailable);
    assert(unavailable.calls == 0 && !unavailable.owned);

    using namespace HdmiWake;
    Snapshot before {8,4,true,0xA0}, now {8,4,true,0xB1};
    Change c {};
    uint32_t out = 0;
    assert(prepare(before,3,1,c));
    assert(recover(before,now,c,out) && out == 0xB0);
    now.powered = false;
    assert(!recover(before,now,c,out));
    now.powered = true;
    now.offset = 0;
    assert(!recover(before,now,c,out));
    now.offset = 4;
    now.value = 0xB2;
    assert(!recover(before,now,c,out));
    now.value = UINT32_MAX;
    assert(!recover(before,now,c,out));
    before.powered = false;
    assert(!prepare(before,3,1,c));
    assert(out == 0xB0);
    Snapshot pin {0x66000, PinBufferOffset, true, 0x1234};
    assert(preparePinBuffer(pin,c) && c.desired == 0x80001234U);
    assert(!prepareCodecWake(pin,true,c));
    Snapshot wake {0x66000, CodecWakeOffset, true, 0x8123};
    assert(prepareCodecWake(wake,false,c) && c.desired == 0x123U);
    wake.value = c.desired;
    assert(prepareCodecWake(wake,true,c) && c.desired == 0x8123U);
    assert(!preparePinBuffer(wake,c));
    wake.powered = false;
    assert(!prepareCodecWake(wake,true,c));
    pin.length = PinBufferOffset;
    assert(!preparePinBuffer(pin,c));
}
