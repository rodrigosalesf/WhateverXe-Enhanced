#!/usr/bin/env python3
"""Exercise the real offline lifecycle replay and CLI, not kernel callbacks."""
import json
from pathlib import Path
import subprocess
import sys
import tempfile
import unittest

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "tools"))
import hdmi_hotplug_replay as tool

# ELD version 2, six baseline dwords, one 2-channel LPCM SAD,
# 44.1/48 kHz and 16-bit support. 28 bytes incl. header and padding.
VALID = "10000600601000000000000000000000000000000906010000000000"
OTHER = "10000600601000000000000000000000000000000910010000000000"


def event(kind):
    return {"event": kind}


def sample(epoch, raw=VALID):
    return {"event": "eld", "epoch": epoch, "hex": raw}


class HotplugReplayTests(unittest.TestCase):
    def test_connect_then_sample(self):
        report = tool.replay([event("connect"), sample(1)])
        self.assertEqual(report["state"], "connected")
        self.assertEqual(report["eld_evidence"]["stereo_pcm16_rates_hz"], [44100, 48000])
        self.assertEqual(report["history"][-1]["decision"], "observed")

    def test_disconnect_revoke_and_late_sample(self):
        report = tool.replay([event("connect"), sample(1), event("disconnect"), sample(1)])
        self.assertEqual(report["state"], "disconnected")
        self.assertIsNone(report["eld_evidence"])
        self.assertEqual(report["history"][-1]["decision"], "stale")

    def test_reconnect_different_sink(self):
        report = tool.replay([event("connect"), sample(1), event("disconnect"),
                              event("connect"), sample(1), sample(3, OTHER), sample(1)])
        self.assertIsNone(report["history"][3]["stereo_pcm16_rates_hz"])
        self.assertIsNone(report["history"][4]["stereo_pcm16_rates_hz"])
        self.assertEqual(report["eld_evidence"]["stereo_pcm16_rates_hz"], [96000])
        self.assertEqual(report["history"][-1]["decision"], "stale")

    def test_suspend_and_resume_require_new_connection(self):
        report = tool.replay([event("connect"), sample(1), event("suspend"), sample(2),
                              event("resume"), sample(3), event("connect"), sample(4)])
        self.assertEqual([x["decision"] for x in report["history"]],
                         ["revoked", "observed", "revoked", "inactive",
                          "revoked", "inactive", "revoked", "observed"])
        self.assertEqual(report["eld_evidence"]["stereo_pcm16_rates_hz"], [44100, 48000])

    def test_bad_current_sample_revokes_but_old_bad_sample_does_not(self):
        report = tool.replay([event("connect"), event("connect"), sample(2),
                              sample(1, ""), sample(2, "")])
        self.assertEqual(report["history"][3]["stereo_pcm16_rates_hz"], [44100, 48000])
        self.assertEqual(report["history"][4]["decision"], "invalidated")
        self.assertIsNone(report["eld_evidence"])

    def test_disconnect_during_suspend_does_not_reactivate(self):
        report = tool.replay([event("suspend"), event("disconnect"), sample(2)])
        self.assertEqual(report["state"], "suspended")
        self.assertIsNone(report["eld_evidence"])

    def test_invalid_sequences_and_envelopes(self):
        for events in ([event("resume")], [event("suspend"), event("connect")],
                       [sample(1)], [sample(True)], [sample(0, "aa bb")],
                       [sample(0, "a")], [sample(0, "00" * 4097)],
                       [{"event": "connect", "private": "secret"}],
                       [event("unknown")], [None], [event("disconnect")] * 1025):
            with self.subTest(events=str(events)[:80]):
                with self.assertRaises(tool.ReplayError):
                    tool.replay(events)

    def test_cli_and_privacy(self):
        with tempfile.TemporaryDirectory() as directory:
            path = Path(directory) / "events.json"
            path.write_text(json.dumps([event("connect"), sample(1)]))
            cmd = [sys.executable, tool.__file__, str(path)]
            result = subprocess.run(cmd, capture_output=True)
            self.assertEqual(result.returncode, 0, result.stderr)
            self.assertEqual(json.loads(result.stdout)["epoch"], 1)
            self.assertNotIn(VALID.encode(), result.stdout)
            path.write_text(json.dumps([{"event": "private-secret"}]))
            result = subprocess.run(cmd, capture_output=True)
            self.assertEqual(result.returncode, 2)
            self.assertNotIn(b"private-secret", result.stderr)
            path.write_bytes(b" " * (tool.MAX_INPUT + 1))
            self.assertEqual(subprocess.run(cmd, capture_output=True).returncode, 2)


if __name__ == "__main__":
    unittest.main()
