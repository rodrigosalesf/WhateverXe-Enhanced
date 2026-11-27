#include "../WhateverXe/hdmi_route_selection.hpp"
#include <cassert>
using namespace HdmiRoute;
struct Reader {
    unsigned caps {0x210}, pcm {0x1A07F0}, formats {1}, fail {0};
    bool get(unsigned address, unsigned nid, unsigned verb, unsigned param, unsigned &out) {
        assert(address == 2 && nid == 3 && verb == 0xF00);
        if (param == fail) return false;
        out = param == 9 ? caps : param == 10 ? pcm : formats;
        return true;
    }
};
struct PinReader {
    unsigned length {2}, word {0x8503}, selection {2};
    bool get(unsigned address, unsigned nid, unsigned verb, unsigned param, unsigned &out) {
        assert(address == 2 && nid == 8);
        if (verb == 0xF00) out = param == 9 ? 0x400300 : length;
        else if (verb == 0xF02) out = word;
        else if (verb == 0xF01) out = selection;
        else return false;
        return true;
    }
};
int main() {
    PinReader pinReader;
    unsigned nodes[127] {};
    size_t count = 0, selected = 0;
    assert(readPinConnections(pinReader,2,8,nodes,count,selected));
    assert(count == 3 && selected == 2 && nodes[0] == 3 && nodes[2] == 5);
    pinReader.length = 0x82;
    pinReader.word = 0x80050003;
    assert(readPinConnections(pinReader,2,8,nodes,count,selected));
    pinReader.selection = 3;
    assert(!readPinConnections(pinReader,2,8,nodes,count,selected));
    pinReader.selection = 0;
    pinReader.word = 0x80020003;
    assert(!readPinConnections(pinReader,2,8,nodes,count,selected));
    assert(count == 3 && selected == 2);

    Reader reader;
    PcmCaps pcm {};
    Route route {2,4,3};
    assert(readSelectedPcm(reader,route,pcm) && pcm.ratesAndDepths == 0x1A07F0);
    reader.caps = 0x200;
    assert(!readSelectedPcm(reader,route,pcm));
    reader.caps = 0x210;
    reader.formats = 0;
    assert(!readSelectedPcm(reader,route,pcm));
    reader.formats = 1;
    reader.fail = 10;
    assert(!readSelectedPcm(reader,route,pcm));
    reader.fail = 0;
    reader.pcm = 0xFFFFFFFFU;
    assert(!readSelectedPcm(reader,route,pcm));

    unsigned edges[] {3,5};
    Widget w[] {{4,Kind::Pin,true,edges,1},{3,Kind::Converter,true,nullptr,0},
                {5,Kind::Converter,true,nullptr,0}};
    Codec c[] {{1,0x8086281C,2,w,3},{1,0x10EC0256,0,nullptr,0}};
    Route out {};
    assert(select(c,2,1,0x8086281C,4,out));
    assert(out.address == 2 && out.pin == 4 && out.converter == 3);
    w[0].count = 2;
    assert(!select(c,2,1,0x8086281C,4,out));
    w[0].selectionKnown = true;
    w[0].selectedIndex = 1;
    assert(select(c,2,1,0x8086281C,4,out) && out.converter == 5);
    w[0].selectedIndex = 2;
    assert(!select(c,2,1,0x8086281C,4,out));
    w[0].selectedIndex = 0;
    assert(select(c,2,1,0x8086281C,4,out) && out.converter == 3);
    w[0].selectionKnown = false;
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
