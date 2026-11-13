# Lorica

Composable security libraries for C++ services. Project code: **Lr**.
Lorica means armour: these components add layers of protection, not complete memory safety.

Components (C++17 unless noted, CMake 3.24+):

| Component | Contract |
| --- | --- |
| `Lorica::boundary` | Checked size arithmetic, bounded byte views, cumulative request budgets |
| `Lorica::boundary` (C++20 headers) | Checked integers of any type, bounded string copy/append/format, endian-safe byte reading ([checked APIs](spec/feature/checked-apis.md)) |
| `Lorica::protection` | Dedicated OS read-only storage for immutable arithmetic/enum values |
| `Lorica::contracts` | C++26 contract emulation (`LORICA_PRE` / `LORICA_POST` / `LORICA_CONTRACT_ASSERT`), four evaluation semantics, replaceable violation handler |
| `lorica_harden_target` | Target-local baseline hardening, with an optional strict `EXTENDED` profile and a configure-time capability query |
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
#include <cstdint>

lorica::byte_reader in(packet);                   // std::span<const std::byte>
const auto count = in.read_big_endian<std::uint32_t>();
const auto name = in.read_prefixed<std::uint16_t, std::endian::big>();
const auto total = count ? lorica::checked_multiply(*count, record_size) : std::nullopt; // record_size is std::uint32_t: both operands have one type
char label[32];
if (!name || !total || !lorica::format_into(label, "{} records", *count)) return reject_request();
```

On Linux, baseline requests libstdc++ assertions or libc++ FAST, FORTIFY in
optimized configurations, and supported stack-clash and control-flow flags.
`lorica_harden_target(my_service EXTENDED)` upgrades that target to libc++
EXTENSIVE or libstdc++ assertions and requires the Linux profile's stack and
branch protections, zero initialization and effective FORTIFY level 3 in
optimized configurations. On Windows it requires native MSVC 19.44+ x64 with
STL hardening and CET-compatible linking. See the
[profile table](spec/feature/security-contracts.md#SPEC-LR-EXTENDED).

`lorica_deprecate_unsafe_apis(my_service)` separately enables
[unsafe API rejection](spec/feature/security-contracts.md#SPEC-LR-UNSAFE-API).
`format_into` needs a library with `__cpp_lib_format`.

## Protection limits

`byte_view` is non-owning. A caller must supply the actual size of a live contiguous
object and retain it without concurrent mutation. It checks indices against that
declared size, not whether the pointer is valid. It does not detect use-after-free,
double-free, invalid pointers, type confusion, or bypasses through raw pointers.
It allocates/frees no memory. Budgets are request-local and are not thread-safe.
Charges must precede work, include decompressed output and nested allocations,
and use the same budget throughout the request. Depth must be supplied truthfully.
The `size_t` functions of `checked_size.hpp` take operands converted by the
language rules, so a negative or wider value is not detected; use `narrow` from
`checked_integer.hpp`, or `-Wconversion -Wsign-conversion`.
Timeouts, concurrency limits and authentication remain service responsibilities.

Hardening supports Windows MSVC-compatible toolchains and Linux GCC/Clang.
It does not protect prebuilt dependencies, prove every object has instrumentation,
or make a compromised process trustworthy. Later conflicting build flags can
weaken protection: inspect actual commands and artifacts. No universal memory
barrier, secure allocator, cryptography or authentication is implemented here.
`std::atomic_thread_fence` (thread ordering) is unrelated to these protections.

## Contracts (C++26 emulation)

A contract states what holds in a correct program, much as an assertion does, with
a role (precondition, postcondition, assertion) and an evaluation semantic chosen
by the build. Link `Lorica::contracts`; deploy its one runtime DLL/shared object
for the executable and all its plugins.

Inside a function body (`<lorica/contracts.hpp>`):

```cpp
int element(std::span<const int> values, std::size_t index) {
    LORICA_PRE(index < values.size());
    return values[index];
}
constexpr int square(int v) { return LORICA_POST_RETURN(v * v, r, r >= 0); }
```

Laid over existing code from outside, without editing it
(`<lorica/contract_overlay.hpp>`, [overlay](spec/feature/contracts.md#SPEC-LR-CONTRACT-OVERLAY)):

```cpp
int reserve(int in_stock, int requested);                     // existing, unchanged

constexpr auto checked_reserve = LORICA_CONTRACT(reserve)
    .pre([](int in_stock, int requested) { return requested >= 0 && requested <= in_stock; },
         "request is covered by the stock")
    .post([](int left, int in_stock, int requested) { return left == in_stock - requested; },
          "what is left is the stock less the request");      // the result comes first

const int left = checked_reserve(in_stock, requested);        // the same call, checked
```

The same conditions are the function's test. `test` reports instead of handling a
violation and never makes a call the preconditions refuse:

```cpp
using lorica::contracts::test_status;
require(static_cast<bool>(checked_reserve.test(10, 3)));
const auto refused = checked_reserve.test(10, 11);            // reserve is not called
require(refused.status == test_status::precondition_failed);
require(std::string_view(refused.condition) == "request is covered by the stock");
```

Choose the semantic per target from the build, without editing sources:
`lorica_set_contract_semantic(my_service enforce)` (the default; also `observe`,
`quick_enforce`, and `ignore`, which strips the checks and leaves the plain call),
or for an existing project `-DLORICA_CONTRACT_SEMANTIC=ignore` next to
`LORICA_TARGETS` with `LoricaInject.cmake`. Contracts catch bugs; they are not
input validation, which must not disappear under `ignore`. `examples/contracts`
runs one contract over a correct and a defective implementation as a test table.
See [the contracts spec](spec/feature/contracts.md).

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
platform test execution must be verified separately. `LORICA_BUILD_PROTECTION=OFF`
omits `Lorica::protection` and does not install its headers.

This is appropriate for a few process-lifetime settings, not every variable: each
value is its own OS mapping with one resident page, and Linux limits a process to
`vm.max_map_count` mappings. Construct values inside `main` under try/catch; at
namespace scope a failing constructor terminates before `main`. A forbidden write
faults the process. It does not stop the process itself from zeroing the page with
`madvise`, writing it through `/proc/self/mem` or changing its permissions, and it
does not protect copies or the owner object. It does not hide secrets, securely
erase memory or protect unrelated allocations.
The owner must outlive reads and be safely published to concurrent readers.
See [the protection contract](spec/feature/sealed-values.md) for limits and suggested
development tools (ASan, UBSan, TSan and fuzzing).

See [security contracts](spec/feature/security-contracts.md),
[verification](spec/test/verification.md), and [dependency review](DEPENDENCIES.md).

## Status

Initial implementation; not a production-security certification. No existing
service has been migrated. Release publication and review are separate steps.
