# Verification plan {#SPEC-LR-VERIFY}

Do not infer execution from the presence of tests. Initial implementation review
must record configure/build and executed tests separately. Run test commands only
with the applicable execution authorization.

Single-config generators (Makefiles, Ninja) take the configuration at configure
time: on Linux add `-DCMAKE_BUILD_TYPE=Release` (and repeat with Debug), or the
`--config`/`-C` options below select nothing and the optimized checks do not run.

```sh
cmake -S . -B build-test -DLORICA_BUILD_TESTS=ON -DLORICA_BUILD_EXAMPLES=ON
cmake --build build-test --config Release
ctest --test-dir build-test -C Release --output-on-failure
cmake -S . -B build-fuzz -DCMAKE_CXX_COMPILER=clang++ -DLORICA_BUILD_FUZZER=ON
cmake --build build-fuzz
build-fuzz/lorica_boundary_fuzz -max_total_time=60
```

Boundary coverage includes SIZE_MAX/zero/exact-end arithmetic; null/empty/exact-end
views; huge offsets; each budget dimension; unchanged state on rejection; exact
depth limit. `lorica.boundary` is built as strict C++17. A view shorter than its
maximum over an exact-size constant array proves at compile time that `at` does
not read past the view; a partial charge is checked in every dimension; the budget
must not be copyable. Tests use explicit abort checks so Release cannot disable
assertions.
Fuzzing supplements these cases; it cannot prove absence of vulnerabilities.

## Checked APIs, extended profile and unsafe API rejection

| Test | Checks |
| --- | --- |
| `lorica.checked.cxx20`, `lorica.checked.cxx23` | `tests/checked.cpp` as C++20 and as C++23: integer, text and reader contracts as compile-time and run-time checks; every pair of 8-bit operands against the exact result in a wider type, and boundary cases of 32- and 64-bit types; that bool/character types, mixed operand types and explicit template arguments for all seven binary functions, `narrow` and `saturate_cast` (also next to `byte_view.hpp`'s `size_t` overloads), temporary and read-only destinations, arrays of unknown bound, `nullptr` and a temporary container for `byte_reader` do not compile; array sources by extent, a null pointer source, overlapping copies, formatted output holding a terminator, a throwing formatter, 4- and 8-byte reads. Built with the unsafe API rejection and the extended profile where supported |
| `lorica.checked.format.cxx20`, `lorica.checked.format.cxx23` | The same executables with an argument: pass where the library defines `__cpp_lib_format`, otherwise reported as skipped (exit 77), so the `format_into` checks are never counted as passed without running |
| `lorica.checked.runtime_format` | `tests/run_build_probe.cmake` builds a `format_into` call with a run-time `std::string` format, which must fail with "constant expression" (CWE-134); skipped where the library has no `<format>` |
| `lorica.profiles.*` | Native Linux Ninja/Makefile consumers: configure, compile and compare C/C++ commands for baseline (executable, shared and static library), direct EXTENDED, repeated calls and promotion, and each target's link options and PIC (full RELRO and NX stack for linked binaries, PIE for executables). The ordered `-U`/`-D` pairs must follow a toolchain's `-U_GLIBCXX_ASSERTIONS`. In Release, baseline must request FORTIFY 3 whenever the compiler itself reports level 3 at `-O2`, whatever Lorica's probes say. Single-config runs cover Release, Debug, empty, RelWithDebInfo and MinSizeRel. Simulated missing flag, lower libc level, unknown CPU, older compiler, 32-bit ABI, missing standard-library hardening and missing zero initialization, plus a real Release `-O0` override, check baseline continuation and explicit EXTENDED refusal; a second flag scope (Release `-O0`, an unknown flag) must not reuse the outer result. Multi-config commands are checked separately per generated configuration. `harness_control` injects nothing and must be reported as an unexpectedly successful strict configuration |
| `lorica.hardening_stops` | `tests/hardening.cpp` built with EXTENDED, driven by `tests/hardening_fault.py`: an in-range run exits 0; an out-of-range `operator[]` and an empty `optional`'s value must stop the child (POSIX SIGABRT/SIGILL/SIGTRAP, Windows 0xC0000409). In optimized Linux configurations the build must have `_FORTIFY_SOURCE` 3 (checked at compile time) and a `memcpy` past a heap buffer of run-time size, which only level 3 sees, must stop with glibc's "buffer overflow detected"; a stop by the stack protector or the heap's own checks does not count. Under AddressSanitizer, which reports that copy first, the FORTIFY part is not checked (configuration says so). A normal exit, another error or a timeout fails. `lorica.hardening_stops.harness_control` (POSIX): a child that exits 1 instead of stopping must be reported |
| `lorica.unsafe_api.*` | `tests/unsafe_api_probes.cmake`: real targets, hardened and built with `-Wno-error` so only Lorica's promotion makes the error, with `lorica_deprecate_unsafe_apis` applied, each built by `tests/run_build_probe.cmake`, which judges by exit code and compiler output, not generator text. Bounded code must build; a direct `std::strcpy` call, a function pointer to it, a macro alias of `std::sprintf`, a parenthesized `::wcscat`, a `-D` alias of `std::strcat`, `std::vsprintf`, `std::wcscpy`, a `strcpy` in a header that arrives only through a linked target's precompiled header, and (GCC/Clang) a call inside a `[[deprecated]]` function and one under a later `-Wno-deprecated-declarations` must fail with the Lorica diagnostic; an earlier `-include` of `<cstring>`, `<cstdio>` or `<cwchar>` must fail with the header's order error. The probes live in CMake, not a C++ source, because they are deliberately unsafe. Controls: `harness_reject_built` and `harness_reject_diagnostic` must be reported by the runner as a built probe and as a missing diagnostic |
| `lorica.unsafe_api.refusals`, `lorica.build_refusals` | `tests/build_refusals.cmake` configures small projects. LR-BUILD-04: precompiled headers (own or `REUSE_FROM`), a C source or a source with `LANGUAGE C`, added after the call, MinGW and a non-Linux system (simulated) must fail configuration with the refusal; (GCC/Clang) a C source added through a generator expression or a linked target must fail the build with the header's `#error`, and Clang with glibc 2.40+ (simulated) must be refused. LR-BUILD-01/02: a missing, INTERFACE, IMPORTED, ALIAS or custom target, an unknown argument, an unknown platform, a C-only project, injection without, with an empty or an unknown target list, an unknown profile and a removed request must fail configuration with the refusal; injection of two targets must apply the default profile to both, and, where supported, the extended profile and the rejection to both. `lorica.build_refusals.harness_control` must report a case that was accepted |
| `lorica.hardening_applied` | Lorica's own libraries and the test targets that depend on a profile carry it (generator-time target properties) |
| `lorica.verify_binary.*` | `unit`: `tests/test_verify_binary.py` with PE bytes, canned GNU and LLVM readelf text (including RUNPATH/SONAME strings that spell dynamic tags) and the tool's exit codes. `hardened`: the tool accepts `lorica_boundary_tests` (Linux, Windows x64). `elf.*` (Linux): fixtures linked here with full options are accepted; without PIE, with an executable stack, without RELRO, with lazy binding, or as a shared library each is rejected for that reason |

Where the toolchain cannot apply EXTENDED (`lorica_extended_hardening_supported`)
or the unsafe API rejection (`lorica_unsafe_api_rejection_supported`),
configuration prints the reason, the affected tests are registered disabled and
CTest reports them "Not Run (Disabled)", and the checked tests are built without
that option: an unexecuted check is never reported as passed. On a host that is
expected to run them, configure with `-DLORICA_TEST_REQUIRE_EXTENDED=ON`: a
regression that makes EXTENDED unavailable then fails configuration instead of
disabling tests.

Recommended on Linux Clang, beyond the registered tests (no runtime library needed):
`clang++ -std=c++23 -O1 -fsanitize=undefined,integer,implicit-conversion -fsanitize-trap=all -fsanitize-ignorelist=<std headers> -Iinclude tests/checked.cpp`.
The ignorelist excludes the standard library's own intended conversions.

Praesidium compiles the `praesidium.json` units whose own file changed (all units in
repository scope); a header-only change compiles no unit, so header coverage comes
from the CMake builds. Every built `.c`/`.cpp` file has an entry whose standard and
defines match its build (a unit built several ways is listed once, with its first
standard). `src/sealed_region_windows.cpp` is empty outside `_WIN32` and is not
checked on Linux. The analyzer fixtures under `tests/analysis/fixtures/` are not
translation units (several are deliberately malformed) and have no entry; the
manifest format cannot exclude them, so a repository-scope Praesidium run stops at
`native.configuration-required` until Revisor offers an exclusion or the fixtures
change extension (an owner decision).

## Source analysis (SPEC-LR-ANALYZE)

`lorica.analysis.lexer`, `.preprocess`, `.extract`, `.complexity`, `.cli`, `.example`
run `tests/analysis/test_*.py` (Python standard library, no compiler): fixtures for
each fail-closed shape, hand-derived complexity values, the exact function list of
`include/` and `src/` (cross-checked once against clang-tidy-18), exit codes,
baseline and suppression semantics, and the README output of `examples/analysis`.
`lorica.analysis.example.over_threshold` and `.baseline` run that example as a failing
and a baselined gate; `lorica.analysis.self` requires zero unparsed regions in
Lorica's own sources under `--strict`. The clang-tidy cross-check in
`test_complexity.py` is skipped when clang-tidy is absent; it is never reported as
passed then. Optional: `LORICA_ANALYSIS_SYSTEM_HEADERS=/usr/include/c++/13` adds a
no-exception, time-bounded run over a whole header tree.

`lorica.analysis.shared_state` runs `tests/analysis/test_shared_state.py`: 38 fixtures
(`tests/analysis/fixtures/shared_state/`, the concurrency review's decision rules
C1-C16) with exact expected synchronization per datum, findings and sharing values;
mutations of six correct fixtures that must add a finding; the gate's exit codes,
baseline and suppression; Lorica's own `include/` and `src/` (two non-member data,
no finding, one shared stream). `lorica.analysis.example.shared_state` and
`.shared_state.baseline` run the adoption example as a failing and a baselined gate.
Opt-in (`-DLORICA_ANALYSIS_TSAN_ORACLE=ON`): `lorica.analysis.shared_state.tsan` builds
every `// tsan: race|clean` fixture line into a two-thread driver with
`-std=c++17 -O1 -g -fsanitize=thread` (spin gate, volatile sink, up to five runs) and
requires ThreadSanitizer to agree; it is skipped (77), never passed, when the compiler
cannot run TSan programs. Fixtures marked `not-observable` (invalid orders, `n = n + 1`,
strtok, fences, an escaping `this`, K&R) are listed, not run. Recorded 2026-11-13 with
GCC 13.3: 48 of 48 drivers agree in five consecutive runs.

`lorica.analysis.constexpr` (Python unittest with a fake compiler, runs everywhere)
checks the constexpr subcommand: locator and exclusion reasons, insertion points,
the strict flags and the stripped ones, diagnostic parsing, no shell and the
timeout, the copy-of-tree overlay (relative includes, bypass detection, a read-only
tree left untouched, cleanup), the rejected/accepted/witnessed logic, the fixed
point, a declaration with its out-of-line definition, gate and baseline.
`lorica.analysis.constexpr.compilers` runs the design review's 65 cases with g++ 13
and clang++ 18 at C++17/20/23 against the recorded states and must never report
`witnessed` where the review's witness fails; it exits 77 (skipped, never passed)
without those compilers or off Linux. The run over Lorica itself is recorded in
`spec/plan/2026-11-13-constexpr-report.md` (0 witnessed). MSVC is not executed.

## Release checks

Required release checks: Windows MSVC x64 and Linux GCC/Clang builds; tests;
sanitizers on Linux; fuzz corpus including SIZE_MAX; separate consumer using
installed find_package; external injection with missing/empty/valid target lists;
binary verifier positive and intentionally unhardened/malformed negative fixtures
(registered as `lorica.verify_binary.*`).
Inspect compile/link commands and each shipped dependency. PE flag checking is
not equivalent to CFG table or instruction coverage verification.

Measure representative service throughput, p99 latency, peak memory and rejection
behavior before deployment. No performance number is promised without measurement.

## Verification ownership and external invocation

`tests/boundary.cpp` owns the explicit Release-enabled `require` oracle and the
boundary-case executable entry point. `tests/fuzz_boundary.cpp` exports the exact
`LLVMFuzzerTestOneInput` ABI required by libFuzzer; it has no repository-local
caller by design. `.anatomia/entrypoints.json` declares this genuine external
entry point, without manufacturing a call edge or exempting unrelated functions.
The naming difference between this ABI and `main`/`require` is intentional.

## Read-only values

`lorica.protection` checks immutable scalar reads, edge values, copy independence,
ownership restrictions, invalid region inputs and concurrent readers. Windows
additionally inspects actual OS page permissions. `lorica.protection_linux` links
with `-Wl,--wrap` for mmap/mprotect/munmap: it checks the requested permissions
and flags, the resulting `/proc/self/maps` entry and the single release, and
injects mmap, mprotect and munmap failures (ENOMEM keeps the page; any other release
failure terminates). `lorica.protection.rejects_*` build pointer, structure and
const-qualified values and require the type diagnostic.
`lorica.protection_write_denied` runs a child process that deliberately writes
sealed bytes, accepting only Windows access violation 0xC0000005 or Linux SIGSEGV.
On Linux the child installs its own handler and exits with another status unless
the byte was readable and the fault is a denied access at that byte, so sanitizer
handlers and unrelated faults cannot pass; the driver also sets `handle_segv=0`
for ASan and TSan. `lorica.protection_write_misdirected` is the control: the same
child judged against another address must be rejected by the driver. Other errors,
normal exits and timeouts fail the check. Crash UI/core dumps are disabled in this
child. `lorica.protection_consumer` installs the build to a scratch prefix and
builds and runs `examples/consumer` against it with `LoricaInject.cmake`, then
builds `examples/contracts` against the same prefix and runs its tests. These
tests must run in the review environment; merely compiling them does not verify OS
enforcement. Sanitizer runs are recorded in
`spec/plan/2026-11-13-protection-review-evidence.md`.

`lorica.pack.unit` checks the sealed pack API (SPEC-LR-PACK): exact readback of
several types, alignment, exact fit and refused adds leaving state unchanged,
array edges and overflow, out-of-range indices as empty, capacity 0, an absurd
capacity (not under the sanitizers, whose allocators exit instead of throwing),
sealing nothing, the consumed builder, and the offset arithmetic and
type/ownership refusals as static_asserts. `lorica.pack.stops.*` run children
through `tests/pack_fault.py`: writes to the first and last used byte must end
with SIGSEGV/0xC0000005, reads through a slot outside a smaller pack with abort,
and the control with exit 0; the driver sets `handle_segv=0` for ASan/TSan.
`lorica.pack.readers_tsan` is registered only in a `-fsanitize=thread` build.
`lorica.demo.packing` judges checksums only.
