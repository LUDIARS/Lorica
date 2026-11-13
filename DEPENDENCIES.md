# Dependency and memory-safety review

Runtime: C++17 standard library (C++20 for the checked API headers) and
Windows/Linux virtual-memory APIs. No third-party packages, vendored sources,
transitive package dependencies, network downloads or install-time code execution.
Build: CMake 3.24+ and a supported compiler/linker. Optional artifact inspection:
Python 3 standard library, plus trusted binutils `readelf` for ELF. Optional fuzzing:
Linux Clang's compiler-rt/libFuzzer; instrumentation is test-only.

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

Write-protection audit: scalar size comes from sizeof, with no user-controlled
rounding arithmetic. OS calls allocate complete pages independently of the heap.
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

Checked API and build profile audit (2026-11-10): the checked APIs are header-only,
allocate nothing, keep no state and check every bound before writing or reading;
integer checks run before each operation. The extended profile adds compiler,
standard-library and C-library modes shipped with the toolchain (libstdc++/libc++/
MSVC STL hardening, glibc FORTIFY), no package. `<lorica/unsafe_api.hpp>` declares six C
library functions deprecated, `#undef`s object-like macros of those names and
re-exports them in `namespace std` (needed for Clang); it reads glibc's
`<features.h>`, changes no definition and affects compilation only. Runtime tests and Linux validation remain separately
recorded; successful Windows compilation is not evidence of those checks.
