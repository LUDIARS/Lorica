# Lorica

Composable security libraries for C++ services. Project code: **Lr**.
Lorica means armour: these components add layers of protection, not complete memory safety.

Initial components (C++17, CMake 3.24+):

| Component | Contract |
| --- | --- |
| `Lorica::boundary` | Checked size arithmetic, bounded byte views, cumulative request budgets |
| `lorica_harden_target` | Target-local compiler/linker mitigations; unsupported platforms fail configuration |
| `LoricaInject.cmake` | External CMake injection for an explicit target allowlist |
| `tools/verify_binary.py` | Selected PE/ELF executable metadata checks; does not execute the binary |

## Use

```cmake
find_package(Lorica 0.1 CONFIG REQUIRED)
target_link_libraries(my_service PRIVATE Lorica::boundary)
lorica_harden_target(my_service)
```

Or add this repository with `add_subdirectory`. No network fetch, package manager,
install-time script, or third-party runtime is required. Installation uses CMake:

```sh
cmake -S . -B build
cmake --build build
cmake --install build --prefix /your/prefix
```

Existing CMake projects can inject build protection without editing their source:

```sh
cmake -S /service/source -B /service/build \
  -DCMAKE_PROJECT_TOP_LEVEL_INCLUDES=/path/to/Lorica/cmake/LoricaInject.cmake \
  '-DLORICA_TARGETS=my_service;my_parser'
```

Every listed target must exist and be locally compiled. Boundary checks still
require call-site adoption; loading a DLL cannot retrofit them into arbitrary C++.
The injection hook requires being the top-level configure and is not a dependency
graph traversal. Explicitly list each source-built library requiring mitigation.

```cpp
#include <lorica/checked_size.hpp>
#include <lorica/input_budget.hpp>

lorica::input_budget budget({1024 * 1024, 4096, 128, 32});
const auto bytes = lorica::checked_multiply(element_count, element_size);
if (!bytes || !budget.consume(*bytes, element_count, 1)) {
    return reject_request(); // Reject expected bad input; do not abort the service.
}
// Allocate/process only after successful checks. This example is schematic.
```

## Protection limits

`byte_view` is non-owning. A caller must supply the actual size of a live contiguous
object and retain it without concurrent mutation. It checks indices against that
declared size, not whether the pointer is valid. It does not detect use-after-free,
double-free, invalid pointers, type confusion, or bypasses through raw pointers.
It allocates/frees no memory. Budgets are request-local and are not thread-safe.
Charges must precede work, include decompressed output and nested allocations,
and use the same budget throughout the request. Depth must be supplied truthfully.
Timeouts, concurrency limits and authentication remain service responsibilities.

Hardening supports Windows MSVC-compatible toolchains and Linux GCC/Clang.
It does not protect prebuilt dependencies, prove every object has instrumentation,
or make a compromised process trustworthy. Later conflicting build flags can
weaken protection: inspect actual commands and artifacts. No universal memory
barrier, secure allocator, cryptography or authentication is implemented here.
`std::atomic_thread_fence` (thread ordering) is unrelated to these protections.

See [security contracts](spec/feature/security-contracts.md),
[verification](spec/test/verification.md), and [dependency review](DEPENDENCIES.md).

## Status

Initial implementation; not a production-security certification. No existing
service has been migrated. Release publication and review are separate steps.
