"""Offline route selection model. Inputs must come from verified hardware evidence."""
import unittest


def select_route(codecs, controller, pin):
    """Return a unique direct digital route, or None. No hardware writes."""
    candidates = [c for c in codecs if c["controller"] == controller
                  and c["vendor"] == 0x8086281C]
    if len(candidates) != 1:
        return None
    codec = candidates[0]
    address = codec.get("address")
    if type(address) is not int or not 0 <= address <= 14:
        return None
    widgets = codec["widgets"]
    target = widgets.get(pin)
    if not target or target["type"] != "pin" or not target["digital"]:
        return None
    routes = set()
    for node in target.get("connections", []):
        widget = widgets.get(node)
        if widget and widget["type"] == "converter" and widget["digital"]:
            routes.add(node)
    if len(routes) != 1:
        return None
    return address, pin, routes.pop()


def fixture():
    return {"controller": "verified-controller", "vendor": 0x8086281C,
            "address": 2, "widgets": {
                4: {"type": "pin", "digital": True, "connections": [3]},
                3: {"type": "converter", "digital": True}}}


class Tests(unittest.TestCase):
    def test_unique(self):
        self.assertEqual(select_route([fixture()], "verified-controller", 4), (2, 4, 3))

    def test_wrong_controller(self):
        self.assertIsNone(select_route([fixture()], "other", 4))

    def test_analog(self):
        codec = fixture()
        codec["vendor"] = 0x10EC0256
        self.assertIsNone(select_route([codec], "verified-controller", 4))

    def test_ambiguous(self):
        self.assertIsNone(select_route([fixture(), fixture()], "verified-controller", 4))
        codec = fixture()
        codec["widgets"][5] = {"type": "converter", "digital": True}
        codec["widgets"][4]["connections"].append(5)
        self.assertIsNone(select_route([codec], "verified-controller", 4))

    def test_missing_address_or_edge(self):
        codec = fixture()
        del codec["address"]
        self.assertIsNone(select_route([codec], "verified-controller", 4))
        codec = fixture()
        codec["widgets"][4]["connections"] = []
        self.assertIsNone(select_route([codec], "verified-controller", 4))


if __name__ == "__main__":
    unittest.main()
