"""Offline readiness classification; never authorizes kernel hooks."""
import unittest
from hdmi_audio_abi import CONTROLLER, MAIN, FRAMEBUFFER

def readiness(report):
    if not isinstance(report, dict) or report.get("schema") != 1:
        return "invalid-report"
    images = report.get("images")
    targets = {"controller": CONTROLLER, "applehda": MAIN, "framebuffer": FRAMEBUFFER}
    if not isinstance(images, dict) or set(images) != set(targets):
        return "incomplete"
    for name, expected in targets.items():
        image = images[name]
        if not isinstance(image, dict) or image.get("status") != "reference_matches":
            return "blocked"
        symbols = image.get("symbols")
        if not isinstance(symbols, dict) or set(symbols) != set(expected):
            return "blocked"
        if any(symbols[key] != ("prefix_match" if prefix is not None else "symbol_present")
               for key, prefix in expected.items()):
            return "blocked"
    return "reference-only-not-authorized"

def fixture():
    return {"schema": 1, "images": {
        name: {"status": "reference_matches", "symbols": {
            key: "prefix_match" if prefix is not None else "symbol_present"
            for key, prefix in targets.items()}}
        for name, targets in (("controller", CONTROLLER), ("applehda", MAIN),
                              ("framebuffer", FRAMEBUFFER))}}

class Tests(unittest.TestCase):
    def test_reference_only(self):
        self.assertEqual(readiness(fixture()), "reference-only-not-authorized")

    def test_missing(self):
        report = fixture()
        del report["images"]["controller"]
        self.assertEqual(readiness(report), "incomplete")

    def test_each_symbol(self):
        for name in ("controller", "applehda", "framebuffer"):
            for key in fixture()["images"][name]["symbols"]:
                for status in ("missing", "ambiguous", "prefix_mismatch"):
                    report = fixture()
                    report["images"][name]["symbols"][key] = status
                    self.assertEqual(readiness(report), "blocked")

    def test_unavailable(self):
        report = fixture()
        report["images"]["applehda"] = {"status": "unavailable_or_unsupported"}
        self.assertEqual(readiness(report), "blocked")

if __name__ == "__main__":
    unittest.main()
