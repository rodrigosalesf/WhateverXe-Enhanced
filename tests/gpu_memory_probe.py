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
