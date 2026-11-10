# Lorica

Composable security libraries for C++ services. Project code: **Lr**.
Lorica means armour: these components add layers of protection, not complete memory safety.

Components (C++17 unless noted, CMake 3.24+):

| Component | Contract |
| --- | --- |
| `Lorica::boundary` | Checked size arithmetic, bounded byte views, cumulative request budgets |
| `Lorica::boundary` (C++20 headers) | Checked integers of any type, bounded string copy/append/format, endian-safe byte reading ([checked APIs](spec/feature/checked-apis.md)) |
| `Lorica::protection` | Dedicated OS read-only storage for immutable arithmetic/enum values |
| `lorica_harden_target` | Target-local compiler/linker mitigations; `EXTENDED` adds standard library hardening, FORTIFY, zero-initialized locals, stack clash and CET/BTI; unsupported platforms fail configuration |
| `lorica_deprecate_unsafe_apis` | Uses of `strcpy`/`strcat`/`sprintf`/`vsprintf`/`wcscpy`/`wcscat` in a target's C++ sources fail to compile; every deprecation becomes an error; [limits](spec/feature/security-contracts.md#SPEC-LR-UNSAFE-API) |
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
  '-DLORICA_TARGETS=my_service;my_parser' \
  -DLORICA_PROFILE=extended -DLORICA_DEPRECATE_UNSAFE_APIS=ON   # optional
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

With C++20, the checked APIs cover the rest of a typical parser:

```cpp
#include <lorica/bounded_text.hpp>
#include <lorica/byte_reader.hpp>
#include <lorica/checked_integer.hpp>

lorica::byte_reader in(packet);                   // std::span<const std::byte>
const auto count = in.read_big_endian<std::uint32_t>();
const auto name = in.read_prefixed<std::uint16_t, std::endian::big>();
const auto total = count ? lorica::checked_multiply(*count, record_size) : std::nullopt;
char label[32];
if (!name || !total || !lorica::format_into(label, "{} records", *count)) return reject_request();
```

`lorica_harden_target(my_service EXTENDED)` and `lorica_deprecate_unsafe_apis(my_service)`
add the hardened standard library (C++26 standard library hardening, available today
as vendor modes) and reject the unbounded C APIs at compile time. See the
[extended profile](spec/feature/security-contracts.md#SPEC-LR-EXTENDED) for the exact
options, toolchain minimums (GCC 12, Clang 18, MSVC 19.44 x64) and limits, and the
[unsafe API rejection](spec/feature/security-contracts.md#SPEC-LR-UNSAFE-API) for the
toolchains and targets it refuses and what it does not see (compiler builtins,
system headers). `format_into` needs a library with `__cpp_lib_format`.

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

## Write-protected variables

Link `Lorica::protection` and include `<lorica/sealed_value.hpp>`:

```cpp
const lorica::sealed_value<unsigned> maximum_requests(128);
const unsigned limit = maximum_requests.load(); // Unprotected value copy.
```

The original bytes live in a dedicated OS mapping requested without execute access and sealed read-only
before construction returns. There is no setter or mutable pointer. Only arithmetic
and enum values are supported. OS allocation/protection errors throw; there is no
writable fallback. Windows and Linux are supported by the implementation;
platform test execution must be verified separately. Disable the compiled component
explicitly with `LORICA_BUILD_PROTECTION=OFF` for boundary-only use.

This is appropriate for sparse immutable configuration, not every variable: each
value consumes at least one page. A forbidden write faults the process. It does not
protect copies, owner metadata or a process that can change its own permissions.
It does not hide secrets, securely erase memory or protect unrelated allocations.
The owner must outlive reads and be safely published to concurrent readers.
See [the protection contract](spec/feature/sealed-values.md) for limits and suggested
development tools (ASan, UBSan, TSan and fuzzing).

See [security contracts](spec/feature/security-contracts.md),
[verification](spec/test/verification.md), and [dependency review](DEPENDENCIES.md).

## Status

Initial implementation; not a production-security certification. No existing
service has been migrated. Release publication and review are separate steps.
