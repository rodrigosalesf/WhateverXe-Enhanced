#!/usr/bin/env python3
"""Read-only HDMI/DP audio preflight. Outputs redacted JSON, not a fix."""
import argparse
import json
import plistlib
import subprocess
import sys
import platform

CLASSES = ("AppleIntelFramebuffer", "AppleDisplay", "IODisplayConnect",
           "AppleHDAController", "IOHDACodecDevice", "AppleGFXHDA",
           "IOAudioEngine")
HEADER = bytes.fromhex("00ffffffffffff00")


def edid_audio(data):
    """Summarize validated CTA audio evidence, not ELD or live playback."""
    def invalid(reason):
        return {"status": "invalid", "reason": reason}
    if not isinstance(data, bytes) or len(data) < 128 or len(data) % 128:
        return invalid("length")
    if data[:8] != HEADER or sum(data[:128]) % 256:
        return invalid("base")
    count = data[126]
    if len(data) != (count + 1) * 128:
        return invalid("extension-count")
    basic = False
    sad_count = cta_count = 0
    hdmi_vendor = False
    for offset in range(128, len(data), 128):
        block = data[offset:offset + 128]
        if sum(block) % 256:
            return invalid("extension-checksum")
        if block[0] != 2:
            continue
        cta_count += 1
        if block[1] < 3:
            return invalid("unsupported-cta-revision")
        end = block[2]
        if end != 0 and not 4 <= end <= 127:
            return invalid("cta-offset")
        basic |= bool(block[3] & 0x40)
        pos = 4
        while end and pos < end:
            tag, length = block[pos] >> 5, block[pos] & 31
            pos += 1
            if pos + length > end:
                return invalid("cta-block-overrun")
            payload = block[pos:pos + length]
            if tag == 1:
                if length == 0 or length % 3:
                    return invalid("audio-block-length")
                sad_count += length // 3
            elif tag == 3 and length >= 3:
                hdmi_vendor |= payload[:3] in (b"\x03\x0c\x00", b"\xd8\x5d\xc4")
            pos += length
    return {"status": "valid", "extensions": count, "cta_extensions": cta_count,
            "basic_audio": basic, "short_audio_descriptors": sad_count,
            "hdmi_vendor_block": hdmi_vendor,
            "advertises_audio": basic or sad_count > 0}


def numeric_property(value):
    if isinstance(value, bytes) and len(value) in (1, 2, 4, 8):
        return int.from_bytes(value, "little")
    if type(value) is int and 0 <= value < 2**64:
        return value
    return None


def summarize_node(node):
    # Deliberately exclude raw EDID, names, serials, UUIDs, paths, and arbitrary properties.
    result = {}
    for key in ("vendor-id", "device-id", "class-code", "IOHDACodecVendorID",
                "IOHDACodecAddress", "status-mask", "audio-codec-info", "connector-type"):
        number = numeric_property(node.get(key))
        if number is not None:
            result[key] = f"0x{number:x}"
    if "IODisplayEDID" in node:
        result["edid_audio"] = edid_audio(node["IODisplayEDID"])
    if "hda-gfx" in node:
        result["hda-gfx-present"] = True
    return result


def plist_nodes(value):
    if not isinstance(value, list) or any(not isinstance(n, dict) for n in value):
        raise ValueError("unexpected registry plist")
    return [summarize_node(n) for n in value]


def command(args, timeout=15):
    try:
        p = subprocess.run(args, stdout=subprocess.PIPE, stderr=subprocess.DEVNULL,
                           timeout=timeout, check=False)
    except (OSError, subprocess.TimeoutExpired):
        return None
    return p.stdout if p.returncode == 0 else None


def registry_class(cls, run=command):
    raw = run(["/usr/sbin/ioreg", "-a", "-r", "-d", "1", "-c", cls])
    if raw is None:
        return {"status": "unavailable"}
    try:
        nodes = plist_nodes(plistlib.loads(raw))
    except (ValueError, TypeError, OverflowError, plistlib.InvalidFileException):
        return {"status": "invalid-response"}
    return {"status": "observed", "count": len(nodes), "nodes": nodes}


def audio_output_summary(value):
    # Count only explicit output-channel fields; never infer transport from a name.
    if not isinstance(value, dict) or not isinstance(value.get("SPAudioDataType"), list):
        raise ValueError("unexpected audio report")
    outputs = 0
    transports = {}
    def walk(x):
        nonlocal outputs
        if isinstance(x, list):
            for item in x:
                walk(item)
        elif isinstance(x, dict):
            channels = x.get("coreaudio_device_output")
            try:
                n = int(channels) if type(channels) in (int, str) else 0
            except ValueError:
                n = 0
            if n > 0:
                outputs += 1
                transport = x.get("coreaudio_device_transport")
                key = transport if transport in ("HDMI", "DisplayPort", "Built-in", "USB", "Bluetooth") else "other-or-unavailable"
                transports[key] = transports.get(key, 0) + 1
            for item in x.get("_items", []):
                walk(item)
    walk(value["SPAudioDataType"])
    return {"status": "observed", "outputs_with_channel_count": outputs,
            "transport_counts": transports}


def collect(run=command):
    report = {"schema": 1, "macos": platform.mac_ver()[0],
              "registry": {cls: registry_class(cls, run) for cls in CLASSES}}
    raw = run(["/usr/sbin/system_profiler", "SPAudioDataType", "-json"], 30)
    try:
        report["audio_outputs"] = audio_output_summary(json.loads(raw)) if raw is not None else {"status": "unavailable"}
    except (ValueError, TypeError, UnicodeError):
        report["audio_outputs"] = {"status": "invalid-response"}
    report["limitations"] = ["Registry snapshots are not proof of connector ownership, codec response, ELD validity, or audible playback.",
                             "Missing fields/classes may reflect OS/driver differences; zero observations do not establish absence.",
                             "EDID audio evidence is not proof that a display audio route works."]
    return report


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.parse_args()
    if sys.platform != "darwin":
        parser.exit(2, "This diagnostic requires macOS.\n")
    print(json.dumps(collect(), indent=2, sort_keys=True))
    return 0


if __name__ == "__main__":
    sys.exit(main())
