#!/usr/bin/env python3
"""Offline Xe-LP RC6 residency interval validation. No MMIO or wake acquisition."""
import argparse
import json
import sys

LAYOUT = "intel-xe-lp-gen12-rc6"
MAX_INPUT = 64 * 1024
TICK_NS = 1280
MODULUS = 1 << 32
WRAP_NS = MODULUS * TICK_NS


def sample(data):
    if not isinstance(data, dict) or set(data) != {"time_ns", "epoch", "rc6"}:
        raise ValueError("invalid sample shape")
    time, epoch, counter = (data[k] for k in ("time_ns", "epoch", "rc6"))
    if type(time) is not int or not 0 <= time < 2**64:
        raise ValueError("invalid timestamp")
    if type(epoch) is not int or not 0 <= epoch < 2**64:
        raise ValueError("invalid epoch")
    if type(counter) is not int or not 0 <= counter < MODULUS:
        return time, epoch, None, "invalid-word"
    if counter == MODULUS - 1:
        return time, epoch, None, "suspect-all-ones"
    return time, epoch, counter, "observed"


def decode(data):
    if not isinstance(data, dict) or set(data) != {"layout", "before", "after"} or data["layout"] != LAYOUT:
        raise ValueError("unsupported snapshot")
    t0, e0, c0, s0 = sample(data["before"])
    t1, e1, c1, s1 = sample(data["after"])
    elapsed = t1 - t0
    result = {"schema": 1, "layout": LAYOUT, "before_status": s0, "after_status": s1,
              "limitations": [
                  "Caller-declared counter identity, common reset epoch and timestamps are not independently verified.",
                  "A reset within an unchanged epoch can resemble wrap; result is conditional on continuity.",
                  "No physical register read, RC6 policy, ForceWake balance or power-saving claim."]}
    if elapsed <= 0:
        result["status"] = "invalid-time-order"
    elif e0 != e1:
        result["status"] = "epoch-changed"
    elif c0 is None or c1 is None:
        result["status"] = "counter-unavailable"
    elif elapsed >= WRAP_NS:
        result["status"] = "ambiguous-wrap-window"
    else:
        # Gen12 non-LP9: 32-bit residency in 1.28 us units (Linux i915
        # intel_rc6_residency_ns). The wrap interval bounds ambiguity.
        ticks = (c1 - c0) % MODULUS
        duration = ticks * TICK_NS
        # A counter tick may straddle the sampling window. Admit at most
        # one tick of quantization uncertainty; never clamp it into a percentage.
        if duration > elapsed + TICK_NS:
            result["status"] = "inconsistent-residency"
        else:
            result.update(status="conditional-delta", elapsed_ns=elapsed,
                          delta_ticks=ticks, residency_ns=duration,
                          wrapped=c1 < c0)
            if duration <= elapsed:
                result["residency_percent"] = round(duration * 100 / elapsed, 6)
            else:
                result["residency_percent_status"] = "quantization-ambiguous"
    return result


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("snapshot", help="offline pair of RC6 counter observations")
    args = parser.parse_args()
    try:
        with open(args.snapshot, "rb") as f:
            raw = f.read(MAX_INPUT + 1)
        if len(raw) > MAX_INPUT:
            raise ValueError("input limit")
        report = decode(json.loads(raw))
    except (OSError, ValueError, RecursionError):
        parser.exit(2, "Invalid or unsupported RC6 snapshot.\n")
    print(json.dumps(report, indent=2, sort_keys=True))
    return 0


if __name__ == "__main__":
    sys.exit(main())
