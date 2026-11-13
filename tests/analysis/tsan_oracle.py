"""ThreadSanitizer oracle for the shared-state fixtures (opt-in; needs GCC or Clang
with a working -fsanitize=thread).

Each `// tsan: <race|clean> | <thread 1> | <thread 2>` line of
tests/analysis/fixtures/shared_state/*.cpp becomes a two-thread driver: the fixture,
then `// driver:` lines, then a main that runs `// setup:` lines and starts two
threads behind a relaxed spin gate (no happens-before between them), each running
its expression 1000 times with `i` as the loop index (`i == 0` selects a one-time
action, `pause()` lets the other thread go first). `sink()` consumes a value
through a thread_local volatile, so -O1 cannot delete a racing read. No shared_ptr
or acq_rel atomic is on the path. Each driver runs up to RUNS times: `race` needs a
report in one run, `clean` needs none in all of them.
`not-observable(<reason>)` lines are listed and not run.

Usage: tsan_oracle.py [--compiler g++] [--jobs 2]. Exit 0 all agree, 1 a
disagreement or a fixture that does not build, 77 (skipped) when the compiler cannot
build and run a -fsanitize=thread program.
"""
import argparse
from concurrent.futures import ThreadPoolExecutor
import os
from pathlib import Path
import re
import subprocess
import sys
import tempfile

FIXTURES = Path(__file__).resolve().parent / "fixtures" / "shared_state"
FLAGS = ["-std=c++17", "-O1", "-g", "-fsanitize=thread", "-pthread"]
RUNS = 5
PRELUDE = """#include <algorithm>
#include <atomic>
#include <cerrno>
#include <chrono>
#include <condition_variable>
#include <cstdio>
#include <cstdlib>
#include <cstring>
#include <functional>
#include <iostream>
#include <memory>
#include <mutex>
#include <shared_mutex>
#include <thread>
#include <vector>
"""
MAIN = """
inline void sink(long v) { static thread_local volatile long s; s = v; }
inline void pause() { std::this_thread::sleep_for(std::chrono::milliseconds(20)); }
int main() {
%s
    std::atomic<int> lorica_go{0};
    auto lorica_first = [&] { while (!lorica_go.load(std::memory_order_relaxed)) std::this_thread::yield();
                       for (int i = 0; i < 1000; ++i) { %s; } };
    auto lorica_second = [&] { while (!lorica_go.load(std::memory_order_relaxed)) std::this_thread::yield();
                        for (int i = 0; i < 1000; ++i) { %s; } };
    std::thread lorica_a(lorica_first), lorica_b(lorica_second);
    lorica_go.store(1, std::memory_order_relaxed);
    lorica_a.join();
    lorica_b.join();
}
"""
_MARKER = re.compile(r"^// tsan: (race|clean|not-observable\((.*)\))(?: \| (.+) \| (.+))?\s*$", re.M)


def drivers():
    """[(fixture, expected, source or reason)] for every marker line."""
    out = []
    for path in sorted(FIXTURES.glob("*.cpp")):
        text = path.read_text(encoding="utf-8")
        setup = "\n".join("    " + line for line in re.findall(r"^// setup: (.*)$", text, re.M))
        driver = "\n".join(re.findall(r"^// driver: (.*)$", text, re.M))
        for marker, reason, first, second in _MARKER.findall(text):
            if reason or not first:
                out.append((path.name, "not-observable", reason or marker))
            else:
                out.append((path.name, marker, PRELUDE + text + "\n" + driver + MAIN % (setup, first, second)))
    return out


def run(compiler, work, number, source):
    """'race', 'clean' or 'build failed: ...'."""
    cpp, exe = Path(work, "d%d.cpp" % number), Path(work, "d%d" % number)
    cpp.write_text(source, encoding="utf-8")
    try:
        built = subprocess.run([compiler] + FLAGS + [str(cpp), "-o", str(exe)], capture_output=True, text=True)
    except OSError as error:
        return "build failed: %s" % error
    if built.returncode:
        return "build failed: " + built.stderr.strip().splitlines()[0] if built.stderr else "build failed"
    env = dict(os.environ, TSAN_OPTIONS="halt_on_error=0 report_signal_unsafe=0")
    for _ in range(RUNS):       # a race is seen in any run; clean means clean in every run
        ran = subprocess.run([str(exe)], capture_output=True, text=True, env=env, timeout=300)
        if "WARNING: ThreadSanitizer" in ran.stderr:
            return "race"
        if ran.returncode:
            return "failed with exit status %d" % ran.returncode
    return "clean"


def main(argv=None):
    parser = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    parser.add_argument("--compiler", default="g++")
    parser.add_argument("--jobs", type=int, default=2)
    args = parser.parse_args(argv)
    with tempfile.TemporaryDirectory() as work:
        probe = run(args.compiler, work, 0, "int main() {}\n")
        if probe != "clean":
            print("skipped: %s cannot build and run -fsanitize=thread programs (%s)" % (args.compiler, probe))
            return 77
        cases = drivers()
        runnable = [(k, c) for k, c in enumerate(cases, 1) if c[1] != "not-observable"]
        with ThreadPoolExecutor(max_workers=max(1, args.jobs)) as pool:
            observed = dict(zip((k for k, _ in runnable),
                                pool.map(lambda kc: run(args.compiler, work, kc[0], kc[1][2]), runnable)))
    disagreements = 0
    for k, (fixture, expected, detail) in enumerate(cases, 1):
        if expected == "not-observable":
            print("not run   %-36s %s" % (fixture, detail))
            continue
        agree = observed[k] == expected
        disagreements += not agree
        print("%s %-36s expected %-5s observed %s" % ("agree    " if agree else "DISAGREE ", fixture,
                                                         expected, observed[k]))
    print("drivers %d, agree %d, disagree %d, not run %d" % (
        len(runnable), len(runnable) - disagreements, disagreements, len(cases) - len(runnable)))
    return 1 if disagreements else 0


if __name__ == "__main__":
    sys.exit(main())
