#!/usr/bin/env python3
"""Read-only HDMI/DP audio preflight. Outputs redacted JSON, not a fix."""
import argparse
import json
import plistlib
import subprocess
import sys
import platform
from xml.parsers.expat import ExpatError

CLASSES = ("AppleIntelFramebuffer", "AppleDisplay", "IODisplayConnect",
           "AppleHDAController", "IOHDACodecDevice", "AppleGFXHDA",
           "IOAudioEngine", "IOPCIDevice")
HEADER = bytes.fromhex("00ffffffffffff00")


PCM_RATES = (32000, 44100, 48000, 88200, 96000, 176400, 192000)


def stereo_pcm16_rates(sads):
    """Rates explicitly advertised in a single LPCM SAD with >=2 channels."""
    rates = set()
    for sad in sads:
        if len(sad) != 3:
            continue
        a, b, c = sad
        # Reserved bits, missing rates/depth and non-LPCM are not positive evidence.
        if a & 0x80 or (a >> 3) != 1 or (a & 7) < 1:
            continue
        if b & 0x80 or c & 0xf8 or not (c & 1):
            continue
        rates.update(rate for i, rate in enumerate(PCM_RATES) if b & (1 << i))
    return sorted(rates)


def eld_audio(data):
    """Read a version-2 ELD baseline; no hardware access and no raw identity output.

    Layout reference: Linux v6.12 include/drm/drm_eld.h (MIT).
    The 4-byte header is excluded from the dword baseline length.
    Vendor-specific bytes after the baseline are not interpreted.
    """
    def invalid(reason):
        return {"status": "invalid", "reason": reason}
    if not isinstance(data, bytes) or len(data) < 4:
        return invalid("header-length")
    if data[0] >> 3 != 2:
        return {"status": "unsupported", "reason": "eld-version"}
    end = 4 + data[2] * 4
    if end < 20 or end > len(data):
        return invalid("baseline-length")
    name_length = data[4] & 31
    count = data[5] >> 4
    connection = (data[5] >> 2) & 3
    if name_length > 16:
        return invalid("monitor-name-length")
    if connection not in (0, 1):
        return {"status": "unsupported", "reason": "connection-type"}
    start = 20 + name_length
    if start + 3 * count > end:
        return invalid("sad-overrun")
    sads = [data[p:p + 3] for p in range(start, start + 3 * count, 3)]
    return {"status": "valid", "version": 2, "baseline_bytes": end,
            "connection": ("HDMI", "DisplayPort")[connection],
            "short_audio_descriptors": count,
            "speaker_allocation_mask": data[7] & 0x7f,
            "stereo_pcm16_rates_hz": stereo_pcm16_rates(sads)}


def compare_audio_evidence(edid, eld):
    """Compare explicit capabilities only; inputs need not describe the same sink."""
    if edid.get("status") != "valid" or eld.get("status") != "valid":
        return {"status": "unavailable"}
    a = set(edid["stereo_pcm16_rates_hz"])
    b = set(eld["stereo_pcm16_rates_hz"])
    return {"status": "compared", "common_stereo_pcm16_rates_hz": sorted(a & b),
            "edid_only_rates_hz": sorted(a - b),
            "eld_only_rates_hz": sorted(b - a),
            "limitations": "Explicit LPCM SAD evidence only; no physical sink association or playback proof."}


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
    sads = []
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
                sads.extend(payload[p:p + 3] for p in range(0, length, 3))
            elif tag == 3 and length >= 3:
                hdmi_vendor |= payload[:3] in (b"\x03\x0c\x00", b"\xd8\x5d\xc4")
            pos += length
    return {"status": "valid", "extensions": count, "cta_extensions": cta_count,
            "basic_audio": basic, "short_audio_descriptors": sad_count,
            "hdmi_vendor_block": hdmi_vendor,
            "stereo_pcm16_rates_hz": stereo_pcm16_rates(sads),
            "advertises_audio": basic or sad_count > 0}


def numeric_property(value):
    if isinstance(value, bytes) and len(value) in (1, 2, 4, 8):
        return int.from_bytes(value, "little")
    if type(value) is int and 0 <= value < 2**64:
        return value
    return None


def pci_display_audio_subclass(code):
    """Decode the recognized class/subclass from either supported PCI encoding."""
    return next((candidate for candidate in
                 ((code >> 16) & 0xffff, (code >> 8) & 0xffff)
                 if candidate in (0x0401, 0x0403) or
                 0x0300 <= candidate <= 0x03ff), None)


def summarize_node(node):
    # Deliberately exclude raw EDID, names, serials, UUIDs, paths, and arbitrary properties.
    result = {}
    for key in ("vendor-id", "device-id", "class-code", "IOHDACodecVendorID",
                "IOHDACodecAddress", "status-mask", "audio-codec-info", "connector-type"):
        number = numeric_property(node.get(key))
        if number is not None:
            result[key] = f"0x{number:x}"
            if key == "status-mask":
                result["codec-status-mask-set-bits"] = [
                    bit for bit in range(16) if number & (1 << bit)]
    if "IODisplayEDID" in node:
        result["edid_audio"] = edid_audio(node["IODisplayEDID"])
    if "hda-gfx" in node:
        result["hda-gfx-present"] = True
    return result


def plist_nodes(value):
    if not isinstance(value, list) or any(not isinstance(n, dict) for n in value):
        raise ValueError("unexpected registry plist")
    return [summarize_node(n) for n in value]


def hda_gfx_value(node):
    """Return a bounded comparison-only hda-gfx token; never include it in JSON."""
    value = node.get("hda-gfx")
    if isinstance(value, bytes):
        if not 0 < len(value) <= 128:
            return None
        raw = value
        try:
            value = value.decode("ascii")
        except UnicodeDecodeError:
            return raw
        if not value.isprintable():
            return raw
    if (not isinstance(value, str) or not value or len(value) > 128
            or not value.isprintable()):
        return None
    return value


def hda_gfx_value_category(node):
    """Classify a property for diagnostics without returning its content."""
    value = node.get("hda-gfx")
    if isinstance(value, bytes):
        if not value:
            return "empty-data"
        if len(value) > 128:
            return "oversized-data"
        try:
            decoded = value.decode("ascii")
        except UnicodeDecodeError:
            return "non-ascii-data"
        return "ascii-data" if decoded.isprintable() else "non-printable-data"
    if isinstance(value, str):
        if not value:
            return "empty-string"
        if len(value) > 128:
            return "oversized-string"
        return "printable-string" if value.isprintable() else "non-printable-string"
    return "other-type"


def hda_gfx_association(gpu_values, audio_values, service_status,
                        gpu_property_count=None, audio_property_count=None):
    """Compare candidate service properties without publishing their values."""
    gpu = set(gpu_values)
    audio = set(audio_values)
    gpu_property_count = (len(gpu_values) if gpu_property_count is None
                          else gpu_property_count)
    audio_property_count = (len(audio_values) if audio_property_count is None
                            else audio_property_count)
    unreadable = (gpu_property_count != len(gpu_values) or
                  audio_property_count != len(audio_values))
    if any(status != "observed" for status in service_status.values()):
        status = "incomplete"
    elif unreadable:
        status = "incomplete"
    elif not gpu_property_count and not audio_property_count:
        status = "not-observed"
    elif not gpu_property_count or not audio_property_count:
        status = "incomplete"
    elif gpu & audio:
        status = "shared-value-observed"
    else:
        status = "different-values-observed"
    return {"status": status, "gpu_candidates": gpu_property_count,
            "audio_candidates": audio_property_count,
            "service_status": service_status,
            "limitations": "Compares only hda-gfx values on selected service classes; it does not prove provider ownership or AppleGFXHDA attachment."}


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
    if not raw:
        return {"status": "invalid-response", "reason": "empty-response"}
    try:
        decoded = plistlib.loads(raw)
    except (ValueError, TypeError, OverflowError, plistlib.InvalidFileException, ExpatError):
        return {"status": "invalid-response", "reason": "malformed-plist"}
    if not isinstance(decoded, list):
        return {"status": "invalid-response", "reason": "unexpected-root-type"}
    if any(not isinstance(node, dict) for node in decoded):
        return {"status": "invalid-response", "reason": "unexpected-node-type"}
    nodes = plist_nodes(decoded)
    result = {"status": "observed", "count": len(nodes), "nodes": nodes}
    result["_hda_gfx_values"] = [token for node in decoded
                                  if (token := hda_gfx_value(node)) is not None]
    result["_hda_gfx_property_count"] = sum(
        "hda-gfx" in node for node in decoded)
    if cls == "IOPCIDevice":
        class_codes = [numeric_property(node.get("class-code")) for node in decoded]
        class_codes = [code for code in class_codes if code is not None]
        result["pci_class_code_observations"] = len(class_codes)
        audio_devices = []
        subclasses = []
        audio_hda_gfx_values = []
        audio_hda_gfx_property_count = 0
        audio_hda_gfx_categories = {}
        display_subclasses = []
        display_hda_gfx_values = []
        display_hda_gfx_property_count = 0
        display_hda_gfx_categories = {}
        for node in decoded:
            code = numeric_property(node.get("class-code"))
            if code is None:
                continue
            subclass = pci_display_audio_subclass(code)
            if subclass is None:
                continue
            if 0x0300 <= subclass <= 0x03ff:
                display_subclasses.append(subclass)
                if "hda-gfx" in node:
                    display_hda_gfx_property_count += 1
                    category = hda_gfx_value_category(node)
                    display_hda_gfx_categories[category] = (
                        display_hda_gfx_categories.get(category, 0) + 1)
                    token = hda_gfx_value(node)
                    if token is not None:
                        display_hda_gfx_values.append(token)
                continue
            subclasses.append(subclass)
            if "hda-gfx" in node:
                audio_hda_gfx_property_count += 1
                category = hda_gfx_value_category(node)
                audio_hda_gfx_categories[category] = (
                    audio_hda_gfx_categories.get(category, 0) + 1)
                token = hda_gfx_value(node)
                if token is not None:
                    audio_hda_gfx_values.append(token)
            item = {"class-code": f"0x{subclass:x}"}
            for key in ("vendor-id", "device-id"):
                value = numeric_property(node.get(key))
                if value is not None:
                    item[key] = f"0x{value:x}"
            audio_devices.append(item)
        result["pci_audio_class_devices"] = audio_devices
        result["pci_dsp_audio_class_candidates"] = subclasses.count(0x0401)
        result["pci_hda_class_candidates"] = subclasses.count(0x0403)
        result["pci_audio_class_candidates"] = (
            result["pci_dsp_audio_class_candidates"] +
            result["pci_hda_class_candidates"])
        result["pci_audio_class_status"] = "observed" if class_codes else "unavailable"
        result["pci_display_class_candidates"] = len(display_subclasses)
        result["pci_display_class_status"] = "observed" if class_codes else "unavailable"
        result["pci_display_hda_gfx_value_categories"] = display_hda_gfx_categories
        result["pci_audio_hda_gfx_value_categories"] = audio_hda_gfx_categories
        result["_pci_audio_hda_gfx_values"] = audio_hda_gfx_values
        result["_pci_audio_hda_gfx_property_count"] = audio_hda_gfx_property_count
        result["_pci_display_hda_gfx_values"] = display_hda_gfx_values
        result["_pci_display_hda_gfx_property_count"] = display_hda_gfx_property_count
        result["nodes"] = []  # PCI enumeration is summarized; device inventory is not emitted.
    return result


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
    registry = {cls: registry_class(cls, run) for cls in CLASSES}
    gpu_values = []
    gpu_property_count = 0
    for cls in ("AppleIntelFramebuffer",):
        gpu_values.extend(registry[cls].pop("_hda_gfx_values", []))
        gpu_property_count += registry[cls].pop("_hda_gfx_property_count", 0)
    audio_values = []
    audio_property_count = 0
    for cls in ("AppleHDAController", "AppleGFXHDA"):
        audio_values.extend(registry[cls].pop("_hda_gfx_values", []))
        audio_property_count += registry[cls].pop("_hda_gfx_property_count", 0)
    pci_audio_values = registry["IOPCIDevice"].pop("_pci_audio_hda_gfx_values", [])
    pci_audio_property_count = registry["IOPCIDevice"].pop(
        "_pci_audio_hda_gfx_property_count", 0)
    pci_display_values = registry["IOPCIDevice"].pop("_pci_display_hda_gfx_values", [])
    pci_display_property_count = registry["IOPCIDevice"].pop(
        "_pci_display_hda_gfx_property_count", 0)
    for result in registry.values():
        result.pop("_hda_gfx_values", None)
        result.pop("_hda_gfx_property_count", None)
        result.pop("_pci_audio_hda_gfx_values", None)
        result.pop("_pci_audio_hda_gfx_property_count", None)
        result.pop("_pci_display_hda_gfx_values", None)
        result.pop("_pci_display_hda_gfx_property_count", None)
    association_classes = {"AppleIntelFramebuffer": registry["AppleIntelFramebuffer"]["status"],
                           "AppleHDAController": registry["AppleHDAController"]["status"],
                           "AppleGFXHDA": registry["AppleGFXHDA"]["status"]}
    report = {"schema": 1, "macos": platform.mac_ver()[0], "registry": registry,
              "hda_gfx_association": hda_gfx_association(
                  gpu_values, audio_values, association_classes,
                  gpu_property_count, audio_property_count)}
    pci_audio_association = hda_gfx_association(
        gpu_values, pci_audio_values,
        {"AppleIntelFramebuffer": registry["AppleIntelFramebuffer"]["status"],
         "PCI audio-class candidates": registry["IOPCIDevice"].get(
             "pci_audio_class_status", "unavailable")},
        gpu_property_count, pci_audio_property_count)
    pci_audio_association["limitations"] = (
        "Compares only hda-gfx values on AppleIntelFramebuffer and PCI audio-class candidates; "
        "it does not prove provider ownership, AppleGFXHDA attachment, or playback.")
    report["pci_audio_hda_gfx_association"] = pci_audio_association
    pci_display_audio_association = hda_gfx_association(
        pci_display_values, pci_audio_values,
        {"PCI display-class candidates": registry["IOPCIDevice"].get(
             "pci_display_class_status", "unavailable"),
         "PCI audio-class candidates": registry["IOPCIDevice"].get(
             "pci_audio_class_status", "unavailable")},
        pci_display_property_count, pci_audio_property_count)
    pci_display_audio_association["limitations"] = (
        "Compares only hda-gfx values on PCI display-class and audio-class candidates; "
        "it does not prove provider ownership, AppleGFXHDA attachment, or playback.")
    report["pci_display_audio_hda_gfx_association"] = pci_display_audio_association
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
    parser.add_argument("--eld-file", help="offline binary ELD snapshot (no device access)")
    parser.add_argument("--edid-file", help="optional offline binary EDID snapshot to compare")
    args = parser.parse_args()
    if args.edid_file and not args.eld_file:
        parser.error("--edid-file requires --eld-file")
    if args.eld_file:
        def read_bounded(path, limit):
            with open(path, "rb") as f:
                data = f.read(limit + 1)
            if len(data) > limit:
                raise ValueError("input exceeds diagnostic size limit")
            return data
        try:
            eld = eld_audio(read_bounded(args.eld_file, 4096))
            report = {"schema": 1, "eld": eld}
            if args.edid_file:
                edid = edid_audio(read_bounded(args.edid_file, 256 * 128))
                report["edid"] = edid
                report["comparison"] = compare_audio_evidence(edid, eld)
        except (OSError, ValueError):
            parser.exit(2, "Unable to read bounded binary input.\\n")
        print(json.dumps(report, indent=2, sort_keys=True))
        return 0 if eld["status"] == "valid" and report.get("edid", {"status": "valid"})["status"] == "valid" else 1
    if sys.platform != "darwin":
        parser.exit(2, "This diagnostic requires macOS.\n")
    print(json.dumps(collect(), indent=2, sort_keys=True))
    return 0


if __name__ == "__main__":
    sys.exit(main())
