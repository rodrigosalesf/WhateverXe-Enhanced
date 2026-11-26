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
                                   "hda-gfx": "private-route-token",
                                   "IORegistryEntryName": "private-display",
                                   "serial-number": "private-serial"}])
        gpu_registry = plistlib.dumps([{"hda-gfx": "private-route-token"}])
        audio_registry = plistlib.dumps([{"hda-gfx": "private-route-token"}])
        pci_registry = plistlib.dumps([{"class-code": 0x04030000,
                                        "vendor-id": 0x8086,
                                        "device-id": 0x51c8,
                                        "IORegistryEntryName": "private-pci-path"}])
        audio = json.dumps({"SPAudioDataType": [{"_items": [
            {"_name": "private-monitor", "coreaudio_device_output": 2,
             "coreaudio_device_transport": "HDMI"},
            {"_name": "private-mic", "coreaudio_device_output": 0}]}]}).encode()
        calls = []
        def run(args, timeout=15):
            calls.append(args)
            if args[0] == "/usr/sbin/ioreg":
                return {"AppleDisplay": registry,
                        "AppleIntelFramebuffer": gpu_registry,
                        "AppleHDAController": audio_registry,
                        "IOPCIDevice": pci_registry}.get(args[-1], plistlib.dumps([]))
            self.assertEqual(args, ["/usr/sbin/system_profiler", "SPAudioDataType", "-json"])
            return audio
        report = probe.collect(run)
        self.assertEqual(len(calls), len(probe.CLASSES) + 1)
        node = report["registry"]["AppleDisplay"]["nodes"][0]
        self.assertEqual(node["vendor-id"], "0x8086")
        self.assertEqual(node["device-id"], "0x46a3")
        self.assertTrue(node["edid_audio"]["advertises_audio"])
        self.assertEqual(report["audio_outputs"]["transport_counts"], {"HDMI": 1})
        self.assertEqual(report["hda_gfx_association"]["status"], "shared-value-observed")
        self.assertEqual(report["registry"]["IOPCIDevice"]["pci_audio_class_candidates"], 1)
        self.assertEqual(report["registry"]["IOPCIDevice"]["pci_class_code_observations"], 1)
        self.assertEqual(report["registry"]["IOPCIDevice"]["pci_audio_class_status"], "observed")
        self.assertEqual(report["registry"]["IOPCIDevice"]["nodes"], [])
        self.assertNotIn("private-", json.dumps(report))
        self.assertNotIn("private-route-token", json.dumps(report))
        self.assertNotIn("IODisplayEDID", json.dumps(report))

    def test_hda_gfx_comparison_is_cautious_and_redacted(self):
        for gpu, audio, expected in ((["shared-token"], ["shared-token"], "shared-value-observed"),
                                     (["gpu-a"], ["audio-b"], "different-values-observed"),
                                     (["gpu-a"], [], "incomplete"),
                                     ([], [], "not-observed")):
            result = probe.hda_gfx_association(
                gpu, audio, {"gpu": "observed", "hda": "observed"})
            self.assertEqual(result["status"], expected)
            self.assertNotIn("shared-token", json.dumps(result))
            self.assertNotIn("gpu-a", json.dumps(result))
            self.assertNotIn("audio-b", json.dumps(result))
        unavailable = probe.hda_gfx_association(
            [], [], {"gpu": "observed", "hda": "invalid-response"})
        self.assertEqual(unavailable["status"], "incomplete")

    def test_pci_class_absence_is_reported_as_unavailable(self):
        registry = plistlib.dumps([{"vendor-id": 0x8086, "device-id": 0x46a3}])
        result = probe.registry_class(
            "IOPCIDevice", lambda args, timeout=15: registry)
        self.assertEqual(result["count"], 1)
        self.assertEqual(result["pci_class_code_observations"], 0)
        self.assertEqual(result["pci_audio_class_candidates"], 0)
        self.assertEqual(result["pci_audio_class_status"], "unavailable")
        self.assertEqual(result["nodes"], [])

    def test_unavailable_is_not_zero(self):
        report = probe.collect(lambda args, timeout=15: None)
        self.assertEqual(report["registry"]["AppleDisplay"], {"status": "unavailable"})
        self.assertEqual(report["audio_outputs"], {"status": "unavailable"})

    def test_invalid_command_responses(self):
        report = probe.collect(lambda args, timeout=15: b"not a plist or JSON")
        self.assertEqual(report["registry"]["AppleDisplay"], {"status": "invalid-response"})
        self.assertEqual(report["audio_outputs"], {"status": "invalid-response"})


class EldTests(unittest.TestCase):
    @staticmethod
    def eld(sads, name=b"PRIVATE", connection=0, extra=b""):
        # Independent literal ELD v2 layout: 4-byte header, 16-byte fixed
        # baseline, monitor name, 3-byte SADs, padding to dword boundary.
        total = 20 + len(name) + sum(map(len, sads))
        size = (total + 3) & ~3
        buf = bytearray(size)
        buf[0] = 0x10
        buf[2] = (size - 4) // 4
        buf[4] = 0x60 | len(name)
        buf[5] = len(sads) * 16 + connection * 4
        buf[7] = 0x01
        buf[8:16] = b"PORTSECR"
        buf[20:20 + len(name)] = name
        buf[20 + len(name):total] = b"".join(sads)
        return bytes(buf) + extra

    def test_stereo_rates_and_redaction(self):
        raw = self.eld([b"\x09\x06\x01"], extra=b"VENDORSECRET")
        self.assertEqual(probe.eld_audio(raw), {
            "status": "valid", "version": 2, "baseline_bytes": 32,
            "connection": "HDMI", "short_audio_descriptors": 1,
            "speaker_allocation_mask": 1,
            "stereo_pcm16_rates_hz": [44100, 48000]})

    def test_dp_and_maximum_name_count(self):
        raw = self.eld([b"\x0f\x7f\x07"] * 15, name=b"A" * 16, connection=1)
        result = probe.eld_audio(raw)
        self.assertEqual(result["connection"], "DisplayPort")
        self.assertEqual(result["short_audio_descriptors"], 15)
        self.assertEqual(result["baseline_bytes"], 84)
        self.assertEqual(result["stereo_pcm16_rates_hz"],
                         [32000, 44100, 48000, 88200, 96000, 176400, 192000])

    def test_no_cross_descriptor_capability_invention(self):
        # Mono LPCM at 44.1, 24-bit-only stereo at 48, compressed stereo,
        # and one valid stereo/16-bit 96 kHz. Do not combine their fields.
        sads = [b"\x08\x02\x01", b"\x09\x04\x04",
                b"\x11\x06\x01", b"\x09\x10\x01"]
        self.assertEqual(probe.eld_audio(self.eld(sads))["stereo_pcm16_rates_hz"],
                         [96000])
        edid = probe.edid_audio(base(1) + cta(bytes([0x20 + 12]) + b"".join(sads)))
        self.assertEqual(edid["stereo_pcm16_rates_hz"], [96000])

    def test_reserved_bits_and_zero_sads(self):
        for sads in ([], [b"\x89\x06\x01"], [b"\x09\x86\x01"],
                     [b"\x09\x06\x81"], [b"\x09\x00\x01"]):
            self.assertEqual(probe.eld_audio(self.eld(sads))["stereo_pcm16_rates_hz"], [])

    def test_truncation_bad_length_and_sad_overrun(self):
        raw = self.eld([b"\x09\x06\x01"])
        for length in range(len(raw)):
            self.assertEqual(probe.eld_audio(raw[:length])["status"], "invalid")
        for index, value in ((2, 3), (2, 255), (4, 0x71), (5, 0xf0)):
            bad = bytearray(raw)
            bad[index] = value
            result = probe.eld_audio(bytes(bad))
            self.assertEqual(result["status"], "invalid")
            self.assertNotIn("stereo_pcm16_rates_hz", result)

    def test_unknown_version_and_connection(self):
        bad = bytearray(self.eld([]))
        bad[0] = 0xf8
        self.assertEqual(probe.eld_audio(bytes(bad))["status"], "unsupported")
        self.assertEqual(probe.eld_audio(self.eld([], connection=2))["status"],
                         "unsupported")

    def test_edid_eld_compare_explicit_rates(self):
        edid = probe.edid_audio(base(1) + cta(b"\x23\x09\x06\x01", 0x40))
        eld = probe.eld_audio(self.eld([b"\x09\x0c\x01"]))
        compared = probe.compare_audio_evidence(edid, eld)
        self.assertEqual(compared["common_stereo_pcm16_rates_hz"], [48000])
        self.assertEqual(compared["edid_only_rates_hz"], [44100])
        self.assertEqual(compared["eld_only_rates_hz"], [88200])
        basic_only = probe.edid_audio(base(1) + cta(flags=0x40))
        self.assertTrue(basic_only["advertises_audio"])
        self.assertEqual(probe.compare_audio_evidence(basic_only, eld)
                         ["common_stereo_pcm16_rates_hz"], [])
        self.assertEqual(probe.compare_audio_evidence(edid, probe.eld_audio(b"")),
                         {"status": "unavailable"})

    def test_cli_offline_real_files(self):
        import subprocess
        import tempfile
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            e = root / "eld.bin"
            d = root / "edid.bin"
            e.write_bytes(self.eld([b"\x09\x06\x01"]))
            d.write_bytes(base(1) + cta(b"\x23\x09\x04\x01"))
            command = [sys.executable, probe.__file__, "--eld-file", str(e),
                       "--edid-file", str(d)]
            result = subprocess.run(command, capture_output=True, check=False)
            self.assertEqual(result.returncode, 0)
            self.assertEqual(json.loads(result.stdout)["comparison"]
                             ["common_stereo_pcm16_rates_hz"], [48000])
            self.assertNotIn(b"PRIVATE", result.stdout)
            e.write_bytes(b"")
            self.assertEqual(subprocess.run(command, capture_output=True).returncode, 1)
            e.write_bytes(bytes(4097))
            self.assertEqual(subprocess.run(command, capture_output=True).returncode, 2)


if __name__ == "__main__":
    unittest.main()
