"""Inspect selected executable mitigation metadata; never execute the artifact.

This cannot prove every object was instrumented or establish memory safety.
Only PE32+ x64 and ELF executables are supported. Python standard library only.
"""
import argparse
import os
from pathlib import Path
import re
import struct
import subprocess
import sys


def verify_pe(data):
    if len(data) < 64:
        raise ValueError("truncated DOS header")
    pe = struct.unpack_from("<I", data, 60)[0]
    if pe > len(data) - 24 or data[pe:pe + 4] != b"PE\0\0":
        raise ValueError("invalid PE header")
    machine, = struct.unpack_from("<H", data, pe + 4)
    optional_size, characteristics = struct.unpack_from("<HH", data, pe + 20)
    optional = pe + 24
    if optional_size < 112 or optional_size > len(data) - optional:
        raise ValueError("truncated PE optional header")
    magic, = struct.unpack_from("<H", data, optional)
    if machine != 0x8664 or magic != 0x20B or characteristics & 0x2000 or not characteristics & 2:
        raise ValueError("only x64 PE32+ executables are supported")
    flags, = struct.unpack_from("<H", data, optional + 70)
    required = {"ASLR": 0x40, "high-entropy ASLR": 0x20, "NX": 0x100, "CFG marker": 0x4000}
    missing = [name for name, mask in required.items() if not flags & mask]
    if missing:
        raise ValueError("missing PE flags: " + ", ".join(missing))
    print("PE mitigation flags present (CFG tables/instruction coverage not verified)")


def verify_elf(path, readelf):
    result = subprocess.run(
        [readelf, "--wide", "--file-header", "--program-headers", "--dynamic", str(path)],
        text=True, encoding="utf-8", errors="replace", capture_output=True,
        check=True, timeout=30, env={**os.environ, "LC_ALL": "C"})
    output = result.stdout
    if not re.search(r"Type:\s+DYN\b", output):
        raise ValueError("executable is not position independent")
    # FLAGS_1 PIE distinguishes an executable from an ordinary shared library.
    if not re.search(r"\(FLAGS_1\).*\bPIE\b", output):
        raise ValueError("ELF PIE executable marker missing")
    stack = next((line.split() for line in output.splitlines() if line.lstrip().startswith("GNU_STACK")), None)
    if not stack or "E" in "".join(stack[6:-1]):
        raise ValueError("non-executable GNU_STACK required")
    if "GNU_RELRO" not in output or not re.search(r"\(BIND_NOW\)|\((?:FLAGS|FLAGS_1)\).*\b(?:BIND_NOW|NOW)\b", output):
        raise ValueError("full RELRO requires GNU_RELRO and immediate binding")
    print("ELF PIE/NX-stack/full-RELRO metadata present (instruction coverage not verified)")


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("binary", type=Path)
    parser.add_argument("--readelf", default="readelf", help="trusted readelf executable")
    args = parser.parse_args()
    path = args.binary.resolve(strict=True)
    with path.open("rb") as stream:
        magic = stream.read(4)
        stream.seek(0)
        if magic[:2] == b"MZ":
            # Restrict input allocation; this is an artifact inspector, not a public parser.
            if path.stat().st_size > 256 * 1024 * 1024:
                raise ValueError("PE inspection limit is 256 MiB")
            verify_pe(stream.read())
        elif magic == b"\x7fELF":
            verify_elf(path, args.readelf)
        else:
            raise ValueError("unsupported executable format")


if __name__ == "__main__":
    try:
        main()
    except (OSError, ValueError, struct.error, subprocess.SubprocessError) as error:
        print(f"Lorica verification failed: {error}", file=sys.stderr)
        sys.exit(1)
