#!/usr/bin/env python3
"""Read-only accelerator-statistics diagnostic; no MMIO or power policy changes."""
import argparse
import json
import plistlib
import subprocess
import sys
from xml.parsers.expat import ExpatError

MAX_INPUT = 16 * 1024 * 1024
U64_MAX = (1 << 64) - 1
# Exact observed driver keys only. Unknown fields and registry identity are omitted.
FIELDS = {
    "Device Utilization %": "percent",
    "Device Utilization % at cur p-state": "percent",
    **{f"Device Unit {i} Utilization %": "percent" for i in range(6)},
    "textureCount": "counter",
    "context2DCount": "counter",
    "contextVideoCount": "counter",
    "agpTextureCreationBytes": "texture-bytes",
    "gartSizeBytes": "bytes",
    "gartUsedBytes": "bytes",
    "gartCacheBytes": "bytes",
    "gartFreeBytes": "bytes",
    "agpTextureCreationCount": "counter",
    "iosurfaceTextureCreationCount": "counter",
    "recoveryCount": "counter",
}


def classify(value, kind):
    if type(value) is not int or not 0 <= value <= U64_MAX:
        return {"status": "invalid-type-or-range"}
    if value == U64_MAX:
        return {"status": "suspect-all-ones"}
    if kind == "percent" and value > 100:
        return {"status": "invalid-percent-range", "value": value}
    if kind == "texture-bytes" and value >= 1 << 63:
        # Diagnostic only: possible signed accounting artifact, not a proven
        # underflow, and not a corrected unsigned value.
        return {"status": "suspect-high-bit", "value": value}
    return {"status": "observed-zero" if value == 0 else "observed", "value": value}


def summarize(stats):
    if not isinstance(stats, dict):
        return {"status": "unavailable"}
    fields = {key: classify(stats[key], kind) if key in stats else {"status": "missing"}
              for key, kind in FIELDS.items()}
    size, used = fields["gartSizeBytes"], fields["gartUsedBytes"]
    relation = "unavailable"
    if size["status"] in ("observed", "observed-zero") and used["status"] in ("observed", "observed-zero"):
        # Report a relationship, not physical memory corruption or VRAM capacity.
        relation = "used-exceeds-reported-size" if used["value"] > size["value"] else "within-reported-size"
    return {"status": "observed", "fields": fields, "gart_relationship": relation}


def analyze(raw):
    if len(raw) > MAX_INPUT:
        raise ValueError("snapshot too large")
    roots = plistlib.loads(raw)
    if not isinstance(roots, list) or any(not isinstance(root, dict) for root in roots):
        raise ValueError("unexpected registry structure")
    # ioreg -r -d 1 yields the matching root objects. Do not recursively
    # associate unrelated child statistics or combine different accelerators.
    return {"schema": 1, "accelerator_count": len(roots),
            "accelerators": [summarize(root.get("PerformanceStatistics")) for root in roots],
            "limitations": ["Zero is an observed value, not proof of idle GPU or zero clock.",
                            "Missing counters or opaque units are not inferred.",
                            "Snapshots cannot establish counter semantics, GPU execution or energy savings.",
                            "No raw device names, identifiers, or unrelated registry properties are exported."]}


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--snapshot", help="offline ioreg XML or binary plist")
    args = parser.parse_args()
    try:
        if args.snapshot:
            with open(args.snapshot, "rb") as f:
                raw = f.read(MAX_INPUT + 1)
        else:
            if sys.platform != "darwin":
                parser.error("live collection requires macOS; use --snapshot on CI")
            # Read-only IORegistry query; no privileged operations.
            p = subprocess.run(["/usr/sbin/ioreg", "-a", "-r", "-d", "1", "-c", "IOAccelerator"],
                               stdout=subprocess.PIPE, stderr=subprocess.DEVNULL,
                               timeout=15, check=False)
            if p.returncode:
                raise ValueError("registry unavailable")
            raw = p.stdout
        report = analyze(raw)
    except (OSError, ValueError, TypeError, OverflowError, RecursionError,
            ExpatError, plistlib.InvalidFileException, subprocess.TimeoutExpired):
        parser.exit(2, "Invalid or unavailable accelerator snapshot.\n")
    print(json.dumps(report, indent=2, sort_keys=True))
    return 0


if __name__ == "__main__":
    sys.exit(main())
