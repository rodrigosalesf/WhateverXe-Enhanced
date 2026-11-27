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
    // Explicit GET_CONNECT_SEL evidence, never inferred from ordering.
    bool selectionKnown {false};
    size_t selectedIndex {0};
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
    if (p->selectionKnown && p->selectedIndex >= p->count) return false;
    unsigned candidate = 0;
    for (size_t i = 0; i < p->count; ++i) {
        unsigned nid = p->connections[i];
        if (!nid || nid > 127 || !nodes[nid] || nid == pin) return false;
        const auto &w = *nodes[nid];
        // Only direct, unambiguous digital paths are supported.
        if (w.kind != Kind::Converter || !w.digital) return false;
        if (p->selectionKnown && i != p->selectedIndex) continue;
        if (candidate && candidate != nid) return false;
        candidate = nid;
    }
    if (!candidate) return false;
    out = {chosen->address, pin, candidate};
    return true;
}

// Adapted from the codec query approach in jkbuha/WhateverXe-contrib 94b8fb6.
// Reader is bound to one verified controller and codec address by its owner.
// No kernel hook or hardware command transport is installed by this helper.
struct PcmCaps { unsigned ratesAndDepths, formats; };
template<class Reader>
bool readSelectedPcm(Reader &reader, const Route &route, PcmCaps &out) {
    if (route.address > 14 || !route.pin || route.pin > 127 ||
        !route.converter || route.converter > 127 || route.pin == route.converter)
        return false;
    unsigned caps = 0, pcm = 0, formats = 0;
    if (!reader.get(route.address, route.converter, 0xF00, 0x09, caps) ||
        caps == 0xFFFFFFFFU || ((caps >> 20) & 15U) != 0 ||
        !(caps & (1U << 9)) || !(caps & (1U << 4))) return false;
    // Only explicit widget format overrides are accepted; inherited AFG
    // capabilities need separate verified function-group evidence.
    if (!reader.get(route.address, route.converter, 0xF00, 0x0A, pcm) ||
        !reader.get(route.address, route.converter, 0xF00, 0x0B, formats) ||
        pcm == 0xFFFFFFFFU || formats == 0xFFFFFFFFU ||
        !(formats & 1U) || !(pcm & 0xFFFU) || !(pcm & 0x1F0000U))
        return false;
    out = {pcm, formats};
    return true;
}

// Resolve inherited PCM only from an audio function group whose subordinate
// range contains the selected converter. Reader remains codec-bound.
template<class Reader>
bool readInheritedPcm(Reader &reader, const Route &route, unsigned afg, PcmCaps &out) {
    if (route.address > 14 || !afg || afg > 127 ||
        !route.converter || route.converter > 127 || route.converter == afg)
        return false;
    unsigned type = 0, children = 0, caps = 0, pcm = 0, formats = 0;
    if (!reader.get(route.address,afg,0xF00,5,type) ||
        type == 0xFFFFFFFFU || (type & 255U) != 1 ||
        !reader.get(route.address,afg,0xF00,4,children) ||
        children == 0xFFFFFFFFU) return false;
    const unsigned start = (children >> 16) & 255U, count = children & 255U;
    if (!start || start > 127 || !count || count > 128U-start ||
        route.converter < start || route.converter-start >= count) return false;
    if (!reader.get(route.address,route.converter,0xF00,9,caps) ||
        caps == 0xFFFFFFFFU || ((caps >> 20) & 15U) != 0 ||
        !(caps & 0x200U)) return false;
    if (caps & 16U) return readSelectedPcm(reader,route,out);
    if (!reader.get(route.address,afg,0xF00,10,pcm) ||
        !reader.get(route.address,afg,0xF00,11,formats) ||
        pcm == 0xFFFFFFFFU || formats == 0xFFFFFFFFU ||
        !(formats & 1U) || !(pcm & 0xFFFU) || !(pcm & 0x1F0000U)) return false;
    out = {pcm,formats};
    return true;
}


// Read a pin's actual connection list, including HDA range encoding.
// The reader must remain bound to the same codec for the entire query.
template<class Reader>
bool readPinConnections(Reader &reader, unsigned address, unsigned pin,
                        unsigned (&nodes)[127], size_t &count, size_t &selected) {
    if (address > 14 || !pin || pin > 127) return false;
    unsigned length = 0, caps = 0, selection = 0;
    if (!reader.get(address,pin,0xF00,9,caps) || caps == 0xFFFFFFFFU ||
        ((caps >> 20) & 15U) != 4 || !(caps & 0x200U) || !(caps & 0x100U) ||
        !reader.get(address,pin,0xF00,0x0E,length) || length > 255 ||
        !(length & 127U)) return false;
    const unsigned width = (length & 128U) ? 16U : 8U;
    const unsigned per = 32U / width, entries = length & 127U;
    const unsigned range = 1U << (width - 1U);
    unsigned scratch[127] {}, previous = 0, used = 0, word = 0;
    for (unsigned i = 0; i < entries; ++i) {
        if (i % per == 0 && (!reader.get(address,pin,0xF02,i,word) ||
                             word == 0xFFFFFFFFU)) return false;
        const unsigned entry = (word >> ((i % per)*width)) & (range*2U-1U);
        const unsigned nid = entry & (range-1U);
        if (!nid || nid > 127) return false;
        unsigned first = nid;
        if (entry & range) {
            if (!previous || nid <= previous) return false;
            first = previous + 1;
        }
        for (unsigned n = first; n <= nid; ++n) {
            if (used == 127 || n == pin) return false;
            scratch[used++] = n;
        }
        previous = nid;
    }
    if (used > 1 && (!reader.get(address,pin,0xF01,0,selection) ||
                     selection >= used)) return false;
    for (unsigned i = 0; i < used; ++i) nodes[i] = scratch[i];
    count = used;
    selected = selection;
    return true;
}
}
