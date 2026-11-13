# C++23 full support: evidence (2026-11-13)

Task: [C++23 full support](../tasks/2026-11-13-cxx23-full-support.md). Branch
`feat/lr-cxx23-full-support`, first from main `5e8281b`, then merged with main
`575a44f` (#4) after Revisor reported conflicts on local PR #3770. Windows 11 x64,
CMake 4.4.4, Python 3. Test execution was authorized by the owner for this worktree.

## Before the change

- MSVC 19.52.37029 (Visual Studio 2026 18.12, toolset 14.52.37025), `Visual Studio
  18 2026` x64, `LORICA_BUILD_TESTS=ON LORICA_BUILD_PROTECTION=ON`, Release on
  `5e8281b`: 15/15 CTest passed; EXTENDED ran on Windows for the first time.
- CMake 4.4.4 `Modules/Compiler/MSVC-CXX.cmake` sets
  `CMAKE_CXX23_STANDARD_COMPILE_OPTION` to `-std:c++latest` from MSVC 19.29.30129;
  the VS 2026 flag table has no ISO `stdcpp23` entry. A consumer requesting
  `cxx_std_23` without Lorica gets `<LanguageStandard>stdcpplatest`.
- Direct `cl` probe, `_MSVC_LANG`: `/std:c++20` 202002, `/std:c++23` 202302,
  `/std:c++latest` 202400; `__cpp_lib_byteswap` 202110 under C++23 and latest,
  absent under C++20. `/std:c++23preview` warns D9048 (deprecated; use `/std:c++23`).

## First version (on 5e8281b)

- VS 2026, Release and Debug: 30/30 CTest passed in each; every `_cxx23` target
  compiled with `-std:c++23`, `std:c++latest` 0 times in the detailed MSBuild logs.
- VS 2022 17.9 / MSVC 19.39.33523, Release: configure reported
  `lorica.standard.cxx23` not run ("cxx_std_23 selects -std:c++latest here, a draft
  mode; ...") and both hardening stops not run (EXTENDED needs MSVC 19.44); build
  succeeded; 27 passed, 3 "Not Run (Disabled)", 0 failed.
- Installed package (`cmake --install`) consumed by a scratch project with
  `cxx_std_23` targets in the top directory and a subdirectory: `find_package`
  and `LoricaInject.cmake` gave both `-std:c++23`; injection with a project's own
  `CMAKE_USER_MAKE_RULES_OVERRIDE_CXX` ran that override and gave `-std:c++23`;
  without Lorica, `stdcpplatest`. Before the override hook existed the injection
  path left `stdcpplatest`: `CMAKE_PROJECT_TOP_LEVEL_INCLUDES` runs before C++ is
  enabled (compiler variables empty there).
- Negative control: `tests/standard.cpp` built by hand with `/std:c++latest
  /DLORICA_TEST_STANDARD=23` prints 202400 and exits 1.

## Merged with main 575a44f (#4)

Executed, VS 2026 / MSVC 19.52 (build directory `build/vs2026-m2`):
- Configure and build, Release and Debug: succeeded.
- CTest, Release and Debug, before `byte_reader::assemble` was split: 112 tests,
  10 "Not Run (Disabled)" (the five GCC/Clang-only unsafe API probes and their
  `.cxx23` copies), 98 passed, 4 failed in each configuration:
  - `lorica.analysis.extract`, `lorica.analysis.complexity`: their self-application
    tables pinned `byte_reader`'s functions and `read`'s complexity. Fixed: the
    tables now list `assemble`, `swapped` and `shifted` (`assemble` was split so
    no function exceeds cognitive complexity 5); both then passed.
  - `lorica.analysis.constexpr`: POSIX path assumptions on Windows (`relpath`
    across drives, `/` separators). The same test from a clean export of main
    `575a44f` fails the same way (14 failures); not changed by this task. #4
    recorded it as not supported on Windows.
  - `lorica.checked.runtime_format`: the probe is rejected correctly (C7595), but
    the Japanese-locale compiler message does not match the English "constant
    expression". Present on main; unchanged.
- Detailed MSBuild logs (Release, Debug): every C++23 target compiles with
  `-std:c++23` (boundary, checked, hardening, protection and its test library,
  packs, contracts ignore/enforce/quick_enforce/overlay and the pre-existing
  `contracts_observe/overlay_cxx23`, which had been `/std:c++latest`, standard);
  C++17/C++20 targets with `/std:c++17`/`/std:c++20`; `std:c++latest` 0 times; no
  generated `.vcxproj` contains `c++latest`/`stdcpplatest`; the 15 `_cxx23` probe
  projects (9 unsafe API, 3 contract, 3 sealed) carry `-std:c++23`.
- After splitting `assemble` (rerun one at a time after a host low-memory stop):
  Release and Debug build succeeded; CTest 112 tests in each: 100 passed, 10
  "Not Run (Disabled)" (GCC/Clang-only probes), 2 failed — only
  `lorica.analysis.constexpr` and `lorica.checked.runtime_format`, both present on
  main as above. `std:c++latest` 0 times in the Debug log.
- `lorica.checked.runtime_format` with `VSLANG=1033`: the compiler message stayed
  Japanese under MSBuild (reused build nodes), so English output was not obtained;
  the probe is still rejected with C7595.
- VS 2022 17.9 / MSVC 19.39.33523 on the merged tree, Release: configure reports
  `lorica.standard.cxx23` not run (draft mode reason) and the four hardening stop
  tests not run (EXTENDED needs MSVC 19.44); build succeeded; CTest 112 tests: 95
  passed, 15 "Not Run (Disabled)", 2 failed (the same two as above).
- `git diff --check`: clean.

## Revisor's registered tests (owner request "Rvのテスト解決して", 2026-11-13)

Revisor reviews Lorica with VS 2022 17.9 (`configure`, `build`, `boundary-contracts`
= the whole CTest, `artifact-parser`, `pe-metadata`), so the two failures above
blocked it. Fixed:
- `lorica.checked.runtime_format`: the expected diagnostic also accepts MSVC's
  error number C7595, as the unsafe API probes accept C4996.
- `lorica.analysis.constexpr` on Windows: `tools/lorica_analysis/gate.py` no
  longer fails on a tree on another drive (`relpath` across drives; the key keeps
  the absolute path); `constexpr_compiler.py` reads a location that starts with a
  drive (`C:\...:7:3:`), turns CRLF output into LF and compares a unit's source
  path in normalized form; `tests/analysis/test_constexpr.py` compares paths in
  the host's form (`os.path.normpath`) instead of POSIX spellings.
Executed after the fix:
- `python tests/analysis/test_constexpr.py` on Windows: 27 tests OK (was 14
  failures, also on main 575a44f).
- VS 2022 17.9, Release: build succeeded; CTest 97/97 passed, 15 "Not Run
  (Disabled)" with reasons. `py -3 tests/test_verify_binary.py`: 9 tests OK;
  `py -3 tools/verify_binary.py .../Release/lorica_boundary_tests.exe`: PE
  mitigation flags present.
- VS 2026 / MSVC 19.52, Release: build succeeded; CTest 102/102 passed, 10 "Not
  Run (Disabled)" (GCC/Clang-only probes).
- The owner's "TSのテストは外して" refers to TypeScript tests; Lorica has none.

Not executed:
- Linux GCC/Clang locally: the local WSL Ubuntu 24.04 has no C/C++ compiler or
  CMake, and installing them needs a network fetch outside this task. The
  repository's CI (`.github/workflows/ci.yml`: Ubuntu 24.04 GCC/Clang Release and
  Debug, GCC sanitizers, windows-2022 MSVC) runs on push; its result is not yet
  known.
- Ninja/NMake with MSVC, clang-cl, libc++, AArch64, a CMake older than 4.4.4.
