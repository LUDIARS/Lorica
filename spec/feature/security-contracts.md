# Security contracts — initial implementation

## Threat model and scope

Remote clients supply hostile lengths/counts/depths. Trusted host code adopts
these contracts before allocation/processing. Compromised native code in the same
address space can bypass or corrupt checks. OS isolation is the security boundary
for that threat, and belongs to the service launcher, not this library.

Design: small independently usable headers and build modules, no allocator. The
only process-wide mutable state is the violation handler of `Lorica::contracts`
(an atomic pointer, see [contracts](contracts.md)). `checked_size`, `byte_view` and `input_budget` are C++17;
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
| LR-BUILD-03 | EXTENDED requires every platform-specific protection in the profile table below, or fails configuration |
| LR-BUILD-04 | `lorica_deprecate_unsafe_apis` turns uses of the unbounded C copy/format functions in a target's C++ sources into compile errors, within the limits of SPEC-LR-UNSAFE-API, or refuses the target |
| LR-ARTIFACT-01 | Verifier rejects missing selected metadata; never claims full coverage |

## Build profiles {#SPEC-LR-EXTENDED}

`lorica_harden_target(app)` selects baseline. Passing `EXTENDED` selects the
strict profile or upgrades an existing baseline. Repeated calls retain the
strongest requested profile. Both the direct API and top-level injection use
the same target property to select a single libc++ mode at generation time.

| Protection | Linux baseline (GCC or Clang) | Linux EXTENDED |
| --- | --- | --- |
| Stack and linking | `-fstack-protector-strong`, PIC, PIE for executables, full RELRO and NX stack for executable/shared/module links | Same flags |
| C++ library | `_GLIBCXX_ASSERTIONS` for libstdc++, FAST for supporting libc++. Older libc++ may ignore the mode. | Require libstdc++ assertions or libc++ EXTENSIVE in the configured headers |
| C library | For Release, RelWithDebInfo and MinSizeRel, request level 3 with GCC/Clang 12+, otherwise level 2. Probe each enabled C/C++ driver and configuration. Fall back to effective level 2 or omit the option with a configure warning. | Require effective level 3 in every configured optimized build type |
| Stack clash and control flow | Probe `-fstack-clash-protection`, x86 CET (`-fcf-protection=full`) or AArch64 PAC/BTI (`-mbranch-protection=standard`). Warn once per unsupported driver/option. | Require both protections on x86-64 or AArch64, GCC 12+ or Clang 18+ and a 64-bit ABI |
| Automatic variables | Toolchain default | Require `-ftrivial-auto-var-init=zero` |

FORTIFY qualification uses the effective `__USE_FORTIFY_LEVEL` from libc headers.
Debug, empty and custom configuration names receive no Lorica FORTIFY override.
Where Lorica selects a FORTIFY level, the libc++ mode or `_GLIBCXX_ASSERTIONS`, its
ordered undefine/define pair follows the toolchain's flags and replaces earlier
definitions. C sources receive only the applicable C options; the functions need
the CXX language enabled and refuse a C-only project.
Use consistent library settings across translation units that share inline code.
The probes describe the configured toolchain and run again on every CMake run (about
a second), so a cache entry cannot stand in for a probe. Target-specific sysroots, later
flags and prebuilt dependencies require inspection of the final build commands.

On Windows, baseline uses `/GS /sdl /guard:cf` for compilation,
`/guard:cf /DYNAMICBASE /NXCOMPAT` for executable/shared/module links and
`/HIGHENTROPYVA` on 64-bit. EXTENDED requires native MSVC 19.44+ x64, an STL
that recognizes both `_MSVC_STL_HARDENING` and `_MSVC_STL_DESTRUCTOR_TOMBSTONES`,
and a linker accepting `/CETCOMPAT`. It enables both C++ switches and adds
`/CETCOMPAT` to those links. Clang-cl can still use the Windows baseline.

`lorica_extended_hardening_supported(result)` uses the same qualification as
an explicit EXTENDED request and returns an explanation in `result_REASON`.
A failed explicit request stops configuration. Library checks cover vendor-defined
preconditions and terminate on violation. Clang CFI, runtime hardware enforcement
and hardening of prebuilt code are outside these profiles. The binary verifier
checks PIE, NX-stack and full RELRO on ELF, and selected flags on PE. Instruction
coverage, CFG tables and performance require separate verification.

## Unsafe C API rejection {#SPEC-LR-UNSAFE-API}

`lorica_deprecate_unsafe_apis(<target>)` makes a use of `strcpy`, `strcat`,
`sprintf`, `vsprintf`, `wcscpy` and `wcscat` in the target's C++ sources a compile
error, including uses a word search misses: through a macro or a `-D` alias, with
`std::` qualification, in parentheses, or by taking the function's address. GCC
and Clang force-include `<lorica/unsafe_api.hpp>` and make deprecation warnings
errors; the header declares the functions deprecated before the C library does,
with glibc's exception specification, so glibc's own declarations and the inline
wrappers of a fortified build inherit the attribute. Clang reports no deprecation
inside a declaration that is itself deprecated, so with Clang the declarations also
carry a `diagnose_if` warning, made an error the same way. The header ends by making
deprecation an error for the rest of the unit, so a later
`-Wno-deprecated-declarations`, also one a linked target exports, does not switch
it off. MSVC turns deprecation
warning C4996, which the UCRT gives these functions, into an error (`/we4996`);
defining `_CRT_SECURE_NO_WARNINGS` disables it there. Either way every deprecation
in the target becomes an error, not only these six: the project's own
`[[deprecated]]` functions and deprecated standard library features too. `gets` is
not declared at all since C11/C++14.

Fail closed: the function refuses, at configuration, clang-cl (which ignores
`/we4996`), MinGW (whose C library deprecates nothing), GCC and Clang outside Linux,
Clang with glibc 2.40 or
newer (whose fortified functions are separate `pass_object_size` overloads no
earlier declaration reaches), a target with C sources and a target with
precompiled headers (CMake compiles them as system headers, where deprecations
are not reported), checked when the top-level directory is done, so sources and
headers added later count. Precompiled headers inherited from linked targets are
switched off for the target (`DISABLE_PRECOMPILE_HEADERS`). With GCC and Clang, C
units get the header too, so a C source the check cannot see (added through a generator expression or a
linked target's sources) stops at its `#error`.
`lorica_unsafe_api_rejection_supported(<var>)` tells a
caller in advance. The header itself stops compilation when a C library header
came before it (for example through an earlier `-include`), and on a fortified
Clang/glibc 2.40+ build that got past configuration.

Not covered: compiler builtins (`__builtin_strcpy`, `__builtin___sprintf_chk`),
glibc's `__*_chk` entry points, headers on system include paths (`-isystem`,
imported targets by default) and the macros they define, project headers that mark
themselves `#pragma GCC system_header`, a declaration bound to one of the six
symbols under another name (an asm label; with GCC also an `extern "C"`
redeclaration in another namespace), and code that switches the warning off
(`#pragma GCC diagnostic ignored` in the source, `-w` anywhere on the command
line). Revisor's Praesidium policy rules remain the
review-time check for those spellings and pragmas, and for other dangerous calls
(`memcpy` with a wrong size, `scanf("%s")`). Set `NO_SYSTEM_FROM_IMPORTED` where
third-party headers must be checked too.

Replacements: `lorica::copy_string`, `lorica::append_string` and
`lorica::format_into` ([checked APIs](checked-apis.md)), or `std::snprintf` and
`std::vsnprintf`. The header `#undef`s object-like macros of the six names and is
a build-time check only. With Clang it reads glibc's `<features.h>` before the
unit's first line, which fixes glibc's feature selection there: give feature-test
macros (`_FORTIFY_SOURCE`, `_FILE_OFFSET_BITS`, `_TIME_BITS`) on the command line,
not in the source. It is C++ only and not for C++20 module units, which cannot take
a force-included header and fail to compile.

## Installed consumer contract {#SPEC-LR-CONSUMER}

`examples/consumer` is an independent CMake project. Its `main` uses a live
two-byte array, checks multiplication and a request budget before constructing
a bounded view, and returns failure on rejected input. It consumes the installed
`Lorica::boundary` and `Lorica::protection` targets (it shows a sealed limit), so
it needs an install built with protection. External `LoricaInject.cmake` applies protection to its
`lorica_consumer` executable (`-DLORICA_PROFILE=extended` and
`-DLORICA_DEPRECATE_UNSAFE_APIS=ON` select the extended profile and the unsafe API
rejection); the example does not claim service deployment.

## Responsibility map

Committed `spec/domains/*.domain.json` describes eight responsibilities:
boundary-validation (including the C++20 checked APIs), build-hardening (including
the extended profile and the unsafe API header), variable-protection
(including sealed packs and their demo), runtime-contracts (in-body contracts and
the overlay), artifact-inspection, source-analysis (the lexical complexity gate,
its tests, fixtures and adoption example), contract-verification and
consumer-integration. These definitions do not disable
review gates or claim test execution. Header-only C++ and Python may not be
represented in a given analyzer snapshot; the map records their responsibility
without claiming analysis coverage.

## Follow-up recommendations (not implemented)

1. Privilege-separated workers for hostile parsing; secrets outside those workers.
2. Request deadlines, bounded concurrency, rate limits and restart backoff.
3. ASan/UBSan + fuzz in validation. Qualify standard-library hardening on each shipped toolchain.
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
