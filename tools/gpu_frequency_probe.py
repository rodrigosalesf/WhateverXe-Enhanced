#!/usr/bin/env python3
"""Decode offline Xe-LP GT frequency register snapshots; never access MMIO."""
import argparse
import json
import sys

MAX_INPUT = 64 * 1024
LAYOUT = "intel-xe-lp-gen12"
# Layout facts: Linux v6.12 i915 intel_rps.c, intel_rps.h,
# intel_gt_regs.h and intel_mchbar_regs.h. Not a live register reader.
REGISTERS = {
    "rp_state_cap": 0x145998,
    "freq_info_rec": 0x145ef0,
    "rpstat1": 0x1381b4,
    "rpnswreq": 0xa008,
}


def word(snapshot, key):
    if key not in snapshot:
        return "missing", None
    value = snapshot[key]
    if type(value) is not int or not 0 <= value <= 0xffffffff:
        return "invalid-word", None
    if value == 0xffffffff:
        return "all-ones", None
    return "observed", value


def opcode_mhz(opcode):
    # Round the exact 50/3 MHz unit to nearest integer MHz.
    return (opcode * 50 + 1) // 3


def limits(snapshot):
    cap_status, cap = word(snapshot, "rp_state_cap")
    rec_status, rec = word(snapshot, "freq_info_rec")
    if cap is None or rec is None:
        return {"status": "unavailable", "cap_status": cap_status,
                "nominal_status": rec_status}
    rp0, rp1, rpn = (cap & 0xff) * 50, ((rec >> 8) & 0xff) * 50, ((cap >> 16) & 0xff) * 50
    if not 0 < rpn <= rp1 <= rp0:
        return {"status": "inconsistent-limits", "rp0_mhz": rp0,
                "rp1_mhz": rp1, "rpn_mhz": rpn}
    return {"status": "observed", "rp0_mhz": rp0, "rp1_mhz": rp1,
            "rpn_mhz": rpn}


def frequency(snapshot, key, shift, bounds):
    status, raw = word(snapshot, key)
    if raw is None:
        return {"status": status}
    opcode = (raw >> shift) & 0x1ff
    mhz = opcode_mhz(opcode)
    result = {"status": "observed" if opcode else "observed-zero",
              "opcode": opcode, "mhz_rounded": mhz}
    if not opcode or bounds["status"] != "observed":
        result["relation_to_nominal_limits"] = "unavailable"
    elif opcode * 50 < bounds["rpn_mhz"] * 3:
        result["relation_to_nominal_limits"] = "below-rpn"
    elif opcode * 50 > bounds["rp0_mhz"] * 3:
        result["relation_to_nominal_limits"] = "above-rp0"
    else:
        result["relation_to_nominal_limits"] = "within-rpn-rp0"
    return result


def decode(snapshot):
    if not isinstance(snapshot, dict) or snapshot.get("layout") != LAYOUT:
        raise ValueError("unsupported register layout")
    if set(snapshot) - ({"layout"} | set(REGISTERS)):
        raise ValueError("unknown snapshot fields")
    bounds = limits(snapshot)
    return {"schema": 1, "layout": LAYOUT, "hardware_limits": bounds,
            "actual": frequency(snapshot, "rpstat1", 11, bounds),
            "register_request": frequency(snapshot, "rpnswreq", 23, bounds),
            "limitations": [
                "Offline caller-declared Xe-LP layout; identity, register access and snapshot coherence are not verified.",
                "A zero opcode can occur in RC6; it does not establish RC6, idle state or a failed read.",
                "RP0 is a nominal non-overclocked limit; out-of-range observations are not clamped.",
                "Register request is not necessarily the driver's cached host RPS target or a GuC policy limit.",
                "No register access, clock request, forcewake or energy measurement is performed."]}


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("snapshot", help="JSON with layout and optional unsigned register words")
    args = parser.parse_args()
    try:
        with open(args.snapshot, "rb") as f:
            data = f.read(MAX_INPUT + 1)
        if len(data) > MAX_INPUT:
            raise ValueError("input limit")
        result = decode(json.loads(data))
    except (OSError, ValueError, RecursionError):
        parser.exit(2, "Invalid or unsupported register snapshot.\n")
    print(json.dumps(result, indent=2, sort_keys=True))
    return 0


if __name__ == "__main__":
    sys.exit(main())
