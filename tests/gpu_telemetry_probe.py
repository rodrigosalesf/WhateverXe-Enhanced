#!/usr/bin/env python3
"""Host-only fixtures for observed accelerator statistic keys and redaction."""
import json
from pathlib import Path
import plistlib
import subprocess
import sys
import tempfile
import unittest

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "tools"))
import gpu_telemetry_probe as probe


class TelemetryTests(unittest.TestCase):
    def test_zero_is_observation_not_missing(self):
        fields = probe.summarize({"Device Utilization %": 0})["fields"]
        self.assertEqual(fields["Device Utilization %"], {"status": "observed-zero", "value": 0})
        self.assertEqual(fields["Device Utilization % at cur p-state"], {"status": "missing"})

    def test_percent_boundary_and_type(self):
        for n in (1, 100):
            self.assertEqual(probe.classify(n, "percent"), {"status": "observed", "value": n})
        self.assertEqual(probe.classify(101, "percent")["status"], "invalid-percent-range")
        for invalid in (True, -1, 2**64, "25", 25.5, None):
            self.assertEqual(probe.classify(invalid, "percent")["status"], "invalid-type-or-range")

    def test_all_ones_and_possible_signed_artifact(self):
        self.assertEqual(probe.classify(2**64 - 1, "texture-bytes"), {"status": "suspect-all-ones"})
        for n in (2**63, 2**64 - 607698944):
            self.assertEqual(probe.classify(n, "texture-bytes"), {"status": "suspect-high-bit", "value": n})
        self.assertEqual(probe.classify(74960896, "texture-bytes")["status"], "observed")
        self.assertEqual(probe.classify(2**63, "bytes")["status"], "observed")

    def test_memory_relationship(self):
        for size, used, expected in ((7516192768, 297131008, "within-reported-size"),
                                     (4, 4, "within-reported-size"),
                                     (4, 5, "used-exceeds-reported-size"),
                                     (0, 1, "used-exceeds-reported-size"),
                                     (2**64 - 1, 1, "unavailable")):
            self.assertEqual(probe.summarize({"gartSizeBytes": size, "gartUsedBytes": used})
                             ["gart_relationship"], expected)
        self.assertEqual(probe.summarize({"gartUsedBytes": 0})["gart_relationship"], "unavailable")

    def test_separate_accelerators_no_child_mixing(self):
        raw = plistlib.dumps([
            {"IORegistryEntryName": "PRIVATE", "PerformanceStatistics": {"Device Utilization %": 0,
             "gartSizeBytes": 100, "serial-number": "SECRET"}, "IORegistryEntryChildren": [
                 {"PerformanceStatistics": {"gartUsedBytes": 99}}]},
            {"PerformanceStatistics": {"Device Utilization %": 75, "gartUsedBytes": 50}},
            {}])
        report = probe.analyze(raw)
        self.assertEqual(report["accelerator_count"], 3)
        a, b, c = report["accelerators"]
        self.assertEqual(a["fields"]["gartUsedBytes"]["status"], "missing")
        self.assertEqual(b["fields"]["gartSizeBytes"]["status"], "missing")
        self.assertEqual(a["gart_relationship"], "unavailable")
        self.assertEqual(b["gart_relationship"], "unavailable")
        self.assertEqual(c, {"status": "unavailable"})
        self.assertNotIn("PRIVATE", json.dumps(report))
        self.assertNotIn("SECRET", json.dumps(report))

    def test_binary_and_xml_equal(self):
        roots = [{"PerformanceStatistics": {"agpTextureCreationBytes": 2**64 - 607698944}}]
        self.assertEqual(probe.analyze(plistlib.dumps(roots)),
                         probe.analyze(plistlib.dumps(roots, fmt=plistlib.FMT_BINARY)))

    def test_invalid_root_and_empty(self):
        self.assertEqual(probe.analyze(plistlib.dumps([]))["accelerator_count"], 0)
        for roots in ({}, ["invalid"]):
            with self.assertRaises(ValueError):
                probe.analyze(plistlib.dumps(roots))

    def test_cli(self):
        with tempfile.TemporaryDirectory() as directory:
            path = Path(directory) / "snapshot.plist"
            cmd = [sys.executable, probe.__file__, "--snapshot", str(path)]
            path.write_bytes(plistlib.dumps([{"PerformanceStatistics": {"recoveryCount": 0}}]))
            p = subprocess.run(cmd, capture_output=True)
            self.assertEqual(p.returncode, 0, p.stderr)
            self.assertEqual(json.loads(p.stdout)["accelerators"][0]["fields"]["recoveryCount"],
                             {"status": "observed-zero", "value": 0})
            path.write_bytes(b"<plist><PRIVATE>")
            p = subprocess.run(cmd, capture_output=True)
            self.assertEqual(p.returncode, 2)
            self.assertNotIn(b"PRIVATE", p.stderr)
            path.write_bytes(b" " * (probe.MAX_INPUT + 1))
            self.assertEqual(subprocess.run(cmd, capture_output=True).returncode, 2)


if __name__ == "__main__":
    unittest.main()
