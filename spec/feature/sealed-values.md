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
synchronization. No atomic/fence guarantee is added.

Threat model: blocks writes into the mapped data while its OS permissions remain
read-only. It does not protect owner metadata, source/readback copies, secrets,
freed mappings or an already-compromised process capable of changing permissions.
An invalid write faults the process; this is not recoverable input validation.
Each value costs at least one OS page. Use for sparse immutable settings, not
every local variable. No guard-page, encryption, secure erasure or performance
claim is made. No production service is automatically migrated.

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
