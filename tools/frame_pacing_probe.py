#!/usr/bin/env python3
"""Analyze offline presentation or VBlank timestamps, not GPU command timings."""
import argparse
import json
import math
import sys

MAX_INPUT = 4 * 1024 * 1024
MAX_SAMPLES = 60000
MAX_DURATION_NS = 24 * 60 * 60 * 10**9
SOURCES = {"presentation", "vblank", "synthetic"}


def analyze(trace):
    if not isinstance(trace, dict) or set(trace) != {"source", "refresh", "timestamps_ns"}:
        raise ValueError("invalid trace schema")
    source, refresh, samples = (trace[k] for k in ("source", "refresh", "timestamps_ns"))
    if not isinstance(source, str) or source not in SOURCES:
        raise ValueError("unsupported timestamp source")
    if not isinstance(refresh, dict) or set(refresh) != {"numerator", "denominator"}:
        raise ValueError("invalid refresh ratio")
    n, d = refresh["numerator"], refresh["denominator"]
    if (type(n) is not int or type(d) is not int or
            not 1 <= n <= 1000000 or not 1 <= d <= 10000 or not d <= n <= 1000 * d):
        raise ValueError("refresh out of range")
    divisor = math.gcd(n, d)
    n, d = n // divisor, d // divisor
    if not isinstance(samples, list) or not 2 <= len(samples) <= MAX_SAMPLES:
        raise ValueError("invalid sample count")
    if any(type(t) is not int or not 0 <= t < 2**63 for t in samples):
        raise ValueError("invalid timestamp")
    duration = samples[-1] - samples[0]
    if not 0 < duration <= MAX_DURATION_NS:
        raise ValueError("invalid duration")
    intervals = [b - a for a, b in zip(samples, samples[1:])]
    if any(gap <= 0 for gap in intervals):
        raise ValueError("timestamps must be strictly increasing")
    count = len(intervals)
    sorted_gaps = sorted(intervals)
    # Compare exactly against 1.5 nominal refresh periods. Do not round the
    # threshold before counting; 60000/1001 Hz must not become 60 Hz.
    long_gaps = sum(2 * gap * n > 3 * 10**9 * d for gap in intervals)
    median = (sorted_gaps[(count - 1) // 2] + sorted_gaps[count // 2]) / 2
    p95 = sorted_gaps[(95 * count + 99) // 100 - 1]
    return {
        "schema": 1, "source": source,
        "refresh": {"numerator": n, "denominator": d},
        "samples": len(samples), "intervals": count, "duration_ns": duration,
        "nominal_period_ms": round(1000 * d / n, 6),
        "observed_event_rate_hz": round(count * 10**9 / duration, 6),
        "interval_ms": {
            "min": round(sorted_gaps[0] / 10**6, 6),
            "median": round(median / 10**6, 6),
            "p95": round(p95 / 10**6, 6),
            "max": round(sorted_gaps[-1] / 10**6, 6),
        },
        "long_gaps": long_gaps, "long_gap_fraction": round(long_gaps / count, 6),
        "limitations": [
            "Caller-declared source and fixed nominal refresh are unverified.",
            "Use one continuous capture; never join sessions or reset epochs.",
            "Long gap means strictly more than 1.5 nominal periods; not a dropped-frame count.",
            "VBlank event rate is not application FPS. Variable refresh and capture loss may affect intervals.",
            "No GPU command completion latency is interpreted as presentation timing.",
        ],
    }


def compare(reference, candidate):
    if reference["source"] != candidate["source"] or reference["refresh"] != candidate["refresh"]:
        raise ValueError("incompatible source or nominal refresh")
    return {
        "status": "conditional-comparison",
        "reference": reference, "candidate": candidate,
        "candidate_minus_reference": {
            "median_interval_ms": round(candidate["interval_ms"]["median"] - reference["interval_ms"]["median"], 6),
            "p95_interval_ms": round(candidate["interval_ms"]["p95"] - reference["interval_ms"]["p95"], 6),
            "long_gap_fraction": round(candidate["long_gap_fraction"] - reference["long_gap_fraction"], 6),
        },
        "limitations": "Equivalent workload, capture conditions, duration and device are not established by this tool; no performance improvement is inferred.",
    }


def load(path):
    with open(path, "rb") as f:
        data = f.read(MAX_INPUT + 1)
    if len(data) > MAX_INPUT:
        raise ValueError("input exceeds limit")
    return analyze(json.loads(data))


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("trace", help="JSON presentation/VBlank timestamp trace")
    parser.add_argument("--reference", help="optional baseline JSON trace")
    args = parser.parse_args()
    try:
        report = load(args.trace)
        if args.reference:
            report = compare(load(args.reference), report)
    except (OSError, ValueError, RecursionError):
        parser.exit(2, "Invalid or incompatible frame timing trace.\n")
    print(json.dumps(report, indent=2, sort_keys=True))
    return 0


if __name__ == "__main__":
    sys.exit(main())
