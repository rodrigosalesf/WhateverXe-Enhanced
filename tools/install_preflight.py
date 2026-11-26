#!/usr/bin/env python3
"""Read-only configuration preflight for the standard WhateverXe OpenCore path."""
import argparse
import json
import plistlib
import re
import sys
from pathlib import Path
from xml.parsers.expat import ExpatError

MAX_INPUT = 4 * 1024 * 1024
MAX_ENTRIES = 4096
GUID = "7C436110-AB2A-4BBB-A880-FE41995C9F82"
REQUIRED = ("lilu", "amfianchor", "amfianchorinjector", "whateverxe")
KNOWN = set(REQUIRED) | {"whatevergreen", "amfipass"}


def version(value):
    if not isinstance(value, str) or not re.fullmatch(r"[0-9]{1,5}(\.[0-9]{1,5}){2}", value):
        raise ValueError("invalid Darwin version")
    return tuple(map(int, value.split(".")))


def mapping(value):
    if not isinstance(value, dict):
        raise ValueError("invalid config structure")
    return value


def analyze(config, darwin):
    target = version(darwin)
    if not 20 <= target[0] <= 25:
        raise ValueError("outside supported OS family scope")
    entries = mapping(mapping(config).get("Kernel")).get("Add")
    if not isinstance(entries, list) or len(entries) > MAX_ENTRIES:
        raise ValueError("invalid Kernel/Add")

    active = {name: [] for name in KNOWN}
    for index, raw in enumerate(entries):
        entry = mapping(raw)
        enabled = entry.get("Enabled")
        if type(enabled) is not bool:
            raise ValueError("invalid entry enable flag")
        if not enabled:
            continue
        arch = entry.get("Arch")
        bundle = entry.get("BundlePath")
        low, high = entry.get("MinKernel"), entry.get("MaxKernel")
        if (arch not in ("Any", "x86_64", "i386") or not isinstance(bundle, str)
                or not bundle or not isinstance(low, str) or not isinstance(high, str)):
            raise ValueError("invalid entry metadata")
        minimum = version(low) if low else (0, 0, 0)
        maximum = version(high) if high else (99999, 99999, 99999)
        if minimum > maximum:
            raise ValueError("inverted Darwin bounds")
        if arch == "i386" or not minimum <= target <= maximum:
            continue
        # Canonical top-level names only; no inspection of actual bundle IDs.
        if bundle.lower().endswith(".kext"):
            name = bundle[:-5].lower()
            if name in active:
                active[name].append(index)

    findings = []
    for name in REQUIRED:
        if not active[name]:
            findings.append("missing-" + name)
    for name in sorted(KNOWN):
        if len(active[name]) > 1:
            findings.append("duplicate-" + name)
    for first, second, code in (
        ("lilu", "whateverxe", "lilu-before-whateverxe"),
        ("lilu", "amfianchor", "lilu-before-amfianchor"),
        ("amfianchor", "amfianchorinjector", "anchor-before-injector"),
        ("amfianchor", "amfipass", "amfipass-after-anchor"),
        ("amfianchorinjector", "amfipass", "amfipass-after-injector"),
    ):
        if len(active[first]) == len(active[second]) == 1 and active[first][0] >= active[second][0]:
            findings.append(code)
    if active["whatevergreen"] and active["whateverxe"]:
        findings.append("whatevergreen-conflict")

    nvram = mapping(mapping(mapping(config.get("NVRAM")).get("Add")).get(GUID, {}))
    args = nvram.get("boot-args", "")
    if not isinstance(args, str):
        raise ValueError("invalid boot arguments")
    tokens = args.split()
    for flag, code in (("-allow3d", "missing-allow3d"),
                       ("-disablegfxfirmware", "missing-disablegfxfirmware")):
        if flag not in tokens:
            findings.append(code)
    amfi_disabled = "amfi_get_out_of_my_way=1" in tokens
    for token in tokens:
        if token.startswith("amfi="):
            try:
                amfi_disabled |= bool(int(token[5:], 0) & 0x80)
            except ValueError:
                findings.append("unrecognized-amfi-override")
    if amfi_disabled:
        findings.append("amfi-disabled")
    if "ipc_control_port_options=0" in tokens:
        findings.append("ipc-control-port-override")
    if nvram.get("csr-active-config") != bytes.fromhex("03080000"):
        findings.append("unexpected-sip")
    findings = sorted(set(findings))
    return {
        "schema": 1,
        "target_darwin": darwin,
        "status": "config-findings" if findings else "no-known-config-blockers",
        "blocking_findings": findings,
        "active_known_entries": {name: len(active[name]) for name in sorted(KNOWN)},
        "limitations": [
            "Standard post-install OpenCore profile only; installer and custom injector profiles are not qualified.",
            "Findings are deviations from the documented configuration, not proof of boot failure.",
            "Canonical filenames and declared Kernel/Add metadata only; renamed bundles, files, executable identity, actual Lilu version and custom CA are not inspected.",
            "NVRAM Add values are proposed configuration, not live NVRAM or effective boot arguments.",
            "Run matching ocvalidate and inspect actual EFI files, Graphics package, GPU identity, DVMT and ABI separately.",
            "No bootability, signature, rollback success or hardware compatibility is certified."
        ]
    }


def read_config(path):
    with path.open("rb") as f:
        data = f.read(MAX_INPUT + 1)
    if len(data) > MAX_INPUT:
        raise ValueError("input exceeds limit")
    return mapping(plistlib.loads(data))


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("config", type=Path)
    parser.add_argument("--darwin", required=True)
    parser.add_argument("--backup-config", type=Path)
    args = parser.parse_args()
    try:
        report = analyze(read_config(args.config), args.darwin)
        if args.backup_config:
            if args.config.samefile(args.backup_config):
                raise ValueError("backup must be a separate file")
            backup = analyze(read_config(args.backup_config), args.darwin)
            report["backup"] = {
                "status": "config-readable-not-boot-verified",
                "blocking_findings": backup["blocking_findings"],
                "limitations": "Only this separate config file was read; a complete EFI backup was not checked or created."
            }
    except (OSError, ValueError, TypeError, OverflowError, RecursionError,
            ExpatError, plistlib.InvalidFileException):
        parser.exit(2, "Invalid or unavailable configuration snapshot.\n")
    print(json.dumps(report, indent=2, sort_keys=True))
    return 1 if report["blocking_findings"] or report.get("backup", {}).get("blocking_findings") else 0


if __name__ == "__main__":
    sys.exit(main())
