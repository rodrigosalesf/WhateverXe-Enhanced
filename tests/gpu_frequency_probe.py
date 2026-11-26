#!/usr/bin/env python3
"""CPU checks of the offline Xe-LP frequency decoder and report consumer."""
import json
from pathlib import Path
import subprocess
import sys
import tempfile
import unittest

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "tools"))
import gpu_frequency_probe as probe


def snapshot(**words):
    return {"layout": "intel-xe-lp-gen12", **words}


class FrequencyTests(unittest.TestCase):
    def test_known_gen12_register_layout(self):
        # Synthetic 200 MHz RPn, 750 MHz RP1, 1200 MHz RP0.
        # RP1 comes from FREQ_INFO_REC, not the middle byte in STATE_CAP.
        raw = snapshot(rp_state_cap=0x0004ff18, freq_info_rec=0x00000f00,
                       rpstat1=0x0000f805, rpnswreq=0x16802000)
        report = probe.decode(raw)
        self.assertEqual(report["hardware_limits"], {"status": "observed",
                         "rp0_mhz": 1200, "rp1_mhz": 750, "rpn_mhz": 200})
        self.assertEqual(report["actual"], {"status": "observed", "opcode": 31,
                         "mhz_rounded": 517, "relation_to_nominal_limits": "within-rpn-rp0"})
        self.assertEqual(report["register_request"], {"status": "observed", "opcode": 45,
                         "mhz_rounded": 750, "relation_to_nominal_limits": "within-rpn-rp0"})

    def test_rounding_and_field_width(self):
        for code, mhz in ((1, 17), (2, 33), (3, 50), (255, 4250), (256, 4267), (511, 8517)):
            r = probe.decode(snapshot(rpstat1=(code << 11) | 0x800007ff,
                                      rpnswreq=code << 23))
            self.assertEqual(r["actual"]["mhz_rounded"], mhz)
            self.assertEqual(r["register_request"]["mhz_rounded"], mhz)

    def test_zero_missing_and_all_ones_distinct(self):
        r = probe.decode(snapshot(rpstat1=0, rpnswreq=0xffffffff))
        self.assertEqual(r["actual"]["status"], "observed-zero")
        self.assertEqual(r["actual"]["mhz_rounded"], 0)
        self.assertEqual(r["actual"]["relation_to_nominal_limits"], "unavailable")
        self.assertEqual(r["register_request"], {"status": "all-ones"})
        self.assertEqual(probe.decode(snapshot())["actual"], {"status": "missing"})

    def test_invalid_word_types(self):
        for word in (True, None, -1, 1 << 32, "0x12", 3.0):
            r = probe.decode(snapshot(rpstat1=word, rp_state_cap=word))
            self.assertEqual(r["actual"], {"status": "invalid-word"})
            self.assertEqual(r["hardware_limits"]["cap_status"], "invalid-word")

    def test_equal_limits_valid_and_inverted_invalid(self):
        r = probe.decode(snapshot(rp_state_cap=0x00050005, freq_info_rec=0x500))
        self.assertEqual(r["hardware_limits"]["status"], "observed")
        for cap, rec in ((0x00000000, 0), (0x00060005, 0x500),
                         (0x00040005, 0x300), (0x00040005, 0x600)):
            r = probe.decode(snapshot(rp_state_cap=cap, freq_info_rec=rec, rpstat1=0x8000))
            self.assertEqual(r["hardware_limits"]["status"], "inconsistent-limits")
            self.assertEqual(r["actual"]["relation_to_nominal_limits"], "unavailable")

    def test_boundaries_no_clamping(self):
        for code, relation in ((11, "below-rpn"), (12, "within-rpn-rp0"),
                               (72, "within-rpn-rp0"), (73, "above-rp0")):
            r = probe.decode(snapshot(rp_state_cap=0x00040018, freq_info_rec=0xf00,
                                      rpstat1=code << 11, rpnswreq=code << 23))
            for key in ("actual", "register_request"):
                self.assertEqual(r[key]["relation_to_nominal_limits"], relation)
                self.assertEqual(r[key]["opcode"], code)

    def test_no_assumed_layout(self):
        for raw in ({}, [], {"layout": "xe3"}, snapshot(private="secret")):
            with self.assertRaises(ValueError):
                probe.decode(raw)

    def test_cli(self):
        with tempfile.TemporaryDirectory() as directory:
            path = Path(directory) / "snapshot.json"
            cmd = [sys.executable, probe.__file__, str(path)]
            path.write_text(json.dumps(snapshot(rpstat1=0x1800)))
            result = subprocess.run(cmd, capture_output=True)
            self.assertEqual(result.returncode, 0, result.stderr)
            self.assertEqual(json.loads(result.stdout)["actual"]["mhz_rounded"], 50)
            path.write_text(json.dumps(snapshot(private="SECRET")))
            result = subprocess.run(cmd, capture_output=True)
            self.assertEqual(result.returncode, 2)
            self.assertNotIn(b"SECRET", result.stderr)
            path.write_bytes(b" " * (probe.MAX_INPUT + 1))
            self.assertEqual(subprocess.run(cmd, capture_output=True).returncode, 2)


if __name__ == "__main__":
    unittest.main()
