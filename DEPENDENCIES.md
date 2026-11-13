# Dependency and memory-safety review

Runtime: C++17 standard library (C++20 for the checked API headers) and
Windows/Linux virtual-memory APIs. No third-party packages, vendored sources,
transitive package dependencies, network downloads or install-time code execution.
Build: CMake 3.24+ and a supported compiler/linker. Optional artifact inspection:
Python 3 standard library, plus trusted binutils `readelf` for ELF. Optional fuzzing:
Linux Clang's compiler-rt/libFuzzer; instrumentation is test-only.

Optional source analysis: Python 3 standard library only (`tools/lorica_analyze.py`);
no compiler, clang or package. clang-tidy was used once to validate it and is not a dependency.

Source analysis audit (2026-11-12): reads files as UTF-8 with replacement, refuses
files over 8 MiB, never executes, imports or edits the analysed code; writes only the files it is
asked to write (a baseline, a patch). Only the `constexpr` subcommand starts a
process (see above). Its results are
heuristics (no macro expansion, no type resolution) and fail closed: what it cannot
parse is reported, not guessed.

The `shared-state` subcommand adds no dependency: Python 3 standard library, same
input handling, nothing executed. Its opt-in ThreadSanitizer oracle
(`-DLORICA_ANALYSIS_TSAN_ORACLE=ON`, test-only) compiles and runs the shared-state
fixtures with the configured C++ compiler and `-fsanitize=thread` (GCC's libtsan on
Linux); it is skipped (exit 77) when that runtime is missing.

The `constexpr` subcommand of tools/lorica_analyze.py starts a C++ compiler, and only
when asked: the compilers named by --compiler or by the entries of --compile-commands.
Only GCC and Clang are accepted (identified by `--version`; cl and clang-cl are
refused). Each compile is `-fsyntax-only` on a temporary copy of the analysed tree,
started with an argument list (no shell), standard input closed, LC_ALL=C and a
timeout (--timeout, default 120 s), in the unit's own directory; the copy is deleted
afterwards. The tool itself stays Python standard library only, and every other
subcommand starts no process. Without --compiler or --compile-commands nothing is
compiled.

Checked arithmetic and request budgeting have small, stable contracts and use
standard size types/optional rather than adding a package. No crypto, authentication,
allocator replacement, or protocol parser is reimplemented. Future adoption of
Scudo/mimalloc or security protocols requires platform/ABI, maintenance, upstream
license and measured cost review; no external license is assumed by this version.
No open-source license grant is assigned to Lorica without the owner's choice.

Memory audit:
- Integer operations check before addition/multiplication; range checks subtract
  only after proving offset <= capacity.
- Byte reads check the declared bound; null + zero pointer arithmetic is avoided.
- Pointer provenance, actual backing extent and lifetime remain caller preconditions.
- Boundary headers allocate nothing. The optional compiled protection component
  owns dedicated OS mappings; it cannot detect UAF or double-free elsewhere.
- Budgets update all dimensions only on success; callers must not race on a budget.
- Read-only views do not synchronize mutations of the underlying object.
- No unchecked C ABI or Rust/unsafe bridge is included in this first version.

Artifact inspection is for trusted local build outputs, not an internet-facing
parser. It invokes a trusted readelf without a shell and limits PE file allocation.

Write-protection audit: scalar and pack sizes come from sizeof and checked
arithmetic, with no user-controlled rounding arithmetic. OS calls allocate complete pages independently of the heap.
Source bytes are copied synchronously before sealing; no writable pointer escapes
the scalar API. Failed sealing releases its mapping before throwing. Successful
owners release once; copy and move are disabled. A release refused by the kernel
for lack of mapping slots (ENOMEM) leaves the page mapped read-only; any other
cleanup failure terminates. Concurrent loads only read immutable bytes; concurrent owner
destruction remains forbidden. Returned copies and owner metadata are unprotected.
No encryption, authentication, secure erase or general allocator is invented.
Tests use Python standard-library subprocess without a shell; no installer or
transitive package dependencies were introduced. Python is needed when building
the tests (the protection and extended-profile stop checks).

Sealed pack audit (2026-11-12): header-only on the existing protection target, no
new OS code. The builder stages values in a zeroed `new[]` buffer of the caller's
capacity (trusted or budget-charged); placement arithmetic is one constexpr
function on checked_add/checked_multiply/contains_range, with no page rounding.
Sealing passes the used bytes once to the unchanged sealed_region. Reads copy with
memcpy after an always-compiled bound check that terminates; no pointer or
reference into the mapping escapes. Not an allocator: no free, reuse, growth or
allocator interface (spec/feature/sealed-packs.md non-goals). The staging copy is
freed, not erased.

Checked API and build profile audit (2026-11-10): the checked APIs are header-only,
allocate nothing, keep no state and check every bound before writing or reading;
integer checks run before each operation. The extended profile adds compiler,
standard-library and C-library modes shipped with the toolchain (libstdc++/libc++/
MSVC STL hardening, glibc FORTIFY), no package. `<lorica/unsafe_api.hpp>` declares six C
library functions deprecated and `#undef`s object-like macros of those names; it
changes no definition and affects compilation only. With Clang it reads glibc's
`<features.h>` before the unit's first line, so feature-test macros must be given on
the command line there (checked with libstdc++ 13, GCC 13 and Clang 18; libc++ not
checked). Runtime tests and Linux validation remain separately
recorded; successful Windows compilation is not evidence of those checks.
