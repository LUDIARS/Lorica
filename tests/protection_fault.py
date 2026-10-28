"""SPEC-LR-VERIFY: require the OS write-denial result, not just any failed child."""
import os
import signal
import subprocess
import sys


def main() -> int:
    # Launch via argv, never a shell. Timeout/missing binary/other failures fail test.
    result = subprocess.run([sys.argv[1], "--write"], timeout=15, check=False)
    expected = 0xC0000005 if os.name == "nt" else -signal.SIGSEGV
    actual = result.returncode & 0xFFFFFFFF if os.name == "nt" else result.returncode
    if actual != expected:
        raise SystemExit(f"Expected write protection fault {expected}, got {actual}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
