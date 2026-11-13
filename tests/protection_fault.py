"""SPEC-LR-VERIFY: require the OS write-denial result, not just any failed child."""
import os
import signal
import subprocess
import sys


def main() -> int:
    # Launch via argv, never a shell. Timeout/missing binary/other failures fail test.
    # The child handles SIGSEGV itself; sanitizer runtimes must not intercept it first.
    env = dict(os.environ)
    for name in ("ASAN_OPTIONS", "TSAN_OPTIONS"):
        env[name] = ":".join(filter(None, (env.get(name), "handle_segv=0")))
    result = subprocess.run(sys.argv[1:3], timeout=15, check=False, env=env)
    expected = 0xC0000005 if os.name == "nt" else -signal.SIGSEGV
    actual = result.returncode & 0xFFFFFFFF if os.name == "nt" else result.returncode
    if actual != expected:
        raise SystemExit(f"Expected write protection fault {expected}, got {actual}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
