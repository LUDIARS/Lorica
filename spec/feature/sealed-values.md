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
does not stop the process itself, and a wrong range given to such a call anywhere
in the process is enough: `madvise(MADV_DONTNEED)` replaces the value with zero
without a fault while the page stays read-only (`MADV_FREE` is accepted too and
lets the kernel do the same later), a write through `/proc/self/mem` replaces it
likewise, its own `mprotect`, `munmap` or `mmap(MAP_FIXED)` over the mapping
unseals or replaces it, and another process can write it with `ptrace` (observed
on Linux, except the deferred `MADV_FREE` discard). This is page protection, not
Linux `mseal(2)`. The owner object is unprotected metadata: a write that reaches
it changes what `load()` reads, without a fault, and what the destructor releases;
`const` on the owner does not make it read-only. Source/readback copies, secrets
and freed mappings are not protected. Sealing is shallow: only the value's own
bytes are protected, never memory they refer to, which is why pointers are
excluded here. Construct values inside `main` (or a function it calls) under
try/catch: a constructor that throws at namespace scope terminates the process
before `main`.

Limits: each value creates and protects a mapping of its own with two OS calls and
removes it with one, which can interrupt the process's other running threads, and
keeps at least one page resident (on Windows one committed page in a reservation
of its own, which takes 64 KiB of address space); once there are hundreds of
values, reads slow down because each sits on its own page. Use for a handful of
process-lifetime settings, not every local variable and not per request. On Linux
a process has at most `vm.max_map_count` mappings, and construction throws
`system_error` (`ENOMEM`) when none is left. The kernel merges adjacent read-only
mappings; releasing a value with live sealed neighbours on both sides of a merged
run splits it and needs one more mapping, while releasing in reverse order of
construction or in order of construction does not. If the kernel refuses a
release for that reason (`ENOMEM`), the destructor leaves the page mapped
read-only until the process exits (observed on Linux with 140,000 values, every
other one destroyed, at the default limit 65,530); any other release failure
terminates. A pack is removed as one mapping and never needs the split. No
guard-page, encryption, secure erasure or performance claim is made. No production
service is automatically migrated.

Acceptance: copy reads preserve supported scalar values; compile-time exclusion
of pointer, structure, qualified and assignment APIs; OS query confirms read-only
protection on Windows; on Linux the OS calls are observed through linker wrapping:
private, never executable, sealed read-only over the whole mapping, released once,
failures thrown with the OS code and a failed seal released. An isolated child
write must exit with the platform's access-violation signal/code, not an arbitrary
nonzero status; on Linux the child also requires the fault to be a denied access
at the sealed byte. Build/install consumer integration must link the new target:
a test installs the build and builds and runs `examples/consumer` against it.
Runtime checks require the existing authorized review/test workflow.

Additional recommended development tools: Clang AddressSanitizer for memory misuse,
UndefinedBehaviorSanitizer for invalid operations, ThreadSanitizer for data races
(separate build), and fuzzing for hostile input. These are proposals, not enabled
production runtimes. References:
- https://learn.microsoft.com/en-us/windows/win32/api/memoryapi/nf-memoryapi-virtualprotect
- https://clang.llvm.org/docs/AddressSanitizer.html
- https://clang.llvm.org/docs/UndefinedBehaviorSanitizer.html
- https://clang.llvm.org/docs/ThreadSanitizer.html
