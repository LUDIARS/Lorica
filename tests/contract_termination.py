"""SPEC-LR-VERIFY: a violated enforce/quick_enforce contract must end the child the
specified way (abort after the handler, or an immediate trap with no handler)."""
import os
import signal
import subprocess
import sys

WINDOWS_ABORT = 3
WINDOWS_FASTFAIL = 0xC0000409


def run(binary: str, mode: str) -> subprocess.CompletedProcess:
    # argv only, never a shell; a hung child fails the test.
    return subprocess.run([binary, mode], timeout=15, check=False,
                          capture_output=True, text=True)


def code(result: subprocess.CompletedProcess) -> int:
    return result.returncode & 0xFFFFFFFF if os.name == "nt" else result.returncode


def expect(condition: bool, message: str) -> None:
    if not condition:
        raise SystemExit(message)


def main() -> int:
    binary, semantic = sys.argv[1], sys.argv[2]
    satisfied = run(binary, "--satisfied")
    expect(satisfied.returncode == 0, f"satisfied contract exited {satisfied.returncode}")

    aborted = WINDOWS_ABORT if os.name == "nt" else -signal.SIGABRT
    trapped = {WINDOWS_FASTFAIL} if os.name == "nt" else {-signal.SIGILL, -signal.SIGTRAP}
    for mode in ("--default", "--handler-returns", "--handler-violates"):
        result = run(binary, mode)
        if semantic == "enforce":
            expect(code(result) == aborted, f"{mode}: expected abort, got {code(result)}")
            if mode == "--default":
                expect("checked_index: contract violation: pre (enforce, predicate false): "
                       "index >= 0" in result.stderr,
                       f"default diagnostic missing: {result.stderr!r}")
            if mode == "--handler-returns":
                expect("custom handler: index >= 0 terminating=1" in result.stderr,
                       f"custom handler did not run: {result.stderr!r}")
            if mode == "--handler-violates":
                expect("while handling a contract violation" in result.stderr and
                       "violating_handler: contract violation: contract_assert" in result.stderr,
                       f"re-entry not reported: {result.stderr!r}")
        elif semantic == "quick_enforce":
            expect(code(result) in trapped, f"{mode}: expected trap, got {code(result)}")
            expect(result.stderr == "", f"{mode}: quick_enforce must not run a handler")
        else:
            raise SystemExit(f"unknown semantic {semantic}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
