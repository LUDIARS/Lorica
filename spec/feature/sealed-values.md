# OS write-protected values {#SPEC-LR-SEALED}

Human decision: neco selected OS write prohibition, not thread-ordering fences.

Design: `Lorica::protection` owns dedicated OS mappings, initialized privately and
sealed read-only before construction succeeds. This is a narrow OS resource
wrapper, not a general-purpose/custom heap allocator. No heap pages containing
unrelated objects are protected. Windows VirtualAlloc/VirtualProtect/VirtualFree
and Linux mmap/mprotect/munmap are separate implementations. Unsupported systems
fail configuration. There is no writable fallback or reseal/update API. Execute
access is never requested. Linux deployments must exclude READ_IMPLIES_EXEC process
personalities; this library does not change process-wide personality. OS failures
throw system_error; failed sealing releases the allocation.

`sealed_value<T>` accepts only unqualified arithmetic and enum types. It stores an
object representation and returns a value copy using memcpy; no typed object is
constructed inside the mapping. Pointers, structures, mutable references and
copy/move assignment are excluded. Ownership is noncopyable and nonmovable.
The owner must outlive all reads; publish it to other threads using normal C++
synchronization. No atomic/fence guarantee is added. Structures, tables and many
values belong in one [sealed pack](sealed-packs.md) instead.

Threat model: an ordinary write through memory access to the sealed bytes faults
the process; this is not recoverable input validation. A kernel-mediated write
into them, such as `read(2)`, fails with an error (EFAULT) instead. The protection
does not stop the process itself: its own `mprotect`, `munmap` or
`mmap(MAP_FIXED)` over the mapping, writes through `/proc/self/mem`, or another
process writing with `ptrace` (all observed on Linux).
This is page protection, not Linux `mseal(2)`. It does not protect owner metadata,
source/readback copies, secrets or freed mappings. Sealing is shallow: only the
value's own bytes are protected, never memory they refer to, which is why pointers
are excluded here.

Limits: each value creates, protects and removes a mapping of its own, which can
interrupt the process's other running threads, and keeps at least one page
resident; once there are hundreds of values, reads slow down because each sits on
its own page. Use for a handful of immutable settings, not every local variable.
The kernel merges adjacent read-only mappings, but destroying very many values out
of creation order splits them again, and once `vm.max_map_count` is reached the
unmapping fails and the destructor calls `std::terminate` (observed on Linux with
140,000 values, every other one destroyed, at the default limit 65,530). A pack is
removed as one mapping and does not have this failure. No guard-page, encryption,
secure erasure or performance claim is made. No production service is
automatically migrated.

Acceptance: copy reads preserve supported scalar values; compile-time exclusion
of pointer and assignment APIs; OS query confirms read-only protection on Windows;
an isolated child write must exit with the platform's access-violation signal/code,
not an arbitrary nonzero status. Build/install consumer integration must link the
new target. Runtime checks require the existing authorized review/test workflow.

Additional recommended development tools: Clang AddressSanitizer for memory misuse,
UndefinedBehaviorSanitizer for invalid operations, ThreadSanitizer for data races
(separate build), and fuzzing for hostile input. These are proposals, not enabled
production runtimes. References:
- https://learn.microsoft.com/en-us/windows/win32/api/memoryapi/nf-memoryapi-virtualprotect
- https://clang.llvm.org/docs/AddressSanitizer.html
- https://clang.llvm.org/docs/UndefinedBehaviorSanitizer.html
- https://clang.llvm.org/docs/ThreadSanitizer.html
