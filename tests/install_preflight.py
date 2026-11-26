#!/usr/bin/env python3
"""Host-only tests of read-only OpenCore install preflight."""
import copy
import json
from pathlib import Path
import plistlib
import subprocess
import sys
import tempfile
import unittest

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "tools"))
import install_preflight as probe

GUID = "7C436110-AB2A-4BBB-A880-FE41995C9F82"


def entry(name, **changes):
    return {"BundlePath": name + ".kext", "Enabled": True, "Arch": "Any",
            "MinKernel": "", "MaxKernel": "", **changes}


def config():
    return {"Kernel": {"Add": [entry("Lilu"), entry("AMFIAnchor"),
                              entry("AMFIAnchorInjector"), entry("WhateverXe")]},
            "NVRAM": {"Add": {GUID: {"boot-args": "-allow3d -disablegfxfirmware",
                                    "csr-active-config": bytes.fromhex("03080000")}}},
            "PlatformInfo": {"Generic": {"SystemSerialNumber": "PRIVATE-SERIAL"}}}


def issues(c, target="24.6.0"):
    return set(probe.analyze(c, target)["blocking_findings"])


class PreflightTests(unittest.TestCase):
    def test_standard_config(self):
        r = probe.analyze(config(), "24.6.0")
        self.assertEqual(r["status"], "no-known-config-blockers")
        self.assertEqual(r["blocking_findings"], [])
        self.assertNotIn("PRIVATE-SERIAL", json.dumps(r))

    def test_order_missing_and_duplicates(self):
        c = config()
        entries = c["Kernel"]["Add"]
        entries[0], entries[3] = entries[3], entries[0]
        self.assertIn("lilu-before-whateverxe", issues(c))
        self.assertIn("lilu-before-amfianchor", issues(c))
        c = config()
        c["Kernel"]["Add"].append(entry("WhateverXe"))
        self.assertIn("duplicate-whateverxe", issues(c))
        c = config()
        c["Kernel"]["Add"].pop(2)
        self.assertIn("missing-amfianchorinjector", issues(c))

    def test_kernel_and_arch_filtering(self):
        c = config()
        c["Kernel"]["Add"][3].update(MinKernel="25.0.0")
        self.assertIn("missing-whateverxe", issues(c))
        self.assertEqual(issues(c, "25.0.0"), set())
        c["Kernel"]["Add"][3].update(Arch="i386")
        self.assertIn("missing-whateverxe", issues(c, "25.0.0"))
        c = config()
        c["Kernel"]["Add"].append(entry("WhateverGreen", MaxKernel="23.99.99"))
        self.assertEqual(issues(c), set())
        c["Kernel"]["Add"][-1]["MaxKernel"] = "24.6.0"
        self.assertIn("whatevergreen-conflict", issues(c))

    def test_disabled_conflict_and_amfipass_order(self):
        c = config()
        c["Kernel"]["Add"].append(entry("WhateverGreen", Enabled=False))
        c["Kernel"]["Add"].append(entry("AMFIPass"))
        self.assertEqual(issues(c), set())
        c["Kernel"]["Add"].insert(0, c["Kernel"]["Add"].pop())
        self.assertIn("amfipass-after-anchor", issues(c))

    def test_boot_args_and_sip(self):
        c = config()
        nv = c["NVRAM"]["Add"][GUID]
        nv["boot-args"] = "-allow3d-extra -disablegfxfirmware amfi=0x80"
        nv["csr-active-config"] = bytes(4)
        self.assertEqual(issues(c), {"missing-allow3d", "amfi-disabled", "unexpected-sip"})
        nv["boot-args"] = "-allow3d -disablegfxfirmware amfi_get_out_of_my_way=1"
        self.assertIn("amfi-disabled", issues(c))
        nv["boot-args"] = "-allow3d -disablegfxfirmware ipc_control_port_options=0"
        self.assertIn("ipc-control-port-override", issues(c))

    def test_invalid_config_metadata(self):
        for changes in ({"Enabled": 1}, {"Arch": "unknown"},
                        {"MinKernel": "garbage"}, {"MinKernel": "25.0.0", "MaxKernel": "24.0.0"}):
            c = config()
            c["Kernel"]["Add"][0].update(changes)
            with self.assertRaises(ValueError):
                probe.analyze(c, "24.6.0")
        for version in ("24", "24.6.0.0", "26.0.0", "19.9.9"):
            with self.assertRaises(ValueError):
                probe.analyze(config(), version)

    def test_efi_snapshot_cli_and_privacy(self):
        with tempfile.TemporaryDirectory() as directory:
            p = Path(directory) / "config.plist"
            p.write_bytes(plistlib.dumps(config(), fmt=plistlib.FMT_BINARY))
            cmd = [sys.executable, probe.__file__, str(p), "--darwin", "24.6.0"]
            before = p.read_bytes()
            r = subprocess.run(cmd, capture_output=True)
            self.assertEqual(r.returncode, 0, r.stderr)
            self.assertEqual(before, p.read_bytes())
            self.assertNotIn(b"PRIVATE", r.stdout)
            c = config()
            c["Kernel"]["Add"].append(entry("WhateverGreen"))
            p.write_bytes(plistlib.dumps(c))
            self.assertEqual(subprocess.run(cmd, capture_output=True).returncode, 1)
            p.write_bytes(b"<plist><PRIVATE>")
            r = subprocess.run(cmd, capture_output=True)
            self.assertEqual(r.returncode, 2)
            self.assertNotIn(b"PRIVATE", r.stderr)

    def test_backup_is_separate_and_not_boot_certification(self):
        with tempfile.TemporaryDirectory() as directory:
            p = Path(directory) / "config.plist"
            backup = Path(directory) / "backup.plist"
            p.write_bytes(plistlib.dumps(config()))
            backup.write_bytes(p.read_bytes())
            cmd = [sys.executable, probe.__file__, str(p), "--darwin", "24.6.0", "--backup-config"]
            r = subprocess.run(cmd + [str(backup)], capture_output=True)
            self.assertEqual(r.returncode, 0, r.stderr)
            self.assertEqual(json.loads(r.stdout)["backup"]["status"], "config-readable-not-boot-verified")
            self.assertEqual(subprocess.run(cmd + [str(p)], capture_output=True).returncode, 2)
            backup.write_bytes(b"invalid")
            self.assertEqual(subprocess.run(cmd + [str(backup)], capture_output=True).returncode, 2)


if __name__ == "__main__":
    unittest.main()
