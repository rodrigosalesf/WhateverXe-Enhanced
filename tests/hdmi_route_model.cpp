#include "../WhateverXe/hdmi_route_selection.hpp"
#include <cassert>
using namespace HdmiRoute;
int main() {
    unsigned edges[] {3,5};
    Widget w[] {{4,Kind::Pin,true,edges,1},{3,Kind::Converter,true,nullptr,0},
                {5,Kind::Converter,true,nullptr,0}};
    Codec c[] {{1,0x8086281C,2,w,3},{1,0x10EC0256,0,nullptr,0}};
    Route out {};
    assert(select(c,2,1,0x8086281C,4,out));
    assert(out.address == 2 && out.pin == 4 && out.converter == 3);
    w[0].count = 2;
    assert(!select(c,2,1,0x8086281C,4,out));
    w[0].count = 1;
    assert(!select(c,2,2,0x8086281C,4,out));
    assert(!select(c,2,1,0x10EC0256,4,out));
    c[0].address = 15;
    assert(!select(c,2,1,0x8086281C,4,out));
    c[0].address = 2;
    c[0].widgets = nullptr;
    c[1].widgets = w;
    c[1].count = 3;
    assert(!select(c,2,1,0x8086281C,4,out));
    c[0].widgets = w;
    w[0].kind = Kind::Other;
    assert(!select(c,2,1,0x8086281C,4,out));
    w[0].kind = Kind::Pin;
    edges[0] = 99;
    assert(!select(c,2,1,0x8086281C,4,out));
    assert(out.address == 2 && out.converter == 3);
}
