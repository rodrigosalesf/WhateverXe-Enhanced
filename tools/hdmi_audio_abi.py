#!/usr/bin/env python3
"""Read-only audit of upstream HDMI hook assumptions in local Intel Mach-O kexts.

No patches, load commands, device access, or binary export. A matching prefix
is necessary but not sufficient: it does not validate a live ABI or object layout.
"""
import argparse
import hashlib
import json
from pathlib import Path
import struct

# Original hook signatures from jkbuha/WhateverXe-contrib 94b8fb6 (BSD-3-Clause).
# Keep these as reference expectations, not inferred Sequoia signatures.
PUSH = bytes.fromhex("55 48 89 e5 41 57 41 56 41 55 41 54 53")
CONTROLLER = {
    "__ZN18AppleHDAController23framebufferEventHandlerEPvP13IOFramebufferiS0_":
        PUSH + bytes.fromhex("48 81 ec 18 03 00 00"),
    "__ZN18AppleHDAController19edidIsValidForAudioEP6OSDatai":
        PUSH + bytes.fromhex("48 83 ec 38"),
    "__ZN18AppleHDAController19executeCodecCommandEP16IOHDACodecDevicejPj": None,
}
MAIN = {
    "__ZN20AppleHDACodecGeneric5startEP9IOService": PUSH + bytes.fromhex("48 83 ec 28"),
    "__ZN14AppleHDAEngine23performAudioEngineStartEv": PUSH + bytes.fromhex("48 83 ec 58"),
    "__ZN21AppleHDAFunctionGroup34pathMapCanBeConstructedByDiscoveryEv": None,
    "__ZN21AppleHDAFunctionGroup27constructPathMapByDiscoveryEPP7OSArray": None,
}
FRAMEBUFFER = {
    "__ZN21AppleIntelFramebuffer13fbGetDDCBlockEjPhPyjP21AppleIntelDisplayPath": None,
    "__ZN21AppleIntelFramebuffer18setAudioPropertiesEv": None,
    "__ZN21AppleIntelFramebuffer21setupDisplayResourcesEv": None,
}
MAX_IMAGE = 128 * 1024 * 1024


class InvalidImage(ValueError):
    pass


def require(condition):
    if not condition:
        raise InvalidImage("invalid or unsupported thin x86_64 kext image")


def bounded(offset, length, limit):
    return 0 <= offset <= limit and 0 <= length <= limit - offset


def audit(data, targets):
    require(32 <= len(data) <= MAX_IMAGE)
    magic, cpu, _, filetype, ncmds, cmdsize, _, _ = struct.unpack_from("<8I", data)
    require(magic == 0xfeedfacf and cpu == 0x01000007 and filetype == 11)
    require(bounded(32, cmdsize, len(data)) and ncmds <= cmdsize // 8)
    end = 32 + cmdsize
    pos = 32
    sections = []
    symtab = None
    for _ in range(ncmds):
        require(bounded(pos, 8, end))
        cmd, size = struct.unpack_from("<2I", data, pos)
        require(size >= 8 and size % 8 == 0 and bounded(pos, size, end))
        if cmd == 0x19:  # LC_SEGMENT_64
            require(size >= 72)
            seg, vm, vmsize, fileoff, filesize, _, prot, nsects, _ = struct.unpack_from(
                "<16s4Q4I", data, pos + 8
            )
            require(nsects <= (size - 72) // 80)
            require(bounded(fileoff, filesize, len(data)))
            for i in range(nsects):
                name, section_seg, addr, length, offset, _, _, _, flags, _, _, _ = (
                    struct.unpack_from("<16s16s2Q8I", data, pos + 72 + i * 80)
                )
                executable = (
                    name.rstrip(b"\0") == b"__text"
                    and seg.rstrip(b"\0") in (b"__TEXT", b"__TEXT_EXEC")
                    and section_seg == seg
                    and bool(prot & 4)
                    and bool(flags & 0x80000400)
                    and (flags & 0xff) == 0
                )
                if executable:
                    require(addr >= vm and bounded(addr - vm, length, vmsize))
                    require(offset >= fileoff and bounded(offset - fileoff, length, filesize))
                    require(bounded(offset, length, len(data)))
                    require(offset - fileoff == addr - vm)
                sections.append((executable, addr, length, offset))
        elif cmd == 2:  # LC_SYMTAB
            require(symtab is None and size == 24)
            symtab = struct.unpack_from("<4I", data, pos + 8)
        pos += size
    require(pos == end and symtab is not None)
    symoff, count, stroff, strsize = symtab
    require(bounded(symoff, count * 16, len(data)))
    require(bounded(stroff, strsize, len(data)))
    require(symoff >= end and stroff >= end)
    require(symoff + count * 16 <= stroff or stroff + strsize <= symoff)

    found = {name: [] for name in targets}
    encoded = {name.encode("ascii"): name for name in targets}
    for i in range(count):
        idx, typ, sec, _, addr = struct.unpack_from("<IBBHQ", data, symoff + i * 16)
        if typ & 0xe0 or (typ & 0x0e) != 0x0e:
            continue
        require(idx < strsize)
        stop = data.find(b"\0", stroff + idx, stroff + strsize)
        require(stop >= 0)
        # A bytearray fixture yields a mutable slice; normalize only the symbol.
        name = encoded.get(bytes(data[stroff + idx:stop]))
        if name is not None:
            found[name].append((sec, addr))

    result = {}
    for name, expected in targets.items():
        matches = found[name]
        if len(matches) != 1:
            result[name] = "missing" if not matches else "ambiguous"
            continue
        sec, addr = matches[0]
        if not 0 < sec <= len(sections):
            result[name] = "invalid_section"
            continue
        executable, base, length, offset = sections[sec - 1]
        need = len(expected) if expected is not None else 1
        delta = addr - base
        if not executable or not bounded(delta, need, length):
            result[name] = "invalid_section"
        elif expected is None:
            result[name] = "symbol_present"
        elif data[offset + delta:offset + delta + need] == expected:
            result[name] = "prefix_match"
        else:
            result[name] = "prefix_mismatch"
    return result


def audit_file(path, targets):
    try:
        with path.open("rb") as handle:
            data = handle.read(MAX_IMAGE + 1)
        symbols = audit(data, targets)
    except (OSError, InvalidImage, struct.error):
        return {"status": "unavailable_or_unsupported", "symbols": {}}
    good = all(
        status == ("prefix_match" if targets[name] is not None else "symbol_present")
        for name, status in symbols.items()
    )
    return {
        "status": "reference_matches" if good else "reference_not_matched",
        "sha256": hashlib.sha256(data).hexdigest(),
        "symbols": symbols,
    }


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--controller", required=True, type=Path)
    parser.add_argument("--applehda", required=True, type=Path)
    parser.add_argument("--framebuffer", required=True, type=Path)
    args = parser.parse_args()
    images = {
        "controller": audit_file(args.controller, CONTROLLER),
        "applehda": audit_file(args.applehda, MAIN),
        "framebuffer": audit_file(args.framebuffer, FRAMEBUFFER),
    }
    print(json.dumps({"schema": 1, "images": images, "kernel_activation_authorized": False},
                     indent=2, sort_keys=True))
    return 0 if all(x["status"] == "reference_matches" for x in images.values()) else 1


if __name__ == "__main__":
    raise SystemExit(main())
