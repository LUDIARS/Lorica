"""Unit tests for malformed/missing PE metadata; no executable is launched."""
import contextlib
import importlib.util
import io
from pathlib import Path
import struct
import unittest

spec = importlib.util.spec_from_file_location(
    "verify_binary", Path(__file__).resolve().parents[1] / "tools" / "verify_binary.py")
verifier = importlib.util.module_from_spec(spec)
spec.loader.exec_module(verifier)


def pe_fixture(flags=0x4160):
    data = bytearray(64 + 24 + 112)
    data[:2] = b"MZ"
    struct.pack_into("<I", data, 60, 64)
    data[64:68] = b"PE\0\0"
    struct.pack_into("<H", data, 68, 0x8664)
    struct.pack_into("<HH", data, 84, 112, 2)
    struct.pack_into("<H", data, 88, 0x20B)
    struct.pack_into("<H", data, 158, flags)
    return data


class PeFlagsTests(unittest.TestCase):
    def test_present(self):
        with contextlib.redirect_stdout(io.StringIO()):
            verifier.verify_pe(pe_fixture())

    def test_each_missing_flag(self):
        for bit in (0x40, 0x20, 0x100, 0x4000):
            with self.subTest(bit=bit), self.assertRaises(ValueError):
                verifier.verify_pe(pe_fixture(0x4160 & ~bit))

    def test_truncation(self):
        fixture = pe_fixture()
        for length in (0, 63, 64, 87, 199):
            with self.subTest(length=length), self.assertRaises(ValueError):
                verifier.verify_pe(fixture[:length])

    def test_huge_offset(self):
        fixture = pe_fixture()
        struct.pack_into("<I", fixture, 60, 0xFFFFFFFF)
        with self.assertRaises(ValueError):
            verifier.verify_pe(fixture)


if __name__ == "__main__":
    unittest.main()
