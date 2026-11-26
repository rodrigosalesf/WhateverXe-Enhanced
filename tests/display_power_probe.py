#!/usr/bin/env python3
"""Host-only tests of the offline DMC entry-counter decoder and CLI."""
import json
from pathlib import Path
import subprocess
import sys
import tempfile
import unittest

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "tools"))
import display_power_probe as probe


def pair(before, after, elapsed=1000, epoch=1):
    return {"layout": "intel-display12-13-dmc",
            "before": {"time_ns": 10000, "epoch": 1, **before},
            "after": {"time_ns": 10000 + elapsed, "epoch": epoch, **after}}


class DisplayPowerTests(unittest.TestCase):
    def test_independent_entry_counts(self):
        r = probe.decode(pair({"dc5": 10, "dc6": 20}, {"dc5": 13, "dc6": 20}))
        self.assertEqual(r["counters"]["dc5"], {"status": "observed-difference", "entry_count_delta": 3})
        self.assertEqual(r["counters"]["dc6"], {"status": "observed-difference", "entry_count_delta": 0})
        self.assertNotIn("residency_percent", json.dumps(r))

    def test_missing_counter_does_not_hide_peer(self):
        r = probe.decode(pair({"dc5": 1}, {"dc5": 2, "dc6": 9}))
        self.assertEqual(r["counters"]["dc6"], {"status": "missing"})
        self.assertEqual(r["counters"]["dc5"]["entry_count_delta"], 1)

    def test_ambiguous_wrap_and_all_ones(self):
        r = probe.decode(pair({"dc5": 0xfffffffe, "dc6": 0xffffffff}, {"dc5": 1, "dc6": 2}))
        self.assertEqual(r["counters"]["dc5"], {"status": "wrap-or-reset-ambiguous"})
        self.assertEqual(r["counters"]["dc6"], {"status": "suspect-all-ones"})

    def test_invalid_counter_values(self):
        for bad in (True, -1, 2**32, 1.0, None, "1"):
            for a, b in ((bad, 1), (1, bad)):
                r = probe.decode(pair({"dc5": a}, {"dc5": b}))
                self.assertEqual(r["counters"]["dc5"], {"status": "invalid-word"})

    def test_discontinuity(self):
        for elapsed, epoch, expected in ((0, 1, "invalid-time-order"), (-1, 1, "invalid-time-order"),
                                          (1000, 2, "epoch-changed")):
            r = probe.decode(pair({"dc5": 1, "dc6": 2}, {"dc5": 2, "dc6": 3}, elapsed, epoch))
            self.assertEqual(r["status"], expected)
            self.assertEqual(r["counters"], {k: {"status": expected} for k in ("dc5", "dc6")})

    def test_layout_and_metadata(self):
        for bad in ({}, [], {**pair({}, {}), "layout": "xe3"},
                    pair({"private": 1}, {}), pair({}, {}, epoch=True)):
            with self.assertRaises(ValueError):
                probe.decode(bad)

    def test_cli(self):
        with tempfile.TemporaryDirectory() as directory:
            path = Path(directory) / "snapshot.json"
            cmd = [sys.executable, probe.__file__, str(path)]
            path.write_text(json.dumps(pair({"dc5": 0}, {"dc5": 1})))
            result = subprocess.run(cmd, capture_output=True)
            self.assertEqual(result.returncode, 0, result.stderr)
            self.assertEqual(json.loads(result.stdout)["counters"]["dc5"]["entry_count_delta"], 1)
            path.write_text(json.dumps({"private": "SECRET"}))
            result = subprocess.run(cmd, capture_output=True)
            self.assertEqual(result.returncode, 2)
            self.assertNotIn(b"SECRET", result.stderr)
            path.write_bytes(b" " * (probe.MAX_INPUT + 1))
            self.assertEqual(subprocess.run(cmd, capture_output=True).returncode, 2)


if __name__ == "__main__":
    unittest.main()
