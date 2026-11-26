#!/usr/bin/env python3
"""Host-only checks for the real preflight collector and its redaction."""
import json
import plistlib
from pathlib import Path
import sys
import unittest

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "tools"))
import hdmi_audio_probe as probe


def checksum(block):
    block[127] = (-sum(block[:127])) % 256
    return bytes(block)


def base(extensions):
    block = bytearray(128)
    block[:8] = bytes.fromhex("00ffffffffffff00")
    block[126] = extensions
    return checksum(block)


def cta(payload=b"", flags=0):
    block = bytearray(128)
    block[:4] = bytes((2, 3, 4 + len(payload), flags))
    block[4:4 + len(payload)] = payload
    return checksum(block)


class ProbeTests(unittest.TestCase):
    def test_base_only(self):
        result = probe.edid_audio(base(0))
        self.assertEqual(result["status"], "valid")
        self.assertFalse(result["advertises_audio"])

    def test_audio_without_hdmi_vendor(self):
        # CTA basic audio and one three-byte short audio descriptor.
        result = probe.edid_audio(base(1) + cta(bytes((0x23, 0x09, 0x07, 0x01)), 0x40))
        self.assertTrue(result["advertises_audio"])
        self.assertTrue(result["basic_audio"])
        self.assertEqual(result["short_audio_descriptors"], 1)
        self.assertFalse(result["hdmi_vendor_block"])

    def test_vendor_only_not_audio(self):
        result = probe.edid_audio(base(1) + cta(bytes((0x63, 3, 12, 0))))
        self.assertTrue(result["hdmi_vendor_block"])
        self.assertFalse(result["advertises_audio"])

    def test_multiple_extensions(self):
        result = probe.edid_audio(base(2) + cta() + cta(bytes((0x23, 9, 7, 1))))
        self.assertEqual(result["cta_extensions"], 2)
        self.assertEqual(result["short_audio_descriptors"], 1)
        self.assertTrue(result["advertises_audio"])

    def test_truncation_and_checksum(self):
        good = base(1) + cta(flags=0x40)
        for bad in (good[:-1], good[:128], good[:-1] + bytes((good[-1] ^ 1,)),
                    bytes(128), b"", "not bytes"):
            self.assertEqual(probe.edid_audio(bad)["status"], "invalid")

    def test_malformed_blocks_never_publish_positive(self):
        for payload in (bytes((0x23, 9)), bytes((0x22, 9, 7)), bytes((0x20,))):
            result = probe.edid_audio(base(1) + cta(payload, 0x40))
            self.assertEqual(result["status"], "invalid")
            self.assertNotIn("advertises_audio", result)

    def test_invalid_later_extension_revokes_evidence(self):
        result = probe.edid_audio(base(2) + cta(flags=0x40) + bytes(127) + b"\x01")
        self.assertEqual(result["status"], "invalid")
        self.assertNotIn("basic_audio", result)

    def test_end_to_end_mocked_commands_and_privacy(self):
        registry = plistlib.dumps([{"IODisplayEDID": base(1) + cta(flags=0x40),
                                   "vendor-id": b"\x86\x80\x00\x00",
                                   "device-id": b"\xa3\x46\x00\x00",
                                   "IORegistryEntryName": "private-display",
                                   "serial-number": "private-serial"}])
        audio = json.dumps({"SPAudioDataType": [{"_items": [
            {"_name": "private-monitor", "coreaudio_device_output": 2,
             "coreaudio_device_transport": "HDMI"},
            {"_name": "private-mic", "coreaudio_device_output": 0}]}]}).encode()
        calls = []
        def run(args, timeout=15):
            calls.append(args)
            if args[0] == "/usr/sbin/ioreg":
                return registry if args[-1] == "AppleDisplay" else plistlib.dumps([])
            self.assertEqual(args, ["/usr/sbin/system_profiler", "SPAudioDataType", "-json"])
            return audio
        report = probe.collect(run)
        self.assertEqual(len(calls), len(probe.CLASSES) + 1)
        node = report["registry"]["AppleDisplay"]["nodes"][0]
        self.assertEqual(node["vendor-id"], "0x8086")
        self.assertEqual(node["device-id"], "0x46a3")
        self.assertTrue(node["edid_audio"]["advertises_audio"])
        self.assertEqual(report["audio_outputs"]["transport_counts"], {"HDMI": 1})
        self.assertNotIn("private-", json.dumps(report))
        self.assertNotIn("IODisplayEDID", json.dumps(report))

    def test_unavailable_is_not_zero(self):
        report = probe.collect(lambda args, timeout=15: None)
        self.assertEqual(report["registry"]["AppleDisplay"], {"status": "unavailable"})
        self.assertEqual(report["audio_outputs"], {"status": "unavailable"})

    def test_invalid_command_responses(self):
        report = probe.collect(lambda args, timeout=15: b"not a plist or JSON")
        self.assertEqual(report["registry"]["AppleDisplay"], {"status": "invalid-response"})
        self.assertEqual(report["audio_outputs"], {"status": "invalid-response"})


if __name__ == "__main__":
    unittest.main()
