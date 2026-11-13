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
| `lorica.profiles.*` | Native Linux Ninja/Makefile consumers: configure, compile and compare C/C++ commands for baseline, direct EXTENDED, repeated calls and promotion. Simulated missing flag, lower libc level and unknown CPU, plus a real Release `-O0` override, check baseline continuation and explicit EXTENDED refusal. Multi-config commands are checked separately per generated configuration. |
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
builds and runs `examples/consumer` against it with `LoricaInject.cmake`. These
tests must run in the review environment; merely compiling them does not verify OS
enforcement. Sanitizer runs are recorded in the evidence files under `spec/plan`.
