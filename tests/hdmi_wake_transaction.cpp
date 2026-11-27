#include "../WhateverXe/hdmi_wake_transaction.hpp"
#include <cassert>
int main() {
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
