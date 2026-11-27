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
}
