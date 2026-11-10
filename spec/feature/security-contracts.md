# Security contracts — initial implementation

## Threat model and scope

Remote clients supply hostile lengths/counts/depths. Trusted host code adopts
these contracts before allocation/processing. Compromised native code in the same
address space can bypass or corrupt checks. OS isolation is the security boundary
for that threat, and belongs to the service launcher, not this library.

Design: small independently usable headers and build modules, no allocator or
global mutable state. `checked_size`, `byte_view` and `input_budget` are C++17;
`checked_integer`, `bounded_text` and `byte_reader` need C++20 (concepts) and use
C++23/26 library features when present (see [checked APIs](checked-apis.md)). The
examples do not require `std::expected` or ownership emulation. Errors are
optional/false, not exceptions or abort for ordinary rejected input. No C
ABI/handle registry is promised in v0.1.

| ID | Guaranteed behavior under stated preconditions |
| --- | --- |
| LR-SIZE-01 | Addition/multiplication returns empty on size_t overflow |
| LR-RANGE-01 | offset <= capacity and length <= capacity-offset; zero tail is allowed |
| LR-VIEW-01 | Null is allowed only for zero size; size <= configured maximum |
| LR-VIEW-02 | Out-of-range reads/subviews fail without reading backing memory |
| LR-BUDGET-01 | All three cumulative dimensions are charged together or not at all |
| LR-BUDGET-02 | Caller-reported depth is compared against an explicit maximum |
| LR-INT-01 | `narrow` returns empty unless the value is representable in the target type |
| LR-INT-02 | Checked add/subtract/multiply/divide return empty on overflow, a zero divisor and MIN / -1; operands share one type |
| LR-INT-03 | Saturating forms clamp to the type's range |
| LR-TEXT-01 | Copy/append write the text and a terminator inside the destination, or leave an empty string and return empty |
| LR-TEXT-02 | `format_into` checks its format string at compile time and never writes past the destination |
| LR-READ-01 | `byte_reader` reads only within its span; a failed read consumes nothing |
| LR-BUILD-01 | Unknown targets/platforms fail; imported/alias/noncompiled targets are rejected |
| LR-BUILD-02 | External injection requires nonempty target allowlist; an unknown profile fails |
| LR-BUILD-03 | EXTENDED adds standard library hardening, FORTIFY, zero-initialized locals, stack clash and control-flow protection, or fails configuration |
| LR-BUILD-04 | `lorica_deprecate_unsafe_apis` turns uses of the unbounded C copy/format functions in a target's C++ sources into compile errors, within the limits of SPEC-LR-UNSAFE-API, or refuses the target |
| LR-ARTIFACT-01 | Verifier rejects missing selected metadata; never claims full coverage |

Windows flags: /GS /sdl /guard:cf at compile; /guard:cf /DYNAMICBASE /NXCOMPAT
at executable/shared linking, plus /HIGHENTROPYVA on 64-bit.
Linux flags: -fstack-protector-strong, position-independent code; -pie for executables;
RELRO, NOW, noexecstack for executable/shared linking. The baseline profile claims
no CFI, CET, FORTIFY or standard library hardening; the extended profile below adds
them where the toolchain is qualified. Compiler/linker rejection fails the build.

Binary metadata does not prove stack checks, CFG call-site coverage, or all
prebuilt modules were compiled with protection. PE checking currently checks flags
only, not Guard CF tables; ELF checks PIE, NX-stack and full RELRO markers.

## Extended build profile {#SPEC-LR-EXTENDED}

`lorica_harden_target(<target> EXTENDED)` applies the baseline and then:

| Toolchain | Added |
| --- | --- |
| Linux GCC 12+/Clang 18+, x86-64 or AArch64 | `_GLIBCXX_ASSERTIONS` (libstdc++), `_LIBCPP_HARDENING_MODE=_LIBCPP_HARDENING_MODE_EXTENSIVE` (libc++), `-ftrivial-auto-var-init=zero`, `-fstack-clash-protection`, `-fcf-protection=full` (x86-64) or `-mbranch-protection=standard` (AArch64); `-U_FORTIFY_SOURCE -D_FORTIFY_SOURCE=3` in Release, RelWithDebInfo and MinSizeRel |
| MSVC 19.44+ (Visual Studio 2022 17.14), x64 | `_MSVC_STL_HARDENING=1`, `_MSVC_STL_DESTRUCTOR_TOMBSTONES=1`; `/CETCOMPAT` when linking executables and shared libraries |

The hardened standard library turns precondition violations that otherwise corrupt
memory (an out-of-range `operator[]`, `front()`/`back()` of an empty container, the
value of an empty `std::optional`, out-of-range `std::span` and `string_view`
access) into a program stop, as C++26 standard library hardening specifies; these
modes are ABI-compatible with unhardened code. FORTIFY makes glibc check copies
into objects of known size at run time; glibc checks only optimized code, so other
configurations (including Debug and a custom configuration name) do not get it.
Zero-initialized automatic variables are the compiler-flag counterpart of C++26's
erroneous behaviour for uninitialized reads; they do not make such reads correct.
Any other toolchain, an older version or another processor fails configuration;
`lorica_extended_hardening_supported(<var>)` tells a caller in advance (the test
suite uses it to report its extended checks as not run). The C and C++ libraries
are not probed: FORTIFY level 3 needs glibc 2.34 or newer (older glibc treats it as
level 2; musl has no FORTIFY), and `_LIBCPP_HARDENING_MODE` needs libc++ 18 or
newer; an older library gets less without a diagnostic. In optimized
configurations a target's own `_FORTIFY_SOURCE` is replaced by level 3 without a
diagnostic; a different `_LIBCPP_HARDENING_MODE` of the target gives a macro
redefinition warning.

Limits: a stop is a deliberate termination, not recoverable input validation; it
does not cover raw pointers, C arrays or third-party code built without these
options, and libc++'s or MSVC's hardening covers only what that library checks.
Overhead is not measured here. `verify_binary.py` does not inspect these options.
Calling the function again with EXTENDED upgrades a baseline target; it never
removes options.

## Unsafe C API rejection {#SPEC-LR-UNSAFE-API}

`lorica_deprecate_unsafe_apis(<target>)` makes a use of `strcpy`, `strcat`,
`sprintf`, `vsprintf`, `wcscpy` and `wcscat` in the target's C++ sources a compile
error, including uses a word search misses: through a macro or a `-D` alias, with
`std::` qualification, in parentheses, or by taking the function's address. GCC
and Clang force-include `<lorica/unsafe_api.hpp>` and make deprecation warnings
errors; the header declares the functions deprecated before the C library does,
with glibc's exception specification, so glibc's own declarations and the inline
wrappers of a fortified build inherit the attribute. MSVC turns deprecation
warning C4996, which the UCRT gives these functions, into an error (`/we4996`);
defining `_CRT_SECURE_NO_WARNINGS` disables it there. Either way every deprecation
in the target becomes an error, not only these six: the project's own
`[[deprecated]]` functions and deprecated standard library features too. `gets` is
not declared at all since C11/C++14.

Fail closed: the function refuses, at configuration, clang-cl (which ignores
`/we4996`), MinGW (whose C library deprecates nothing), Clang with glibc 2.40 or
newer (whose fortified functions are separate `pass_object_size` overloads no
earlier declaration reaches), a target with C sources and a target with
precompiled headers (CMake compiles them as system headers, where deprecations
are not reported), checked when the top-level directory is done, so sources and
headers added later count. `lorica_unsafe_api_rejection_supported(<var>)` tells a
caller in advance. The header itself stops compilation when a C library header
came before it (for example through an earlier `-include`), and on a fortified
Clang/glibc 2.40+ build that got past configuration.

Not covered: compiler builtins (`__builtin_strcpy`, `__builtin___sprintf_chk`),
glibc's `__*_chk` entry points, headers on system include paths (`-isystem`,
imported targets by default) and the macros they define, and code that switches
the warning off (`#pragma GCC diagnostic ignored`, a later
`-Wno-deprecated-declarations`). Revisor's Praesidium policy rules remain the
review-time check for those spellings and pragmas, and for other dangerous calls
(`memcpy` with a wrong size, `scanf("%s")`). Set `NO_SYSTEM_FROM_IMPORTED` where
third-party headers must be checked too.

Replacements: `lorica::copy_string`, `lorica::append_string` and
`lorica::format_into` ([checked APIs](checked-apis.md)), or `std::snprintf` and
`std::vsnprintf`. The header `#undef`s object-like macros of the six names and
re-exports them in `namespace std` (Clang attaches the attribute to the `std::`
names only so); this names the same functions the standard headers export and
is a build-time check only. It reads glibc's `<features.h>`, which declares no
function. It is C++ only and not for C++20 module units, which cannot take a
force-included header.

## Installed consumer contract {#SPEC-LR-CONSUMER}

`examples/consumer` is an independent CMake project. Its `main` uses a live
two-byte array, checks multiplication and a request budget before constructing
a bounded view, and returns failure on rejected input. It consumes the installed
`Lorica::boundary` target. External `LoricaInject.cmake` applies protection to its
`lorica_consumer` executable (`-DLORICA_PROFILE=extended` and
`-DLORICA_DEPRECATE_UNSAFE_APIS=ON` select the extended profile and the unsafe API
rejection); the example does not claim service deployment.

## Responsibility map

Committed `spec/domains/*.domain.json` describes six responsibilities:
boundary-validation (including the C++20 checked APIs), build-hardening (including
the extended profile and the unsafe API header), variable-protection,
artifact-inspection, contract-verification and consumer-integration. These definitions do not disable
review gates or claim test execution. Header-only C++ and Python may not be
represented in a given analyzer snapshot; the map records their responsibility
without claiming analysis coverage.

## Follow-up recommendations (not implemented)

1. Privilege-separated workers for hostile parsing; secrets outside those workers.
2. Request deadlines, bounded concurrency, rate limits and restart backoff.
3. ASan/UBSan + fuzz in validation. Standard library hardening is available as the
   EXTENDED profile; libc++ and MSVC STL behaviour still needs execution on those
   toolchains (see the 2026-11-10 evidence).
4. Evaluate maintained hardened allocators separately. Do not create a new allocator.
5. Prefer memory-safe implementations for new high-risk parsers where practical;
   audit every native boundary and unsafe block separately.

Fable design review was obtained 2026-10-28. Accepted: independent repository,
build plus boundary contracts, artifact inspection, no arbitrary C++ safety claim,
no allocator invention. Numeric overhead estimates and universal flag combinations
were not accepted without platform measurements. Review completion registration
failed because a read-only review had no feature-branch implementation evidence;
that administrative failure is not a passed implementation/security review.

References:
- https://llvm.org/docs/ScudoHardenedAllocator.html
- https://clang.llvm.org/docs/AddressSanitizer.html#security-considerations
- https://gcc.gnu.org/onlinedocs/gcc/Instrumentation-Options.html
- https://learn.microsoft.com/en-us/windows/win32/secbp/control-flow-guard
