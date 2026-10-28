# Verification plan {#SPEC-LR-VERIFY}

Do not infer execution from the presence of tests. Initial implementation review
must record configure/build and executed tests separately. Run test commands only
with the applicable execution authorization.

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
