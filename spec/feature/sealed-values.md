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

Threat model: blocks ordinary stores into the mapped data while its OS permissions
remain read-only; such a store faults the process, which is not recoverable input
validation. Read-only permission does not stop the process itself from changing
the value without a fault: `madvise(MADV_DONTNEED)` on the page replaces it with
zero (`MADV_FREE` lets the kernel do so later), a write through `/proc/self/mem`
replaces it, the process's own `mprotect`, `munmap` or `mmap(MAP_FIXED)` can unseal
or replace the page, and a permitted ptrace tracer can write it. A wrong range given
to such a call anywhere in the process is enough. The owner object is unprotected
metadata: a write that reaches it changes what `load()` reads, without a fault, and
what the destructor releases; `const` on the owner does not make it read-only.
Source/readback copies, secrets and freed mappings are not protected. Construct
values inside `main` (or a function it calls) under try/catch: a constructor that
throws at namespace scope terminates the process before `main`.

Cost and limits: each value is its own mapping, created with two OS calls and
released with one, and keeps one resident page (on Windows one committed page in
its own reservation, which takes 64 KiB of address space). Use it for a few
process-lifetime settings, not every local variable and not per request. On Linux
a process has at most `vm.max_map_count` mappings; adjacent sealed pages may merge
into one. When no mapping is left, construction throws `system_error`
(`ENOMEM`). Releasing a value with live sealed neighbours on both sides in one
merged run needs one more mapping; releasing in reverse order of construction or
in order of construction does not. If the kernel refuses a release for that reason
(`ENOMEM`), the destructor leaves the page mapped read-only until the process exits;
any other release failure terminates. No guard-page, encryption, secure erasure or
performance claim is made. No production service is automatically migrated.

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
