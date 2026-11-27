"""Synthetic thin Mach-O inputs; never treat them as Apple driver evidence."""
import importlib.util
from pathlib import Path
import struct
import tempfile
import unittest

ROOT = Path(__file__).resolve().parents[1]
SPEC = importlib.util.spec_from_file_location("abi", ROOT / "tools/hdmi_audio_abi.py")
abi = importlib.util.module_from_spec(SPEC)
SPEC.loader.exec_module(abi)

NAME = "__ZN18AppleHDAController19edidIsValidForAudioEP6OSDatai"
PREFIX = bytes.fromhex("55 48 89 e5 41 57 41 56 41 55 41 54 53 48 83 ec 38")
VM = 0x100000


def image(names=(NAME,), prefix=PREFIX, section_flags=0x80000400, sec=1, delta=0):
    data = bytearray(1024)
    strings = bytearray(b"\0")
    struct.pack_into("<8I", data, 0, 0xfeedfacf, 0x01000007, 3, 11, 2, 176, 0, 0)
    struct.pack_into("<2I16s4Q4I", data, 32, 0x19, 152, b"__TEXT", VM, 64,
                     512, 64, 7, 5, 1, 0)
    struct.pack_into("<16s16s2Q8I", data, 104, b"__text", b"__TEXT", VM, 64,
                     512, 0, 0, 0, section_flags, 0, 0, 0)
    struct.pack_into("<2I", data, 184, 2, 24)
    data[512:512 + len(prefix)] = prefix
    for index, name in enumerate(names):
        struct.pack_into("<IBBHQ", data, 640 + index * 16, len(strings), 0x0f,
                         sec, 0, VM + delta)
        strings.extend(name.encode() + b"\0")
    struct.pack_into("<4I", data, 192, 640, len(names), 768, len(strings))
    data[768:768 + len(strings)] = strings
    return data


class TestABI(unittest.TestCase):
    def test_reference(self):
        self.assertEqual(abi.CONTROLLER[NAME], PREFIX)
        self.assertEqual(abi.audit(image(), {NAME: PREFIX})[NAME], "prefix_match")
        self.assertEqual(abi.audit(image(), {NAME: None})[NAME], "symbol_present")

    def test_symbol_lookup_accepts_immutable_and_mutable_images(self):
        for data in (bytes(image()), bytearray(image())):
            with self.subTest(image_type=type(data).__name__):
                self.assertEqual(abi.audit(data, {NAME: PREFIX})[NAME], "prefix_match")

    def test_nonmatching(self):
        self.assertEqual(abi.audit(image(prefix=b"\x90"), {NAME: PREFIX})[NAME],
                         "prefix_mismatch")
        self.assertEqual(abi.audit(image(names=("other",)), {NAME: PREFIX})[NAME],
                         "missing")
        self.assertEqual(abi.audit(image(names=(NAME, NAME)), {NAME: PREFIX})[NAME],
                         "ambiguous")

    def test_section_admission(self):
        for data in (image(sec=0), image(sec=2), image(delta=63),
                     image(section_flags=0)):
            self.assertEqual(abi.audit(data, {NAME: PREFIX})[NAME], "invalid_section")

    def test_malformed(self):
        for off, value in ((0, 0xcafebabe), (4, 0x0100000c), (12, 2),
                           (16, 999), (36, 0), (196, 9999999),
                           (200, 640), (640, 9999999)):
            data = image()
            struct.pack_into("<I", data, off, value)
            with self.assertRaises(abi.InvalidImage):
                abi.audit(data, {NAME: PREFIX})
        with self.assertRaises(abi.InvalidImage):
            abi.audit(image()[:520], {NAME: PREFIX})

    def test_file_status(self):
        with tempfile.TemporaryDirectory() as temp:
            path = Path(temp) / "binary"
            self.assertEqual(abi.audit_file(path, {NAME: PREFIX})["status"],
                             "unavailable_or_unsupported")
            path.write_bytes(image())
            report = abi.audit_file(path, {NAME: PREFIX})
            self.assertEqual(report["status"], "reference_matches")
            self.assertEqual(len(report["sha256"]), 64)
            path.write_bytes(image(prefix=b"\x90"))
            self.assertEqual(abi.audit_file(path, {NAME: PREFIX})["status"],
                             "reference_not_matched")


if __name__ == "__main__":
    unittest.main()
