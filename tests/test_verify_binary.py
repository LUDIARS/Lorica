"""Unit tests for the verifier: PE bytes, canned readelf text and the exit code; no artifact is launched."""
import contextlib
import importlib.util
import io
from pathlib import Path
import struct
import subprocess
import sys
import tempfile
import types
import unittest
from unittest import mock

spec = importlib.util.spec_from_file_location(
    "verify_binary", Path(__file__).resolve().parents[1] / "tools" / "verify_binary.py")
verifier = importlib.util.module_from_spec(spec)
spec.loader.exec_module(verifier)


TOOL = Path(__file__).resolve().parents[1] / "tools" / "verify_binary.py"
ELF_LINES = {
    "type": "  Type:                              DYN (Position-Independent Executable file)",
    "stack": "  GNU_STACK      0x000000 0x0000000000000000 0x0000000000000000 0x000000 0x000000 RW  0x10",
    "relro": "  GNU_RELRO      0x002df0 0x0000000000003df0 0x0000000000003df0 0x000210 0x000210 R   0x1",
    "flags": " 0x000000000000001e (FLAGS)              BIND_NOW",
    "flags_1": " 0x000000006ffffffb (FLAGS_1)            Flags: NOW PIE",
}


def verify_elf_text(**changed):
    text = "\n".join(line for line in {**ELF_LINES, **changed}.values() if line)
    with mock.patch.object(verifier.subprocess, "run", return_value=types.SimpleNamespace(stdout=text)), \
            contextlib.redirect_stdout(io.StringIO()):
        verifier.verify_elf(Path("unused"), "readelf")


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

    def test_unsupported_images(self):
        cases = {"signature": (64, "<4s", b"PF\0\0"), "optional size": (84, "<H", 111), "machine": (68, "<H", 0xAA64),
                 "magic": (88, "<H", 0x10B), "dll": (86, "<H", 0x2002), "not executable": (86, "<H", 0)}
        for name, (offset, layout, value) in cases.items():
            fixture = pe_fixture()
            struct.pack_into(layout, fixture, offset, value)
            with self.subTest(name), self.assertRaises(ValueError):
                verifier.verify_pe(fixture)


class ElfTextTests(unittest.TestCase):
    def test_present(self):
        verify_elf_text()
        verify_elf_text(flags="", flags_1=" 0x000000006ffffffb (FLAGS_1)      NOW PIE")  # llvm-readelf

    def test_each_missing_property(self):
        cases = {
            "not PIE": {"type": "  Type:                              EXEC (Executable file)"},
            "shared library": {"flags_1": " 0x000000006ffffffb (FLAGS_1)            Flags: NOW"},
            "executable stack": {"stack": ELF_LINES["stack"].replace("RW ", "RWE")},
            "no GNU_STACK": {"stack": ""},
            "no RELRO": {"relro": ""},
            "lazy binding": {"flags": "", "flags_1": " 0x000000006ffffffb (FLAGS_1)            Flags: PIE"},
        }
        for name, changed in cases.items():
            with self.subTest(name), self.assertRaises(ValueError):
                verify_elf_text(**changed)

    def test_strings_are_not_entries(self):
        # Ordinary linker flags put these texts into RUNPATH and SONAME strings.
        lazy = {"flags": "", "flags_1": " 0x000000006ffffffb (FLAGS_1)            Flags: PIE"}
        cases = {
            "lazy binding": {**lazy, "runpath": " 0x000000000000001d (RUNPATH)            Library runpath: [/opt/(BIND_NOW)/lib]"},
            "no RELRO": {**lazy, "relro": "", "runpath": " 0x000000000000001d (RUNPATH)            Library runpath: [GNU_RELRO (FLAGS) NOW]"},
            "shared library": {"flags_1": " 0x000000006ffffffb (FLAGS_1)            Flags: NOW",
                               "runpath": " 0x000000000000000e (SONAME)             Library soname: [(FLAGS_1) PIE]"},
        }
        for name, changed in cases.items():
            with self.subTest(name), self.assertRaises(ValueError):
                verify_elf_text(**changed)


class ExitCodeTests(unittest.TestCase):
    def run_tool(self, content):
        with tempfile.TemporaryDirectory() as directory:
            path = Path(directory) / "artifact"
            path.write_bytes(content)
            return subprocess.run([sys.executable, str(TOOL), str(path)], capture_output=True).returncode

    def test_exit_codes(self):
        self.assertEqual(self.run_tool(bytes(pe_fixture())), 0)
        self.assertEqual(self.run_tool(bytes(pe_fixture(0))), 1)
        self.assertEqual(self.run_tool(b"not an executable"), 1)


if __name__ == "__main__":
    unittest.main()
