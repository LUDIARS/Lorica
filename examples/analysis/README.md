# Complexity gate on an unchanged source

`sample.cpp` stands for a consumer's code. `parse_flags` is deliberately over the
limit. The analyser reads the file as text: nothing is compiled, executed or
edited. The commands run from this directory; the blocks below are checked
against the real output by `tests/analysis/test_example.py`.

A threshold run fails (exit status 1) and names the lines that contributed:

```console
$ python3 ../../tools/lorica_analyze.py complexity sample.cpp --max-cognitive 10
lorica-analyze complexity: files 1, functions analysed 3, unparsed regions 0, lines not analysed 0
FAIL sample.cpp:11 parse_flags: cognitive 11 > 10
    line 13: +1 for
    line 14: +2 if (nesting 1)
    line 15: +3 if (nesting 2)
    line 15: +1 &&
    line 18: +1 else if
    line 18: +1 ||
    line 20: +1 else if
    line 22: +1 else
result: fail, findings 1, suppressed 0
$ echo $?
1
```

Adopting the gate on existing code: record a baseline once, commit it, and the
same limit passes until a function gets worse or a new function exceeds it:

```console
$ python3 ../../tools/lorica_analyze.py complexity sample.cpp --write-baseline analysis-baseline.json
lorica-analyze complexity: files 1, functions analysed 3, unparsed regions 0, lines not analysed 0
result: pass, findings 0, suppressed 0
$ python3 ../../tools/lorica_analyze.py complexity sample.cpp --max-cognitive 10 --baseline analysis-baseline.json
lorica-analyze complexity: files 1, functions analysed 3, unparsed regions 0, lines not analysed 0
result: pass, findings 0, suppressed 0
$ echo $?
0
```

Every metric of every function, with `--all` (`--json` for a machine-readable report):

```console
$ python3 ../../tools/lorica_analyze.py complexity sample.cpp --all
lorica-analyze complexity: files 1, functions analysed 3, unparsed regions 0, lines not analysed 0
cyclomatic  cognitive  nesting  parameters  nloc  function
         3          2        1           1     4  sample.cpp:6 clamp_percent
         8         11        3           1    17  sample.cpp:11 parse_flags
         2          1        1           1     5  sample.cpp:29 checksum
result: pass, findings 0, suppressed 0
```

In a CMake project the gate is an ordinary test. Lorica's own build runs this
example twice, as `lorica.analysis.example.over_threshold` (expected to fail) and
`lorica.analysis.example.baseline` (`tests/analysis/CMakeLists.txt`). A consumer:

```cmake
add_test(NAME myapp.complexity COMMAND ${Python3_EXECUTABLE}
    ${LORICA_SOURCE_DIR}/tools/lorica_analyze.py complexity --strict
    --max-cognitive 15 --max-cyclomatic 10
    --baseline ${CMAKE_CURRENT_SOURCE_DIR}/analysis-baseline.json
    ${CMAKE_CURRENT_SOURCE_DIR}/src)
```

A single function can be exempted, with a reason, on its declaration line:
`int legacy(int x) { // lorica-analyze: ignore(cognitive) generated table, reviewed`.

## Shared state and synchronization

`shared.cpp` stands for code that worker threads share. The `shared-state`
subcommand lists every non-const global, static and member with the locks held at
each access (the `synchronization` column) and gives each function a `sharing`
value; it states what it could not resolve as `unknown`, never as safe. Without a
threshold it only reports. A finding kind fails the run once it has a limit:

```console
$ python3 ../../tools/lorica_analyze.py shared-state shared.cpp --max-inconsistent-locking 0 --max-unsynchronized 0
lorica-analyze shared-state: files 1, functions analysed 8, data 8, unparsed regions 0, lines not analysed 0
FAIL shared.cpp:7 failures: unsynchronized 1 > 0
    (global long: synchronization missing, unsynchronized; accesses: 32 rmw {} serve)
FAIL shared.cpp:15 registry::hits_: inconsistent-locking 1 > 0
    (member int: synchronization inconsistent, inconsistent-locking; accesses: 21 rmw {m_} add; 22 read {} peek)
result: fail, findings 2, suppressed 0
$ echo $?
1
```

`failures` needs `std::atomic<long>` or a lock; `peek()` must take `m_` as `add()`
does. To adopt the gate on existing code, record a baseline and only new or worse
findings fail:

```console
$ python3 ../../tools/lorica_analyze.py shared-state shared.cpp --write-baseline shared-state-baseline.json
lorica-analyze shared-state: files 1, functions analysed 8, data 8, unparsed regions 0, lines not analysed 0
result: pass, findings 0, suppressed 0
$ python3 ../../tools/lorica_analyze.py shared-state shared.cpp --max-inconsistent-locking 0 --max-unsynchronized 0 --baseline shared-state-baseline.json
lorica-analyze shared-state: files 1, functions analysed 8, data 8, unparsed regions 0, lines not analysed 0
result: pass, findings 0, suppressed 0
$ echo $?
0
```

The table, with `--all` (one row per datum, then per function; `--json` has every
access as a `contributions` entry):

```console
$ python3 ../../tools/lorica_analyze.py shared-state shared.cpp --all
lorica-analyze shared-state: files 1, functions analysed 8, data 8, unparsed regions 0, lines not analysed 0
inconsistent-locking  unsynchronized  write-under-shared-lock  reference-escapes-lock  const-writes-mutable  lock-not-held  relaxed-publication  invalid-order  fence-without-atomic  mt-unsafe-call  unknown  function
                   0               0                        0                       0                     0              0                    0              0                     0               0        0  shared.cpp:6 served (global std::atomic<long>: synchronization atomic:relaxed; accesses: 30 atomic {} serve)
                   0               1                        0                       0                     0              0                    0              0                     0               0        0  shared.cpp:7 failures (global long: synchronization missing, unsynchronized; accesses: 32 rmw {} serve)
                   0               0                        0                       0                     0              0                    0              0                     0               0        0  shared.cpp:8 depth (global int: synchronization not-needed (thread_local); accesses: 31 rmw {} serve; 33 rmw {} serve)
                   0               0                        0                       0                     0              0                    0              0                     0               0        0  shared.cpp:10 port (global int: synchronization not-needed (read-only in the analysed set); accesses: 27 read {} configured_port)
                   0               0                        0                       0                     0              0                    0              0                     0               0        0  shared.cpp:14 registry::name_ (member std::string: synchronization lock:m_; accesses: 19 write {m_} rename; 20 read {m_} name)
                   1               0                        0                       0                     0              0                    0              0                     0               0        0  shared.cpp:15 registry::hits_ (member int: synchronization inconsistent, inconsistent-locking; accesses: 21 rmw {m_} add; 22 read {} peek)
                   0               0                        0                       0                     0              0                    0              0                     0               0        0  shared.cpp:16 registry::size_ (member int: synchronization caller-must-synchronize; accesses: 23 rmw {} grow)
                   0               0                        0                       0                     0              0                    0              0                     0               0        1  shared.cpp:17 registry::total_ (member int: synchronization unknown (lockset unknown at line 24); accesses: 24 write ? reset)
                   0               0                        0                       0                     0              0                    0              0                     0               0        0  shared.cpp:19 registry::rename (sharing self-synchronized(unverified))
                   0               0                        0                       0                     0              0                    0              0                     0               0        0  shared.cpp:20 registry::name (sharing self-synchronized(unverified))
                   0               0                        0                       0                     0              0                    0              0                     0               0        0  shared.cpp:21 registry::add (sharing self-synchronized(unverified))
                   0               0                        0                       0                     0              0                    0              0                     0               0        0  shared.cpp:22 registry::peek (sharing thread-hostile; registry::hits_ line 22: inconsistent-locking)
                   0               0                        0                       0                     0              0                    0              0                     0               0        0  shared.cpp:23 registry::grow (sharing caller-synchronized:write)
                   0               0                        0                       0                     0              0                    0              0                     0               0        1  shared.cpp:24 registry::reset (sharing unknown; registry::total_ line 24: lockset unknown at line 24)
                   0               0                        0                       0                     0              0                    0              0                     0               0        0  shared.cpp:27 configured_port (sharing no-shared-state)
                   0               0                        0                       0                     0              0                    0              0                     0               0        0  shared.cpp:29 serve (sharing thread-hostile; failures line 32: unsynchronized)
result: pass, findings 0, suppressed 0
```

Each limit is `--max-<finding> N`; `--max-unknown 0` also fails on anything the
tool could not resolve. A datum is exempted on its declaration line, with a reason:
`long failures = 0; // lorica-analyze: ignore(unsynchronized) written before the workers start`.
No result here proves the absence of a data race; `lock:` means consistent in the
analysed files. Use ThreadSanitizer and Clang `-Wthread-safety` for evidence.

## constexpr: what the compiler tolerates, and what a witness verifies

`constexpr_sample.hpp` holds functions none of which is declared constexpr. The
`constexpr` subcommand inserts the specifier in a temporary copy of the tree (never
in these files) and asks GCC or Clang. Accepting the specifier is only a necessary
condition; a function is verified only when a *witness* (a `static_assert` or a
constexpr variable that calls it) compiles with the change and fails without it.

Without a compiler nothing is tried; the locator lists what it can state as fact:

```console
$ python3 ../../tools/lorica_analyze.py constexpr constexpr_sample.hpp constexpr_sample.cpp --all
lorica-analyze constexpr: files 2, functions analysed 5, unparsed regions 0, lines not analysed 0
functions not declared constexpr: 7 (tried 0, excluded 2); already constexpr 0; variables are not analysed
nothing was compiled (no --compiler and no --compile-commands): no function is reported as rejected, accepted or witnessed
not tried: 5
    not tried constexpr_sample.hpp:7 scaled
    not tried constexpr_sample.hpp:10 address_of
    not tried constexpr_sample.hpp:13 checked_divide
    not tried constexpr_sample.hpp:22 now_seconds
    not tried constexpr_sample.hpp:26 twice (hidden: template)
excluded (not tried): 2
    1 defined in a source file with external linkage: constexpr implies inline, so the definition would have to move to a header, which changes linkage and exported symbols
    1 main cannot be constexpr
    excluded constexpr_sample.cpp:4 parse_level: defined in a source file with external linkage: constexpr implies inline, so the definition would have to move to a header, which changes linkage and exported symbols
    excluded constexpr_sample.cpp:6 main: main cannot be constexpr
result: pass, findings 0, suppressed 0
```

With GCC at C++17 and C++20 and the witnesses in `constexpr-witnesses.json` (keys as
in a baseline). `scaled` is witnessed; `address_of` is accepted by GCC but its witness
does not compile (it is never constant); `checked_divide` needs C++20 and has no
witness; `now_seconds` is rejected; the template is hidden, since every compiler
accepts the specifier on one. This block is skipped where `g++` is absent; lines
ending in `...` depend on the compiler version:

```console
$ python3 ../../tools/lorica_analyze.py constexpr constexpr_sample.hpp constexpr_sample.cpp --compiler g++ --std 17 --std 20 --witnesses constexpr-witnesses.json
lorica-analyze constexpr: files 2, functions analysed 5, unparsed regions 0, lines not analysed 0
functions not declared constexpr: 7 (tried 5, excluded 2); already constexpr 0; variables are not analysed
tried g++ ...
tried g++ ...
constexpr_sample.hpp:7 scaled: witnessed everywhere
    witnessed g++ c++17, c++20: witness compiled in constexpr_sample.cpp and fails without the change
constexpr_sample.hpp:10 address_of: accepted at most (not verified)
    accepted g++ c++17, c++20: necessary condition only, not verified: the witness does not compile: lorica-witness:2: ...
constexpr_sample.hpp:13 checked_divide: accepted at most (not verified)
    rejected g++ c++17: constexpr_sample.hpp:14: ...
    accepted g++ c++20: necessary condition only, not verified: no witness
constexpr_sample.hpp:22 now_seconds: rejected everywhere
    rejected g++ c++17, c++20: constexpr_sample.hpp:22: ...
hidden: 1 (template 1); --show-hidden lists them
excluded (not tried): 2 (--all lists them)
    1 defined in a source file with external linkage: constexpr implies inline, so the definition would have to move to a header, which changes linkage and exported symbols
    1 main cannot be constexpr
result: pass, findings 0, suppressed 0
$ echo $?
0
```

Used as an assertion: `--max-witnessed 0` fails while a function proven convertible
is not declared constexpr. `--emit-patch FILE` writes a unified diff of the results
witnessed in every configuration; nothing is ever applied:

```console
$ python3 ../../tools/lorica_analyze.py constexpr constexpr_sample.hpp constexpr_sample.cpp --compiler g++ --std 20 --witnesses constexpr-witnesses.json --max-witnessed 0 --emit-patch witnessed.diff
lorica-analyze constexpr: files 2, functions analysed 5, unparsed regions 0, lines not analysed 0
FAIL constexpr_sample.hpp:7 scaled: witnessed 1 > 0
functions not declared constexpr: 7 (tried 5, excluded 2); already constexpr 0; variables are not analysed
tried g++ ...
constexpr_sample.hpp:7 scaled: witnessed everywhere
    witnessed g++ c++20: witness compiled in constexpr_sample.cpp and fails without the change
constexpr_sample.hpp:10 address_of: accepted at most (not verified)
    accepted g++ c++20: necessary condition only, not verified: the witness does not compile: lorica-witness:2: ...
constexpr_sample.hpp:13 checked_divide: accepted at most (not verified)
    accepted g++ c++20: necessary condition only, not verified: no witness
constexpr_sample.hpp:22 now_seconds: rejected everywhere
    rejected g++ c++20: constexpr_sample.hpp:22: ...
hidden: 1 (template 1); --show-hidden lists them
excluded (not tried): 2 (--all lists them)
    1 defined in a source file with external linkage: constexpr implies inline, so the definition would have to move to a header, which changes linkage and exported symbols
    1 main cannot be constexpr
result: fail, findings 1, suppressed 0
$ echo $?
1
```

On a CMake project, export `compile_commands.json` and name the headers to try:
`python3 tools/lorica_analyze.py constexpr include src --compile-commands
build/compile_commands.json --std 17 --std 20 --witnesses constexpr-witnesses.json`.
A function kept deliberately non-constexpr carries
`// lorica-analyze: ignore(constexpr) <reason>` on its declaration line. The durable
proof is the witness itself, as a `static_assert` in a test every CI compiler builds.
