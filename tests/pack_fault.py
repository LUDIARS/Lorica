"""SPEC-LR-VERIFY: require the exact way a sealed pack child ends, not just any failure.

Usage: pack_fault.py <tests/pack_fault.cpp binary> <mode> access-violation|abort|exit-0
"""
import os
import signal
import subprocess
import sys

# Each ending as (Windows exit code, POSIX return code).
ENDINGS = {
    "access-violation": (0xC0000005, -signal.SIGSEGV),
    "abort": (3, -signal.SIGABRT),
    "exit-0": (0, 0),
}


def main() -> int:
    binary, mode, ending = sys.argv[1:]
    expected = ENDINGS[ending][0 if os.name == "nt" else 1]
    # Sanitizer runtimes would otherwise catch SIGSEGV themselves and exit 1 or 66.
    env = dict(os.environ)
    for name in ("ASAN_OPTIONS", "TSAN_OPTIONS"):
        env[name] = ":".join(filter(None, (env.get(name), "handle_segv=0")))
    # Launch via argv, never a shell. Timeout/missing binary/other failures fail test.
    result = subprocess.run([binary, mode], env=env, timeout=15, check=False)
    actual = result.returncode & 0xFFFFFFFF if os.name == "nt" else result.returncode
    if actual != expected:
        raise SystemExit(f"{mode}: expected {ending} ({expected}), got {actual}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
