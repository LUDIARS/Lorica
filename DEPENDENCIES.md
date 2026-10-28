# Dependency and memory-safety review

Runtime: C++17 standard library only. No third-party packages, vendored sources,
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
- No dynamic allocation/free is performed by the headers; they cannot detect UAF
  or double-free elsewhere in the service.
- Budgets update all dimensions only on success; callers must not race on a budget.
- Read-only views do not synchronize mutations of the underlying object.
- No unchecked C ABI or Rust/unsafe bridge is included in this first version.

Artifact inspection is for trusted local build outputs, not an internet-facing
parser. It invokes a trusted readelf without a shell and limits PE file allocation.
