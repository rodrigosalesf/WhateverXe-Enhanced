#include "../WhateverXe/hdmi_wake_plan.hpp"
#include <cassert>
int main() {
    HdmiWake::Change c {};
    uint32_t out = 0;
    assert(!HdmiWake::plan(0,0,0,c));
    assert(!HdmiWake::plan(0,1,2,c));
    assert(HdmiWake::plan(0xA0,3,1,c));
    assert(c.desired == 0xA1);
    assert(HdmiWake::restore(c,0xB1,out) && out == 0xB0);
    assert(!HdmiWake::restore(c,0xB2,out));
    assert(out == 0xB0);
}
