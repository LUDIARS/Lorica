"""SPEC-LR-VERIFY: require the extended profile's stop, not just any failed child.

Usage: hardening_fault.py <tests binary> fortified|unfortified
The hardened standard library must stop an out-of-range element access and an
empty optional's dereference; with fortified, glibc's _FORTIFY_SOURCE=3 must stop a
copy past a heap buffer of run-time size, with glibc's own message. A normal exit,
another error, another check's stop or a timeout fails.
"""
import os
import signal
import subprocess
import sys

# libstdc++ assertions and glibc's fortify checks abort; libc++ hardening traps.
# The MSVC STL fails fast with STATUS_STACK_BUFFER_OVERRUN.
if os.name != "nt":
    POSIX_STOPS = {-signal.SIGABRT, -signal.SIGILL, -signal.SIGTRAP}
WINDOWS_STOP = 0xC0000409


def stopped(binary, mode, argument, message=None):
    # Launch via argv, never a shell. Timeout/missing binary fail the test.
    result = subprocess.run([binary, mode, argument], timeout=15, check=False,
                            stdout=subprocess.DEVNULL, stderr=subprocess.PIPE)
    if os.name == "nt":
        ok = result.returncode & 0xFFFFFFFF == WINDOWS_STOP
    else:
        ok = result.returncode in POSIX_STOPS
    # A stop by another check (the stack protector, a heap consistency abort)
    # must not count for the one under test.
    if ok and message is not None:
        ok = message in result.stderr
    return ok, result.returncode


def main() -> int:
    binary, fortification = sys.argv[1], sys.argv[2]
    if fortification not in ("fortified", "unfortified"):
        raise SystemExit(f"unknown fortification {fortification!r}")
    normal = subprocess.run([binary], timeout=15, check=False)
    if normal.returncode != 0:
        raise SystemExit(f"in-range run failed with {normal.returncode}")
    checks = [("--element", "x", None), ("--empty-optional", "x", None)]
    if fortification == "fortified" and os.name != "nt":
        checks.append(("--copy", "x" * 64, b"buffer overflow detected"))
    for mode, argument, message in checks:
        ok, code = stopped(binary, mode, argument, message)
        if not ok:
            raise SystemExit(f"{mode} was not stopped by the extended profile (exit {code})")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
