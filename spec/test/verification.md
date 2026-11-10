# Verification plan {#SPEC-LR-VERIFY}

Do not infer execution from the presence of tests. Initial implementation review
must record configure/build and executed tests separately. Run test commands only
with the applicable execution authorization.

Single-config generators (Makefiles, Ninja) take the configuration at configure
time: on Linux add `-DCMAKE_BUILD_TYPE=Release` (and repeat with Debug), or the
`--config`/`-C` options below select nothing and the optimized checks do not run.

```sh
cmake -S . -B build-test -DLORICA_BUILD_TESTS=ON
cmake --build build-test --config Release
ctest --test-dir build-test -C Release --output-on-failure
python tools/verify_binary.py build-test/Release/lorica_boundary_tests.exe
# Linux: python tools/verify_binary.py build-test/lorica_boundary_tests
cmake -S . -B build-fuzz -DCMAKE_CXX_COMPILER=clang++ -DLORICA_BUILD_FUZZER=ON
cmake --build build-fuzz
build-fuzz/lorica_boundary_fuzz -max_total_time=60
```

Boundary coverage includes SIZE_MAX/zero/exact-end arithmetic; null/empty/exact-end
views; huge offsets; each budget dimension; unchanged state on rejection; exact
depth limit. Tests use explicit abort checks so Release cannot disable assertions.
Fuzzing supplements these cases; it cannot prove absence of vulnerabilities.

## Checked APIs, extended profile and unsafe API rejection

| Test | Checks |
| --- | --- |
| `lorica.checked.cxx20`, `lorica.checked.cxx23` | `tests/checked.cpp` as C++20 and as C++23: integer, text and reader contracts as compile-time and run-time checks; every pair of 8-bit operands against the exact result in a wider type; that bool/character types, mixed operand types and explicit template arguments (also next to `byte_view.hpp`'s `size_t` overloads), temporary and read-only destinations do not compile; array sources by extent, overlapping copies, a throwing formatter. Built with the unsafe API rejection and the extended profile where supported |
| `lorica.hardening_stops` | `tests/hardening.cpp` built with EXTENDED, driven by `tests/hardening_fault.py`: an in-range run exits 0; an out-of-range `operator[]` and an empty `optional`'s value must stop the child (POSIX SIGABRT/SIGILL/SIGTRAP, Windows 0xC0000409). In optimized Linux configurations the build must have `_FORTIFY_SOURCE` 3 (checked at compile time) and a `memcpy` past a heap buffer of run-time size, which only level 3 sees, must stop with glibc's "buffer overflow detected"; a stop by the stack protector or the heap's own checks does not count. A normal exit, another error or a timeout fails |
| `lorica.unsafe_api.*` | `tests/unsafe_api_probes.cmake`: real targets with `lorica_deprecate_unsafe_apis` applied, each built by `tests/run_build_probe.cmake`, which judges by exit code and compiler output, not generator text. Bounded code must build; a direct `std::strcpy` call, a function pointer to it, a macro alias of `std::sprintf`, a parenthesized `::wcscat`, a `-D` alias of `std::strcat` and `std::vsprintf` must fail with the deprecation diagnostic; an earlier `-include` of a C library header must fail with the header's order error. The probes live in CMake, not a C++ source, because they are deliberately unsafe |
| `lorica.unsafe_api.refusals` | `tests/unsafe_api_refusals.cmake`: projects whose target gets precompiled headers or a C source after the call must fail configuration with the refusal; the control must configure |

Where the toolchain cannot apply EXTENDED (`lorica_extended_hardening_supported`)
or the unsafe API rejection (`lorica_unsafe_api_rejection_supported`),
configuration prints the reason, the affected tests are registered disabled and
CTest reports them "Not Run (Disabled)", and the checked tests are built without
that option: an unexecuted check is never reported as passed.

Recommended on Linux Clang, beyond the registered tests (no runtime library needed):
`clang++ -std=c++23 -O1 -fsanitize=undefined,integer,implicit-conversion -fsanitize-trap=all -fsanitize-ignorelist=<std headers> -Iinclude tests/checked.cpp`.
The ignorelist excludes the standard library's own intended conversions.

Praesidium: `tests/checked.cpp` is listed first in `praesidium.json`, so a changed
header is analyzed with a C++20 unit, the newest standard Lorica's headers require.
The C++17 headers keep C++17 coverage through the C++17 units and the CMake builds.

Required release checks: Windows MSVC x64 and Linux GCC/Clang builds; tests;
sanitizers on Linux; fuzz corpus including SIZE_MAX; separate consumer using
installed find_package; external injection with missing/empty/valid target lists;
binary verifier positive and intentionally unhardened/malformed negative fixtures.
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
ownership restrictions and invalid region inputs. Windows additionally inspects
actual OS page permissions. `lorica.protection_write_denied` runs a child process
that deliberately writes sealed bytes, accepting only Windows access violation
0xC0000005 or Linux SIGSEGV. Other errors, normal exits and timeouts fail the check.
Crash UI/core dumps are disabled in this child. These tests must run in the review
environment; merely compiling them does not verify OS enforcement. Linux and
concurrent-reader sanitizer coverage must be recorded independently.
