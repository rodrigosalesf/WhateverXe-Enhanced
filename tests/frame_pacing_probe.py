#!/usr/bin/env python3
"""Host-only tests for frame pacing analysis and the real offline CLI."""
import json
from pathlib import Path
import subprocess
import sys
import tempfile
import unittest

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "tools"))
import frame_pacing_probe as probe


def trace(gaps, n=60, d=1, source="synthetic", start=0):
    stamps = [start]
    for gap in gaps:
        stamps.append(stamps[-1] + gap)
    return {"source": source, "refresh": {"numerator": n, "denominator": d},
            "timestamps_ns": stamps}


class FramePacingTests(unittest.TestCase):
    def test_statistics_and_long_gaps(self):
        r = probe.analyze(trace([10_000_000, 20_000_000, 30_000_000, 40_000_000]))
        self.assertEqual(r["interval_ms"], {"min": 10, "median": 25, "p95": 40, "max": 40})
        self.assertEqual(r["samples"], 5)
        self.assertEqual(r["intervals"], 4)
        self.assertEqual(r["duration_ns"], 100_000_000)
        self.assertEqual(r["observed_event_rate_hz"], 40)
        self.assertEqual(r["long_gaps"], 2)
        self.assertEqual(r["long_gap_fraction"], 0.5)

    def test_exact_fractional_refresh_boundary(self):
        for n, d, boundary in ((60, 1, 25_000_000), (60000, 1001, 25_025_000),
                               (120, 1, 12_500_000)):
            r = probe.analyze(trace([boundary - 1, boundary, boundary + 1], n, d))
            self.assertEqual(r["long_gaps"], 1)
            self.assertEqual(r["long_gap_fraction"], 0.333333)

    def test_nearest_rank_and_even_median(self):
        r = probe.analyze(trace([i * 1_000_000 for i in range(1, 101)]))
        self.assertEqual(r["interval_ms"]["median"], 50.5)
        self.assertEqual(r["interval_ms"]["p95"], 95)
        self.assertEqual(probe.analyze(trace([7_000_000]))["interval_ms"],
                         {"min": 7, "median": 7, "p95": 7, "max": 7})

    def test_large_timestamp_origin_and_no_raw_export(self):
        a = probe.analyze(trace([16_000_000, 17_000_000]))
        b = probe.analyze(trace([16_000_000, 17_000_000], start=2**62))
        self.assertEqual(a, b)
        self.assertNotIn("timestamps_ns", b)
        self.assertNotIn("dropped_frames", b)

    def test_conditional_reference_comparison(self):
        a = probe.analyze(trace([20_000_000, 40_000_000], 120, 2, "presentation"))
        b = probe.analyze(trace([20_000_000, 20_000_000], 60, 1, "presentation"))
        r = probe.compare(a, b)
        self.assertEqual(r["status"], "conditional-comparison")
        self.assertEqual(r["candidate_minus_reference"],
                         {"median_interval_ms": -10, "p95_interval_ms": -20,
                          "long_gap_fraction": -0.5})
        for t in (trace([20_000_000], 60, 1, "vblank"), trace([20_000_000], 120, 1, "presentation")):
            with self.assertRaises(ValueError):
                probe.compare(a, probe.analyze(t))

    def test_no_command_completion_source(self):
        for source in ("gpu-completion", "cpu-submit", "fps", None, []):
            with self.assertRaises(ValueError):
                probe.analyze(trace([1], source=source))

    def test_reject_nonmonotonic_and_invalid_samples(self):
        for samples in ([], [0], [1, 1], [2, 1], [0, 2, 1, 3],
                        [-1, 2], [False, 2], [0, 2.0], [0, 2**63],
                        [0, probe.MAX_DURATION_NS + 1], list(range(probe.MAX_SAMPLES + 1))):
            t = trace([1])
            t["timestamps_ns"] = samples
            with self.assertRaises(ValueError):
                probe.analyze(t)

    def test_invalid_refresh_and_unknown_fields(self):
        for n, d in ((0, 1), (60, 0), (True, 1), (60, 1.0), (1001, 1),
                     (1, 2), (1000001, 10000), (60000, 10001)):
            with self.assertRaises(ValueError):
                probe.analyze(trace([1], n, d))
        for t in ({}, [], {**trace([1]), "private": "SECRET"}):
            with self.assertRaises(ValueError):
                probe.analyze(t)

    def test_cli_and_privacy(self):
        with tempfile.TemporaryDirectory() as directory:
            path = Path(directory) / "trace.json"
            ref = Path(directory) / "reference.json"
            cmd = [sys.executable, probe.__file__, str(path)]
            path.write_text(json.dumps(trace([10_000_000, 20_000_000])))
            ref.write_text(json.dumps(trace([30_000_000, 40_000_000])))
            r = subprocess.run(cmd + ["--reference", str(ref)], capture_output=True)
            self.assertEqual(r.returncode, 0, r.stderr)
            self.assertEqual(json.loads(r.stdout)["candidate_minus_reference"]["long_gap_fraction"], -1)
            path.write_text(json.dumps({"private": "SECRET"}))
            r = subprocess.run(cmd, capture_output=True)
            self.assertEqual(r.returncode, 2)
            self.assertNotIn(b"SECRET", r.stderr)
            path.write_bytes(b" " * (probe.MAX_INPUT + 1))
            self.assertEqual(subprocess.run(cmd, capture_output=True).returncode, 2)


if __name__ == "__main__":
    unittest.main()
