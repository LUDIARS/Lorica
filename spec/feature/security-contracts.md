# Security contracts — initial implementation

## Threat model and scope

Remote clients supply hostile lengths/counts/depths. Trusted host code adopts
these contracts before allocation/processing. Compromised native code in the same
address space can bypass or corrupt checks. OS isolation is the security boundary
for that threat, and belongs to the service launcher, not this library.

Design: small independently usable headers and build modules, no allocator or
global mutable state. Source compatibility is C++17; the examples do not require
`std::expected` or ownership emulation. Errors are optional/false, not exceptions
or abort for ordinary rejected input. No C ABI/handle registry is promised in v0.1.

| ID | Guaranteed behavior under stated preconditions |
| --- | --- |
| LR-SIZE-01 | Addition/multiplication returns empty on size_t overflow |
| LR-RANGE-01 | offset <= capacity and length <= capacity-offset; zero tail is allowed |
| LR-VIEW-01 | Null is allowed only for zero size; size <= configured maximum |
| LR-VIEW-02 | Out-of-range reads/subviews fail without reading backing memory |
| LR-BUDGET-01 | All three cumulative dimensions are charged together or not at all |
| LR-BUDGET-02 | Caller-reported depth is compared against an explicit maximum |
| LR-BUILD-01 | Unknown targets/platforms fail; imported/alias/noncompiled targets are rejected |
| LR-BUILD-02 | External injection requires nonempty target allowlist |
| LR-ARTIFACT-01 | Verifier rejects missing selected metadata; never claims full coverage |

Windows flags: /GS /sdl /guard:cf at compile; /guard:cf /DYNAMICBASE /NXCOMPAT
at executable/shared linking, plus /HIGHENTROPYVA on 64-bit.
Linux flags: -fstack-protector-strong, position-independent code; -pie for executables;
RELRO, NOW, noexecstack for executable/shared linking. Compiler/linker rejection fails the build.
Also on Linux, stated explicitly so they do not depend on a distribution's compiler defaults:
standard-library precondition checks (`_GLIBCXX_ASSERTIONS` for libstdc++,
`_LIBCPP_HARDENING_MODE_FAST` for libc++ 18+; an older libc++ ignores the macro and gets no checks);
`_FORTIFY_SOURCE` (3 with GCC/Clang 12+, otherwise 2) in the Release, RelWithDebInfo and MinSizeRel
configurations only, because fortified calls require optimization; `-fstack-clash-protection` and
`-fcf-protection=full` where the compiler accepts them, with a configure warning where it does not
(`-fcf-protection` is x86 only). A build with an empty or Debug configuration gets no FORTIFY.
Precondition checks abort the process on violation; they bound standard containers, not raw
pointers. Clang CFI is not applied.

Binary metadata does not prove stack checks, CFG call-site coverage, or all
prebuilt modules were compiled with protection. PE checking currently checks flags
only, not Guard CF tables; ELF checks PIE, NX-stack and full RELRO markers.

## Installed consumer contract {#SPEC-LR-CONSUMER}

`examples/consumer` is an independent CMake project. Its `main` uses a live
two-byte array, checks multiplication and a request budget before constructing
a bounded view, and returns failure on rejected input. It consumes the installed
`Lorica::boundary` target. External `LoricaInject.cmake` applies protection to its
`lorica_consumer` executable; the example does not claim service deployment.

## Responsibility map

Committed `spec/domains/*.domain.json` describes the initial implementation's
five responsibilities: boundary-validation, build-hardening, artifact-inspection,
contract-verification and consumer-integration. These definitions do not disable
review gates or claim test execution. Header-only C++ and Python may not be
represented in a given analyzer snapshot; the map records their responsibility
without claiming analysis coverage.

## Follow-up recommendations (not implemented)

1. Privilege-separated workers for hostile parsing; secrets outside those workers.
2. Request deadlines, bounded concurrency, rate limits and restart backoff.
3. ASan/UBSan + fuzz in validation; audited standard-library hardening per toolchain.
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
