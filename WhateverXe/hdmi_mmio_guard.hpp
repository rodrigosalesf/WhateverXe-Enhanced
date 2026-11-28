#pragma once
#include <stddef.h>
#include <stdint.h>
namespace HdmiMmio {
// Preconditions only; no mapping, dereference or authorization of hardware writes.
inline bool validOffset(size_t length, size_t offset) {
    return length >= sizeof(uint32_t) && offset % sizeof(uint32_t) == 0 &&
           offset <= length - sizeof(uint32_t);
}
inline bool readableSnapshot(size_t length, size_t offset, bool powered,
                             uint32_t value) {
    return powered && validOffset(length, offset) && value != UINT32_MAX;
}
}
