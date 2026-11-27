#pragma once
#include <stddef.h>

namespace HdmiRoute {
enum class Kind : unsigned char { Other, Pin, Converter };
struct Widget {
    unsigned nid;
    Kind kind;
    bool digital;
    const unsigned *connections;
    size_t count;
};
struct Codec {
    unsigned controller, vendor, address;
    const Widget *widgets;
    size_t count;
};
struct Route { unsigned address, pin, converter; };
// Pure selection only. Caller must establish hardware provenance and ABI.
inline bool select(const Codec *codecs, size_t count, unsigned controller,
                   unsigned vendor, unsigned pin, Route &out) {
    if (!codecs || count > 15 || !controller || (vendor >> 16) != 0x8086 ||
        !pin || pin > 127) return false;
    const Codec *chosen = nullptr;
    for (size_t i = 0; i < count; ++i) {
        const auto &c = codecs[i];
        if (c.controller != controller || c.vendor != vendor) continue;
        if (chosen || c.address > 14) return false;
        chosen = &c;
    }
    if (!chosen || !chosen->widgets || chosen->count > 127) return false;
    const Widget *nodes[128] {};
    for (size_t i = 0; i < chosen->count; ++i) {
        const auto &w = chosen->widgets[i];
        if (!w.nid || w.nid > 127 || nodes[w.nid]) return false;
        nodes[w.nid] = &w;
    }
    const auto *p = nodes[pin];
    if (!p || p->kind != Kind::Pin || !p->digital || !p->connections ||
        !p->count || p->count > 127) return false;
    unsigned candidate = 0;
    for (size_t i = 0; i < p->count; ++i) {
        unsigned nid = p->connections[i];
        if (!nid || nid > 127 || !nodes[nid] || nid == pin) return false;
        const auto &w = *nodes[nid];
        // Only direct, unambiguous digital paths are supported.
        if (w.kind != Kind::Converter || !w.digital) return false;
        if (candidate && candidate != nid) return false;
        candidate = nid;
    }
    if (!candidate) return false;
    out = {chosen->address, pin, candidate};
    return true;
}
}
