# Hardening profile integration verification (2026-11-11)

The patch applies to the common main commit `cab4f12086e30484f249d1b4aa479bf7cdec13a9`.
It combines PR #2 at `9989dd8877ee090f84290decf9d571398d47a79d` and
PR #3 at `09f845ef493b185cff22ab5eeb4a10ae7c99d258`. The main and PR #2
source trees matched their Git tree IDs before integration.

## Lorica

| Environment | Checks on the integrated source |
| --- | --- |
| Debian x86-64, glibc 2.41, GCC 14.2, libstdc++ 14 | Release, Ninja, CMake 4.4.4: 20/20 CTest passed. Ninja Multi-Config: 20/20 in Release and 20/20 in Debug. |
| Minimum CMake series, 3.24.3, Unix Makefiles, GCC 14.2 | Release: 20/20 CTest passed. |
| Clang 19.1.7, libstdc++ 14 | Release: 11 passed, 9 disabled. |
| Clang 19.1.7, libc++ 19 | Release and Debug: 11 passed and 9 disabled per configuration. |
| Linux AArch64, GCC 14.2 cross compiler | Release configured, compiled and linked. The EXTENDED commands used stack-clash protection, branch-protection=standard, zero initialization and FORTIFY 3. The ELF verifier accepted the AArch64 test executable. No target runtime execution. |
| Native Windows MSVC and clang-cl | No Windows SDK/toolchain or runtime validation. Native MSVC 19.44+ x64 remains the EXTENDED qualification target. |

The nine disabled Clang tests exercise the separate unsafe API rejection feature.
With glibc 2.41 the unfortified configuration probe from PR #2 previously accepted
Clang, but its force-included header rejected an actual fortified build. The
configure check now recognizes that header family independently of the probe's
own FORTIFY level. EXTENDED's standard-library and optimized FORTIFY stop tests
ran on both C++ libraries. On Linux the native configuration tests compare the
actual C/C++ options for direct EXTENDED and a baseline target upgraded in place.
They exercise earlier macro definitions, repeat application, the effective glibc
level, a real Release override to -O0 and injected missing capabilities. The
lower-libc test simulates a missing level-3 probe on the host glibc.

A separately installed GCC package was consumed via `find_package` and the
installed top-level injection hook with both profiles, including unsafe API
rejection. Both executables ran and passed the ELF PIE/NX-stack/full-RELRO
inspection. The verifier's four existing Python unit tests passed.

To repeat a native run from a clean checkout:

```sh
cmake -S . -B build-gcc -G Ninja -DCMAKE_CXX_COMPILER=g++ \
  -DCMAKE_BUILD_TYPE=Release -DLORICA_BUILD_TESTS=ON \
  -DCMAKE_EXPORT_COMPILE_COMMANDS=ON '-DCMAKE_CXX_FLAGS=-Wall -Wextra -Werror'
cmake --build build-gcc
ctest --test-dir build-gcc --output-on-failure
```

For Clang, select `clang++` in a fresh build directory. Add `-stdlib=libc++`
to `CMAKE_CXX_FLAGS` for the libc++ run. For Ninja Multi-Config select the
generator at configure time, then pass `--config Release` or `--config Debug`
to the build and `-C Release` or `-C Debug` to CTest.

## Discutere downstream check

The inspected Discutere checkout was `2aea49e73016d2f6947d36d70a1d1e01733dc5f1`
(native subtree `64fe1d1ac8d805cdd1f2a4a6adb54f229d54e430`). With
`-DLORICA_SOURCE_DIR=<integrated checkout>`, GCC 14.2 Release and the project's
normal warnings-as-errors policy, configuration generated 625 compilation
commands. All 624 C++ commands had baseline library checks. All 625, including
SQLite's C unit, had one stack protector, stack-clash option, CET option and
ordered FORTIFY undefine/level-3 pair. The C unit had no C++ library flags.

The full build stopped in `routes_paper_blocks.cpp` and `routes_start.cpp`.
GCC diagnosed the inline function `schedule_web_auto_approve_locked` as used
without a definition in those translation units. The original main Lorica
configuration produced the same diagnostic compiling both units. Discutere
registered 202 CTests, all unexecuted on this build.
