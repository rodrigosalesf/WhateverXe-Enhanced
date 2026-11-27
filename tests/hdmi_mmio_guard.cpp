#include "../WhateverXe/hdmi_mmio_guard.hpp"
#include <cassert>
int main() {
    using namespace HdmiMmio;
    assert(validOffset(8,4));
    assert(!validOffset(3,0));
    assert(!validOffset(8,8));
    assert(!validOffset(8,1));
    assert(!validOffset(8,SIZE_MAX));
    assert(readableSnapshot(8,4,true,0));
    assert(!readableSnapshot(8,4,false,0));
    assert(!readableSnapshot(8,4,true,UINT32_MAX));
}
