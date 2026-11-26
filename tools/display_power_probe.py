#!/usr/bin/env python3
"""Offline TGL/ADL display DMC event-counter comparison, not residency."""
import argparse
import json
import sys

LAYOUT = "intel-display12-13-dmc"
MAX_INPUT = 65536
# Linux v6.12 intel_dmc_regs.h and intel_dmc.c: entry event counts.
REGISTERS = {"dc5": 0x101084, "dc6": 0x101088}


def decode(data):
    if not isinstance(data, dict) or set(data) != {"layout", "before", "after"} or data["layout"] != LAYOUT:
        raise ValueError("unsupported snapshot")
    a, b = data["before"], data["after"]
    for s in (a, b):
        if not isinstance(s, dict) or set(s) - {"epoch", "time_ns", *REGISTERS}:
            raise ValueError("invalid sample")
        for key in ("epoch", "time_ns"):
            if type(s.get(key)) is not int or not 0 <= s[key] < 2**64:
                raise ValueError("invalid sample metadata")
    elapsed = b["time_ns"] - a["time_ns"]
    status = ("invalid-time-order" if elapsed <= 0 else
              "epoch-changed" if a["epoch"] != b["epoch"] else "conditional-comparison")
    counters = {}
    for key in REGISTERS:
        x, y = a.get(key), b.get(key)
        if status != "conditional-comparison":
            counters[key] = {"status": status}
        elif key not in a or key not in b:
            counters[key] = {"status": "missing"}
        elif any(type(v) is not int or not 0 <= v < 2**32 for v in (x, y)):
            counters[key] = {"status": "invalid-word"}
        elif 0xffffffff in (x, y):
            counters[key] = {"status": "suspect-all-ones"}
        elif y < x:
            counters[key] = {"status": "wrap-or-reset-ambiguous"}
        else:
            counters[key] = {"status": "observed-difference", "entry_count_delta": y - x}
    return {"schema": 1, "layout": LAYOUT, "status": status, "counters": counters,
            "limitations": ["Caller-declared layout and continuity are unverified.",
                            "DMC entry counts are not residency time or proof of current DC state.",
                            "An unchanged count does not prove DC is disabled; unseen wraps cannot be excluded.",
                            "No MMIO, firmware, power policy, or live hardware validation."]}


def main():
    p = argparse.ArgumentParser(description=__doc__)
    p.add_argument("snapshot")
    args = p.parse_args()
    try:
        with open(args.snapshot, "rb") as f:
            raw = f.read(MAX_INPUT + 1)
        if len(raw) > MAX_INPUT:
            raise ValueError("input limit")
        result = decode(json.loads(raw))
    except (OSError, ValueError, RecursionError):
        p.exit(2, "Invalid or unsupported DMC snapshot.\n")
    print(json.dumps(result, indent=2, sort_keys=True))
    return 0


if __name__ == "__main__":
    sys.exit(main())
