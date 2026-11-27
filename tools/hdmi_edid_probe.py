"""Offline EDID audio capability probe. No kernel or hardware access."""
import unittest

def audio_caps(data):
    if len(data) < 128 or data[:8] != bytes.fromhex("00ffffffffffff00"):
        raise ValueError("invalid EDID header")
    if len(data) != 128 * (1 + data[126]):
        raise ValueError("invalid EDID length")
    basic = False
    descriptors = []
    for offset in range(0, len(data), 128):
        block = data[offset:offset+128]
        if sum(block) % 256:
            raise ValueError("invalid checksum")
        if offset == 0 or block[0] != 2 or block[1] < 3:
            continue
        end = block[2]
        if end == 0:
            continue
        if not 4 <= end <= 127:
            raise ValueError("invalid CTA offset")
        basic |= bool(block[3] & 64)
        pos = 4
        while pos < end:
            tag, size = block[pos] >> 5, block[pos] & 31
            pos += 1
            if pos + size > end:
                raise ValueError("truncated CTA block")
            if tag == 1:
                if not size or size % 3:
                    raise ValueError("invalid audio block")
                for i in range(pos, pos+size, 3):
                    descriptors.append(tuple(block[i:i+3]))
            pos += size
    return basic, tuple(descriptors)

def fixture(payload=b"", flags=0):
    base = bytearray(128)
    base[:8] = bytes.fromhex("00ffffffffffff00")
    base[126] = 1
    base[127] = -sum(base) % 256
    ext = bytearray(128)
    ext[:4] = bytes((2,3,4+len(payload),flags))
    ext[4:4+len(payload)] = payload
    ext[127] = -sum(ext) % 256
    return bytes(base+ext)

class Tests(unittest.TestCase):
    def test_audio(self):
        self.assertEqual(audio_caps(fixture(bytes((35,9,7,1)),64)), (True,((9,7,1),)))
    def test_no_audio(self):
        self.assertEqual(audio_caps(fixture()), (False,()))
    def test_basic_only(self):
        self.assertEqual(audio_caps(fixture(flags=64)), (True,()))
    def test_invalid(self):
        good = fixture()
        for bad in (good[:-1], good[:-1]+bytes((good[-1]^1,)), fixture(bytes((35,9))), fixture(bytes((34,9,7)))):
            with self.subTest(bad=bad):
                with self.assertRaises(ValueError):
                    audio_caps(bad)

if __name__ == "__main__":
    unittest.main()
