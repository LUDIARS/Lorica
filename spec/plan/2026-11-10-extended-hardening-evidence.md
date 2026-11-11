# Extended hardening and checked APIs: evidence

Executed in an isolated Linux container (Ubuntu 24.04, x86-64, glibc 2.39,
CMake 3.28.3, Python 3.13) with GCC 13.3.0 and Clang 18.1.3, both with libstdc++ 13.
The user asked for this implementation to be committed; the checks below ran in
that container only.

Executed:
- Before the change, on main: configure, build and CTest with `LORICA_BUILD_TESTS=ON`,
  GCC and Clang, Release: 3/3 passed; `verify_binary.py` on the boundary tests:
  ELF PIE/NX-stack/full-RELRO present. This is Lorica's first Linux run on record.
- After the change, GCC and Clang, each with `CMAKE_BUILD_TYPE` Release and Debug:
  configure, build and CTest 15/15 passed (boundary, checked C++20 and C++23,
  hardening stops, eight unsafe API probes, the refusals test, protection,
  protection write denial).
- Observed stops of `tests/hardening.cpp` under EXTENDED, Release, both compilers:
  out-of-range `vector::operator[]` and an empty `optional`'s value abort with
  libstdc++'s assertion message; a `memcpy` past a heap buffer of run-time size
  aborts with glibc's "buffer overflow detected". Built by hand with Clang and
  `_FORTIFY_SOURCE` 2, or without it, the harness fails on that copy; with level 3
  it passes. Built with the baseline profile only, it fails on the element access.
- `readelf -n`: Clang EXTENDED executables carry `x86 feature: IBT, SHSTK` and Clang
  baseline ones do not. Ubuntu's GCC enables CET by default, so GCC executables
  carry it in both profiles; this is no evidence for EXTENDED with GCC.
- Unsafe API header: direct, function pointer, macro alias and parenthesized uses
  are rejected with GCC and Clang as C++17, C++20 and C++23, at -O0 and with
  `_FORTIFY_SOURCE` 2 and 3 at -O2; bounded code compiles. A C library header
  included earlier stops compilation with the header's order error.
- glibc 2.40+ with Clang: glibc 2.41's `sys/cdefs.h` and `bits/string_fortified.h`
  placed in front of the local glibc (`-isystem`) give Clang separate fortified
  overloads that ignore the deprecation; with that overlay the header stops a
  fortified build with its error and still rejects calls in an unfortified one.
  Configuration refuses such toolchains (`lorica_unsafe_api_rejection_supported`).
- Independent review of the first version (two reviewers) found mixed-type calls
  converting through `checked_size.hpp`, unterminated array sources read past their
  end, overlapping copies, a formatter exception leaving partial output, the
  glibc 2.40+ Clang overloads, precompiled headers and C sources escaping the
  rejection, probes that passed under Ninja when only warned, and a FORTIFY check
  that the stack protector satisfied. Each is fixed or refused as above.
- Reverting each fix in a scratch copy fails the suite: `-Werror` removed, the
  order check, the deferred refusal check, FORTIFY level 2, the formatter reset,
  the array extent, the overlap-safe copy, the mixed-type and explicit-argument
  refusals and the append terminator check.
- `tests/checked.cpp` under trap-mode sanitizers (no runtime library): GCC
  `-fsanitize=undefined`, Clang `-fsanitize=undefined,integer,implicit-conversion`
  with the standard library headers ignored: exit 0, C++20 and C++23. Clang's
  implicit-conversion check traps inside libstdc++'s own `<format>` without the
  ignorelist; that is the library's intended conversion, not Lorica code.
- Simulated toolchain without EXTENDED support (scratch copy): configuration
  reports the reason and `lorica.hardening_stops` is "Not Run (Disabled)".
- Installed package and `examples/consumer` through `LoricaInject.cmake`: baseline,
  `LORICA_PROFILE=extended` with and without `LORICA_DEPRECATE_UNSAFE_APIS=ON`,
  configure/build/run exit 0 and the compile commands carry the documented options;
  `LORICA_PROFILE=max` fails configuration. `verify_binary.py` passes on each.
- The README checked-API snippet compiles and runs with GCC and Clang.
- `python -m unittest tests/test_verify_binary.py`: OK. `git diff --check`: clean.
- Revisor Praesidium (the hardened branch and the local main checkout), repository
  scope and `--base main`: passed, zero findings, every unit and changed header
  passed, nothing left unanalyzed.

Not executed: Windows/MSVC (the EXTENDED MSVC options, `/we4996` probes, the CRT
report settings and the 0xC0000409 stop are untested; MSVC 19.39 from the earlier
record is below the 19.44 minimum, so the extended checks report "Not Run" there),
libc++, a real glibc 2.40+ system, AArch64 branch protection, libFuzzer/ASan
(compiler-rt is not installed here), production service integration and
performance measurement.
