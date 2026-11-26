#!/usr/bin/env python3
"""Host-only tests of normalized ownership accounting and CLI."""
import copy
import json
from pathlib import Path
import subprocess
import sys
import tempfile
import unittest

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "tools"))
import gpu_memory_probe as probe


def snapshot():
    return {"schema": "wex-memory-accounting-v1",
            "clients": [{"id": 900001}, {"id": 900002}],
            "contexts": [{"id": 100, "client": 900001}, {"id": 200, "client": 900002}],
            "queues": [{"id": 10, "context": 100, "client": 900001},
                       {"id": 11, "context": 100, "client": 900001},
                       {"id": 20, "context": 200, "client": 900002}],
            "allocations": [{"id": 1, "bytes": 4096, "queues": [10, 11]},
                            {"id": 2, "bytes": 8192, "queues": [10, 20]},
                            {"id": 3, "bytes": 1024, "queues": [20]},
                            {"id": 4, "bytes": 512, "queues": []}]}


class MemoryTests(unittest.TestCase):
    def test_registry_series_deltas_require_one_unambiguous_observation(self):
        high = str(2**63 + 8)
        report = probe.analyze_registry_series([
            {"elapsed_ns": 0, "captured_at_utc": "2026-01-01T00:00:00+00:00",
             "registry_text": '"inUseSysMemoryBytes"=100'},
            {"elapsed_ns": 1_000_000_000, "captured_at_utc": "2026-01-01T00:00:01+00:00",
             "registry_text": '"inUseSysMemoryBytes"=125'},
            {"elapsed_ns": 2_000_000_000, "captured_at_utc": "2026-01-01T00:00:02+00:00",
             "registry_text": '"inUseSysMemoryBytes"=' + high},
            {"elapsed_ns": 3_000_000_000, "captured_at_utc": "2026-01-01T00:00:03+00:00",
             "registry_text": '"inUseSysMemoryBytes"=125'},
            {"elapsed_ns": 4_000_000_000, "captured_at_utc": "2026-01-01T00:00:04+00:00",
             "registry_text": '"inUseSysMemoryBytes"=125\n"inUseSysMemoryBytes"=125'},
            {"elapsed_ns": 5_000_000_000, "captured_at_utc": "2026-01-01T00:00:05+00:00",
             "registry_text": '"inUseVidMemoryBytes"=7'},
        ])
        samples = report["samples"]
        self.assertEqual(report["schema"], "wex-memory-registry-series-v1")
        self.assertEqual(samples[1]["counters"]["inUseSysMemoryBytes"]["delta_from_previous"],
                         {"status": "computed", "bytes": 25, "elapsed_ns": 1_000_000_000})
        self.assertEqual(samples[2]["counters"]["inUseSysMemoryBytes"]["delta_from_previous"]["status"],
                         "suspicious-value")
        self.assertEqual(samples[4]["counters"]["inUseSysMemoryBytes"]["delta_from_previous"]["status"],
                         "ambiguous-observation")
        self.assertEqual(samples[5]["counters"]["inUseSysMemoryBytes"]["delta_from_previous"]["status"],
                         "missing-observation")
        self.assertNotIn("registry_text", json.dumps(report))

    def test_registry_series_rejects_nonmonotonic_and_malformed_samples(self):
        valid = {"elapsed_ns": 0, "captured_at_utc": "2026-01-01T00:00:00+00:00",
                 "registry_text": '"inUseSysMemoryBytes"=100'}
        for samples in ([valid, {**valid, "elapsed_ns": 0}],
                        [{**valid, "captured_at_utc": "not-a-time"}],
                        [{**valid, "elapsed_ns": True}],
                        [{**valid, "unexpected": "field"}]):
            with self.subTest(samples=samples), self.assertRaises(ValueError):
                probe.analyze_registry_series(samples)

    def test_temporal_collector_uses_read_only_ioreg_and_keeps_failures_as_gaps(self):
        class Clock:
            elapsed = 0

            def monotonic_ns(self):
                return self.elapsed

            def sleep(self, seconds):
                self.elapsed += int(seconds * 1_000_000_000)

        clock = Clock()
        calls = []

        class Result:
            stdout = '"inUseSysMemoryBytes"=100'

        def run(command, **kwargs):
            calls.append((command, kwargs))
            if len(calls) == 2:
                raise OSError("fixture failure")
            return Result()

        timestamps = iter(("2026-01-01T00:00:00+00:00", "2026-01-01T00:00:01+00:00",
                           "2026-01-01T00:00:02+00:00"))
        result = probe.collect_registry_series(2, 1, run_capture=run, sleep=clock.sleep,
                                               monotonic_ns=clock.monotonic_ns,
                                               utc_now=lambda: next(timestamps))
        self.assertEqual(len(calls), 3)
        self.assertEqual(calls[0][0], ["/usr/sbin/ioreg", "-r", "-c", "IOAccelerator", "-d", "1", "-l", "-w0"])
        self.assertTrue(calls[0][1]["check"])
        self.assertEqual([sample["capture_status"] for sample in result["samples"]],
                         ["ok", "capture-failed", "ok"])
        self.assertIsNone(result["samples"][1]["counters"])
        self.assertEqual([sample["elapsed_ns"] for sample in result["samples"]],
                         [0, 1_000_000_000, 2_000_000_000])

    def test_partition_no_double_count(self):
        r = probe.analyze(snapshot())
        self.assertEqual(r["bytes"], {"valid_observed_total": 13824,
                         "exclusive": 5120, "shared": 8192, "unattributed": 512})
        self.assertEqual(r["clients"], [{"ordinal": 1, "exclusive_observed_bytes": 4096},
                                        {"ordinal": 2, "exclusive_observed_bytes": 1024}])
        self.assertEqual(r["allocations"], {"observed": 4, "invalid_size": 0,
                         "exclusive": 2, "shared": 1, "unattributed": 1})
        self.assertNotIn("900001", json.dumps(r))
        self.assertNotIn("900002", json.dumps(r))

    def test_conflicting_queue_owner_revokes_attribution(self):
        s = snapshot()
        s["queues"][1]["client"] = 900002
        r = probe.analyze(s)
        self.assertEqual(r["queues"], {"observed": 3, "resolved": 2})
        self.assertEqual(r["bytes"]["unattributed"], 4608)
        self.assertEqual(r["clients"][0]["exclusive_observed_bytes"], 0)

    def test_unknown_context_and_missing_link(self):
        s = snapshot()
        s["contexts"][0]["client"] = 42
        s["allocations"][2]["queues"].append(99)
        r = probe.analyze(s)
        self.assertEqual(r["contexts"]["resolved"], 1)
        self.assertEqual(r["queues"]["resolved"], 1)
        self.assertEqual(r["bytes"]["unattributed"], 13824)
        self.assertEqual(r["bytes"]["exclusive"], 0)

    def test_invalid_sizes_not_zero_bytes_evidence(self):
        for invalid in (0, -1, True, None, 1.0, 2**64 - 1, 2**64):
            s = snapshot()
            s["allocations"][0]["bytes"] = invalid
            r = probe.analyze(s)
            self.assertEqual(r["allocations"]["invalid_size"], 1)
            self.assertEqual(r["bytes"]["valid_observed_total"], 9728)

    def test_aggregate_overflow(self):
        s = snapshot()
        s["allocations"][0]["bytes"] = 2**64 - 2
        with self.assertRaises(ValueError):
            probe.analyze(s)

    def test_duplicate_identity_and_link(self):
        for group in ("clients", "contexts", "queues", "allocations"):
            s = snapshot()
            s[group].append(copy.deepcopy(s[group][0]))
            with self.assertRaises(ValueError):
                probe.analyze(s)
        s = snapshot()
        s["allocations"][0]["queues"] = [10, 10]
        with self.assertRaises(ValueError):
            probe.analyze(s)

    def test_invalid_schema_and_bounds(self):
        for s in ({}, [], {**snapshot(), "schema": "other"},
                  {**snapshot(), "private": "secret"},
                  {**snapshot(), "clients": [{"id": True}]},
                  {**snapshot(), "clients": [{"id": i + 1} for i in range(probe.MAX_RECORDS + 1)]}):
            with self.assertRaises(ValueError):
                probe.analyze(s)
        s = snapshot()
        s["allocations"][0]["queues"] = list(range(1, probe.MAX_LINKS + 2))
        with self.assertRaises(ValueError):
            probe.analyze(s)

    def test_empty_snapshot(self):
        s = {"schema": probe.SCHEMA, "clients": [], "contexts": [],
             "queues": [], "allocations": []}
        r = probe.analyze(s)
        self.assertEqual(r["bytes"]["valid_observed_total"], 0)
        self.assertEqual(r["clients"], [])
        self.assertEqual(r["allocations"]["observed"], 0)

    def test_registry_text_high_bit_and_duplicates(self):
        raw = "18446744073622759680"
        text = ('"inUseSysMemoryBytes"=' + raw + '\n') * 2
        text += '"inUseVidMemoryBytes"=0, "orphanedReusableSysMemoryBytes"=393453568'
        report = probe.analyze_registry_text(text)["counters"]
        self.assertEqual(report["inUseSysMemoryBytes"]["distinct_values"], [
            {"raw_decimal": raw, "occurrences": 2, "status": "high-bit-set",
             "signed_int64_candidate": "-86791936"}])
        self.assertEqual(report["inUseVidMemoryBytes"]["distinct_values"][0]["raw_decimal"], "0")
        self.assertEqual(report["orphanedNonReusableSysMemoryBytes"]["distinct_values"], [])

    def test_registry_text_boundaries_and_invalid(self):
        text = '\n'.join('"inUseSysMemoryBytes"=' + str(x) for x in
                         (2**63 - 1, 2**63, 2**64 - 1, 2**64, -1, "secret", "1.5"))
        report = probe.analyze_registry_text(text)["counters"]["inUseSysMemoryBytes"]
        self.assertEqual(report["invalid_tokens"], 4)
        self.assertEqual([r["status"] for r in report["distinct_values"]],
                         ["unsigned-observed", "high-bit-set", "all-ones-ambiguous"])
        self.assertNotIn("signed_int64_candidate", report["distinct_values"][-1])
        self.assertNotIn("secret", json.dumps(report))
        with self.assertRaises(ValueError):
            probe.analyze_registry_text(" " * (probe.MAX_INPUT + 1))

    def test_registry_text_cli(self):
        with tempfile.TemporaryDirectory() as directory:
            path = Path(directory) / "registry.txt"
            path.write_text('"inUseSysMemoryBytes"=18446744073622759680')
            cmd = [sys.executable, probe.__file__, "--registry-text", str(path)]
            r = subprocess.run(cmd, capture_output=True)
            self.assertEqual(r.returncode, 0, r.stderr)
            self.assertEqual(json.loads(r.stdout)["schema"], "wex-memory-registry-text-v1")
            path.write_bytes(b"\xff")
            self.assertEqual(subprocess.run(cmd, capture_output=True).returncode, 2)

    def test_cli_and_privacy(self):
        with tempfile.TemporaryDirectory() as directory:
            path = Path(directory) / "memory.json"
            cmd = [sys.executable, probe.__file__, str(path)]
            path.write_text(json.dumps(snapshot()))
            r = subprocess.run(cmd, capture_output=True)
            self.assertEqual(r.returncode, 0, r.stderr)
            self.assertEqual(json.loads(r.stdout)["bytes"]["shared"], 8192)
            self.assertNotIn(b"900001", r.stdout)
            path.write_text(json.dumps({"private": "SECRET"}))
            r = subprocess.run(cmd, capture_output=True)
            self.assertEqual(r.returncode, 2)
            self.assertNotIn(b"SECRET", r.stderr)
            path.write_bytes(b" " * (probe.MAX_INPUT + 1))
            self.assertEqual(subprocess.run(cmd, capture_output=True).returncode, 2)


if __name__ == "__main__":
    unittest.main()
