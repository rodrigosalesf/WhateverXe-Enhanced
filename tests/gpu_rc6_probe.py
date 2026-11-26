#!/usr/bin/env python3
"""Host-only checks for the offline RC6 interval decoder and CLI."""
import json
from pathlib import Path
import subprocess
import sys
import tempfile
import unittest

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "tools"))
import gpu_rc6_probe as probe


def pair(c0, c1, elapsed=12800, e0=7, e1=7):
    return {"layout": "intel-xe-lp-gen12-rc6",
            "before": {"time_ns": 100000, "epoch": e0, "rc6": c0},
            "after": {"time_ns": 100000 + elapsed, "epoch": e1, "rc6": c1}}


class RC6Tests(unittest.TestCase):
    def test_known_tick_and_residency(self):
        r = probe.decode(pair(20, 25))
        self.assertEqual(r["status"], "conditional-delta")
        self.assertEqual(r["delta_ticks"], 5)
        self.assertEqual(r["residency_ns"], 6400)
        self.assertEqual(r["residency_percent"], 50.0)
        self.assertFalse(r["wrapped"])

    def test_zero_and_full_residency(self):
        for count, expected in ((0, 0), (10, 100)):
            r = probe.decode(pair(50, 50 + count))
            self.assertEqual(r["status"], "conditional-delta")
            self.assertEqual(r["residency_percent"], expected)

    def test_single_wrap(self):
        r = probe.decode(pair(0xfffffffc, 2))
        self.assertEqual(r["delta_ticks"], 6)
        self.assertEqual(r["residency_ns"], 7680)
        self.assertEqual(r["residency_percent"], 60)
        self.assertTrue(r["wrapped"])

    def test_epoch_and_time_discontinuities(self):
        for data, expected in ((pair(10, 11, e1=8), "epoch-changed"),
                               (pair(10, 11, 0), "invalid-time-order"),
                               (pair(10, 11, -1), "invalid-time-order")):
            r = probe.decode(data)
            self.assertEqual(r["status"], expected)
            self.assertNotIn("residency_percent", r)

    def test_unavailable_counters(self):
        for invalid in (0xffffffff, -1, 2**32, True, None, "20", 3.5):
            for data in (pair(invalid, 20), pair(20, invalid)):
                r = probe.decode(data)
                self.assertEqual(r["status"], "counter-unavailable")
                self.assertNotIn("delta_ticks", r)
        self.assertEqual(probe.decode(pair(0xffffffff, 0))["before_status"],
                         "suspect-all-ones")

    def test_ambiguous_wrap_window(self):
        wrap_ns = 5497558138880
        for elapsed in (wrap_ns, wrap_ns + 1, wrap_ns * 2):
            self.assertEqual(probe.decode(pair(12, 12, elapsed))["status"],
                             "ambiguous-wrap-window")
        self.assertEqual(probe.decode(pair(12, 12, wrap_ns - 1))["status"],
                         "ambiguous-wrap-window")
        self.assertEqual(probe.decode(pair(12, 12, wrap_ns - 1281))["status"],
                         "conditional-delta")

    def test_quantization_and_impossible_delta(self):
        r = probe.decode(pair(1, 2, 1000))
        self.assertEqual(r["residency_percent_status"], "quantization-ambiguous")
        self.assertNotIn("residency_percent", r)
        for data in (pair(1, 12, 1000), pair(100, 2)):
            self.assertEqual(probe.decode(data)["status"], "inconsistent-residency")

    def test_reject_unknown_layout_and_metadata(self):
        for data in ({}, [], {**pair(1, 2), "layout": "xe3"},
                     {**pair(1, 2), "private": "secret"}):
            with self.assertRaises(ValueError):
                probe.decode(data)
        for key in ("time_ns", "epoch"):
            data = pair(1, 2)
            data["before"][key] = True
            with self.assertRaises(ValueError):
                probe.decode(data)

    def test_cli(self):
        with tempfile.TemporaryDirectory() as directory:
            path = Path(directory) / "rc6.json"
            cmd = [sys.executable, probe.__file__, str(path)]
            path.write_text(json.dumps(pair(20, 25)))
            r = subprocess.run(cmd, capture_output=True)
            self.assertEqual(r.returncode, 0, r.stderr)
            self.assertEqual(json.loads(r.stdout)["residency_percent"], 50)
            path.write_text(json.dumps({"private": "SECRET"}))
            r = subprocess.run(cmd, capture_output=True)
            self.assertEqual(r.returncode, 2)
            self.assertNotIn(b"SECRET", r.stderr)
            path.write_bytes(b" " * (probe.MAX_INPUT + 1))
            self.assertEqual(subprocess.run(cmd, capture_output=True).returncode, 2)


if __name__ == "__main__":
    unittest.main()
