#include <cstdint>
#include <cstddef>
#include <cassert>

// Host-only prototype. No hardware access or kernel activation.
struct Widget {
    unsigned nid;
    bool digital;
    bool converter;
};
struct Codec {
    unsigned controller;
    unsigned vendor;
    unsigned address;
};
bool select(const Codec *codecs, std::size_t count, unsigned controller,
            const Widget *widgets, std::size_t n, unsigned pin,
            const unsigned *edges, std::size_t m, unsigned &out) {
    if (!codecs || !widgets || !edges || count > 16 || n > 256 || m > 256 ||
        pin == 0 || pin > 255) return false;
    unsigned matches = 0;
    for (std::size_t i = 0; i < count; ++i)
        if (codecs[i].controller == controller && codecs[i].vendor == 0x8086281C) {
            if (codecs[i].address > 14) return false;
            ++matches;
        }
    if (matches != 1) return false;
    // Widgets and edges must belong to the selected codec; caller supplies verified snapshot.
    bool seen[256] {};
    bool target = false;
    for (std::size_t i = 0; i < n; ++i) {
        const auto &w = widgets[i];
        if (!w.nid || w.nid > 255 || seen[w.nid]) return false;
        seen[w.nid] = true;
        if (w.nid == pin) target = w.digital && !w.converter;
    }
    if (!target) return false;
    unsigned candidate = 0;
    for (std::size_t j = 0; j < m; ++j) {
        if (!edges[j] || edges[j] > 255 || !seen[edges[j]]) return false;
        for (std::size_t i = 0; i < n; ++i)
            if (widgets[i].nid == edges[j] && widgets[i].digital && widgets[i].converter) {
                if (candidate && candidate != edges[j]) return false;
                candidate = edges[j];
            }
    }
    if (!candidate) return false;
    out = candidate;
    return true;
}
int main() {
    Codec c[] {{1,0x8086281C,2},{1,0x10EC0256,0}};
    Widget w[] {{4,true,false},{3,true,true},{5,true,true}};
    unsigned e[] {3,5}, out = 0;
    assert(select(c,2,1,w,3,4,e,1,out) && out == 3);
    assert(!select(c,2,1,w,3,4,e,2,out));
    assert(!select(c,2,2,w,3,4,e,1,out));
    assert(!select(c+1,1,1,w,3,4,e,1,out));
    c[0].address = 15;
    assert(!select(c,2,1,w,3,4,e,1,out));
    c[0].address = 2;
    e[0] = 99;
    assert(!select(c,2,1,w,3,4,e,1,out));
}
