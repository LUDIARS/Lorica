---
task: lorica-cxx23-full-support
project: Lr
kind: implementation
created: 2026-11-13
memory_links: []
---

# C++23 full support and Japanese README

Human instructions (2026-11-13): "Make Lorica fully C++23-compliant, then write a
Japanese README" and "GOGO". LUDIARS adopted Visual Studio 2026 (MSVC 14.52,
cl 19.52, stable in 18.12 on 2026-11-10) with C++23; contracts (P2900) are not
used.

Scope: ISO C++23 selection for `cxx_std_23` (CMake maps it to `/std:c++latest`
on MSVC), a C++23 run of every test, a language-version test, C++23 library use
that keeps behavior (`std::byteswap` in `byte_reader`), spec/README/dependency
updates and `README.ja.md`. Not in scope: contracts, new components, downstream
repositories (Odeum, Curare, Ingenium, Discutere, Manus, Tirocinium), dependency
additions. The C++17/C++20 minimums and the `#error` policy are unchanged.

Design:
- `cmake/LoricaCxxStandard.cmake`: `lorica_use_iso_cxx23()` (macro; directory
  scope) and `lorica_iso_cxx23_supported()` (query with reason). Called by
  Lorica's CMakeLists, `LoricaConfig.cmake` and `LoricaInject.cmake`.
- `cmake/LoricaCxxStandardOverride.cmake`: the injection hook runs before the
  consuming project enables C++, so the switch is replaced through
  `CMAKE_USER_MAKE_RULES_OVERRIDE_CXX`, chaining a project's own override.
- Tests stay registered in CMakeLists.txt as main (#4) arranged them; each C++
  test of a C++17/C++20 part also runs as C++23 (`.cxx23`), including the
  contracts runtime and sealed packs added by #4. `tests/unsafe_api_probes.cmake`
  takes the standards to build its probes with.
- `tests/language_standards.cmake` + `tests/standard.cpp`:
  `lorica.standard.cxx17/20/23` check the language version.
- Rebased on main 575a44f (#4) by merging it after Revisor reported conflicts on
  local PR #3770.

Acceptance:
- VS2026 (MSVC 19.52): configure/build/CTest all pass; the C++23 targets compile
  with `-std:c++23` and none with `std:c++latest`.
- VS2022 17.9 (MSVC 19.39): configure as before; EXTENDED and the ISO C++23 check
  are reported not run with reasons.
- Installed `find_package` and `LoricaInject.cmake` consumers (including a
  subdirectory and an existing override) get `-std:c++23`.
- Linux GCC/Clang: recorded as not executed when unavailable.
- AGENTS.md (no network fetch, one responsibility per file, threat-model limits
  as public contracts) and LUDIARS coding conventions; no dependency added.

Evidence: [2026-11-13 C++23 evidence](../plan/2026-11-13-cxx23-evidence.md).
