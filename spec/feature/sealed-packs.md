# Sealed packs {#SPEC-LR-PACK}

Human instruction: neco asked for "a packager that lets memory be handled faster"
(2026-11-12), right after naming the existing memory protection
([sealed values](sealed-values.md)).

## Purpose

A `sealed_value<T>` gives every value its own OS mapping. A sealed pack puts many
immutable values, structures, tables and strings into one mapping, sealed read-only
the same way. It makes sealed structures, run-time sized tables and large value
sets practical. For a handful of settings it is not faster than `sealed_value`
(see the cost model); one structure in one pack already gives them a single
mapping.

## API

Header `<lorica/sealed_pack.hpp>`, C++17, part of `Lorica::protection` (no new
library target and no new OS code: sealing is the existing
`lorica::detail::sealed_region(source, size)`).

```cpp
lorica::pack_builder builder(capacity);              // capacity zeroed bytes of ordinary heap memory
std::optional<lorica::pack_slot<T>> slot = builder.add(value);
std::optional<lorica::pack_array_slot<T>> table = builder.add_array(data, count);
const lorica::sealed_pack pack(std::move(builder)); // one mapping, read-only when this returns
T copy = pack.load(*slot);
std::optional<T> element = pack.at(*table, index);  // empty when index >= table->size()
```

- `T` must satisfy `lorica::is_packable_v<T>`: an unqualified object type that is
  not an array, pointer or member pointer, is trivially copyable, trivially copy
  constructible (this rejects `std::atomic`) and default constructible. Other
  types do not compile.
- `add` and `add_array` copy the bytes into the builder at the next offset that
  is a multiple of `alignof(T)` from the start of the pack. They return empty,
  and change nothing, when the bytes do not fit in the remaining capacity, when
  `count * sizeof(T)` overflows, or when `data` is null with a nonzero count. An
  empty array takes no bytes. `used()` and `capacity()` report the builder's state.
- `pack_builder(0)` throws `std::invalid_argument`; a failed staging allocation
  throws `std::bad_alloc`. The capacity is the caller's to bound: take it from
  trusted configuration or charge it to an `input_budget` first.
- `sealed_pack(pack_builder&&)` copies the builder's used bytes once into a new
  mapping, seals it and consumes the builder, which then has capacity 0 and
  accepts nothing. It throws `std::invalid_argument` when nothing was added (also
  for a consumed builder) and `std::system_error` when the OS refuses; the
  builder is then unchanged. There is no writable fallback.
- Slots are an offset (and a count for arrays), opaque and made only by a builder.
  `load` and `at` return copies made with `memcpy`; no typed object is constructed
  inside the mapping and no reference, pointer or view into it is handed out.
- `pack_builder` and `sealed_pack` are neither copyable nor movable.
  `std::optional<sealed_pack>::emplace` and `std::make_unique<sealed_pack>` cover
  deferred and heap ownership.

| ID | Guaranteed behavior under stated preconditions |
| --- | --- |
| LR-PACK-01 | `load` and `at` return values with exactly the bytes they were added with, for scalars, enums, structures, 64-byte aligned types and arrays |
| LR-PACK-02 | An add that does not fit, a null array with a nonzero count and a `count * sizeof(T)` overflow return empty and leave `used()` unchanged; an exact fit is accepted; an empty array takes no bytes |
| LR-PACK-03 | Offsets are multiples of `alignof(T)` from the pack's start; the offset arithmetic is one `constexpr` function on `checked_add`, `checked_multiply` and `contains_range` and cannot overflow `size_t` |
| LR-PACK-04 | `at` with an index at or beyond the array's size returns empty without reading |
| LR-PACK-05 | A `load` or `at` whose bytes do not lie inside this pack's used bytes calls `std::terminate`. The check is always compiled; it is not a contract and does not depend on `Lorica::contracts` |
| LR-PACK-06 | Once the constructor returns, an ordinary write to any used byte of the pack, first or last, faults the process (Linux SIGSEGV, Windows 0xC0000005) |
| LR-PACK-07 | Types that fail `is_packable_v` do not compile; neither class can be copied or moved; slots cannot be made outside a builder; sealing requires an rvalue builder |
| LR-PACK-08 | Capacity 0 throws `std::invalid_argument`; an absurd capacity throws `std::bad_alloc`; sealing nothing throws `std::invalid_argument` and leaves the builder usable; a consumed builder refuses every add and cannot be sealed again |
| LR-PACK-09 | Unsynchronised concurrent `load`, `at` and `sealed_value::load` on safely published objects report no data race under ThreadSanitizer |

## Threat model and limits

What the read-only protection does:

- An ordinary write through memory access to a sealed byte faults the process.
  Kernel-mediated writes into it, such as `read(2)` into the bytes, fail with an
  error (EFAULT) instead, and the process keeps running.

What it does not stop:

- The process itself: `mprotect`, `munmap` and `mmap(MAP_FIXED)` over the mapping, writes through `/proc/self/mem`, and another process writing with
  `ptrace`. This is page protection, not Linux `mseal(2)`.
- Values before sealing: the builder's staging buffer is ordinary writable heap
  memory, freed (not erased) after sealing, as are the caller's source values.
- Metadata: slots and the `sealed_pack` object itself (mapping address and sizes)
  are ordinary memory.
- Pointees: sealing is shallow. Only the bytes of `T` are protected. Memory that a
  member points or refers to (a `std::string_view`, a `const char*` member, a
  handle) is neither copied nor protected, and C++17 cannot reject such members at
  compile time.

What the slot check proves (LR-PACK-05): it keeps the read inside this pack's used
bytes. It does not tell whose slot it is. A slot kept from another pack, or from a
destroyed pack, whose bytes fall inside this pack's used bytes reads this pack's
bytes, possibly as the wrong type, and is not detected; neither is a corrupted slot
that stays in range. A slot's lifetime and origin are the caller's precondition.

No secrecy, encryption, secure erasure, guard page or performance claim is made.
A write fault is not recoverable input validation.

## Cost model

Stated as mechanisms; no number is promised. Run `examples/packing` to see
figures for one host and load.

- Each `sealed_value` creates a mapping, changes its protection, takes a page
  fault when it is filled, and removes the mapping when destroyed. Changing or
  removing mappings can interrupt the process's other running threads. Each value
  keeps at least one page resident. Once there are hundreds of values, reads slow
  down because each sits on its own page at the same in-page offset (cache-set
  aliasing, then the TLB's reach).
- A pack does that once for all its values and keeps them contiguous. Its own
  costs: the staging allocation; each value is copied twice (into the builder, then
  into the mapping); peak memory is the staging buffer plus the mapping while the
  constructor runs; the mapping takes at least one page; `load` copies `sizeof(T)`
  on every call, so a large table belongs in `add_array` and `at`, which copies one
  element; each read performs the bound check, and `at` an index check.
- On Windows each allocation is placed on a 64 KiB boundary according to
  Microsoft's documentation (not executed here), which makes many `sealed_value`
  objects costlier in address space and a pack relatively cheaper.

## Thread safety

The builder is used by one thread. A sealed pack has no mutable state: `load` and
`at` only read the object and the mapping. Publish the pack to other threads with
normal C++ synchronisation (for example by constructing it before starting them);
after that, readers need no synchronisation. The pack must outlive every read, and
its destruction must not race with reads. Slots are plain values and can be copied
freely. No atomic or fence guarantee is added.

## Non-goals and design-review record

AGENTS.md requires a design review for anything allocator-like. Two adversarial
design reviews (performance and security, 2026-11-12) cut the first draft to this
design. It is a write-once staging buffer followed by one sealed copy, not an
allocator. Out of scope, each needing a new design review:

- an allocate or emplace API that hands out writable or uninitialised storage;
- free, reuse, reset, growth or chaining;
- a `std::allocator` or `std::pmr` interface, including a budgeted memory resource;
- an `operator new` replacement;
- unsealing.

Also rejected by the reviews: references, pointers or views into the mapping and
placement-new (they would construct objects in the mapping and hand out pointers
that dangle with the pack); slot identity tags (a per-module counter in a static
library cannot be made reliable); guard pages, `MAP_NORESERVE`, `madvise` flags and
`mlock` (they stop mapping merges, change fork behaviour or are secrecy measures,
which this component does not claim); a builder that writes into its own writable
mapping (a second protection state and new OS code); movable packs (an empty state
on every read).

## Verification

`tests/pack.cpp` (`lorica.pack.unit`): LR-PACK-01 to -04, -07 and -08, with the
offset arithmetic's edges (exact fit, one past, align-up and `count * size`
overflow, `SIZE_MAX`) and every compile-time refusal as `static_assert`. It also
shows the stated limit that an in-range slot from another pack reads that pack.

`tests/pack_fault.cpp`, driven by `tests/pack_fault.py` (`lorica.pack.stops.*`):
children that write the first and the last used byte of a multi-page pack must end
with exactly SIGSEGV (Windows 0xC0000005), children reading through a slot outside
a smaller pack with `load` and with `at` must end with SIGABRT (Windows exit code
3), and a control child taking every other step must exit 0 (LR-PACK-05, -06). The
driver sets `handle_segv=0` in `ASAN_OPTIONS` and `TSAN_OPTIONS` so the result
holds in sanitizer builds.

`tests/pack_readers.cpp` (`lorica.pack.readers_tsan`, LR-PACK-09): eight readers;
registered only when `CMAKE_CXX_FLAGS` contains `-fsanitize=thread`, because
without ThreadSanitizer it cannot fail.

`examples/packing` (`lorica.demo.packing`): seals a configuration structure, a
lookup table and a string table and reads them back, then measures N integers held
as `sealed_value`s, as one pack and as heap allocations. Only checksums are judged.

Under GCC 13's AddressSanitizer and ThreadSanitizer the unit test fails at its
last check only, the absurd capacity: those runtimes' `operator new[]` reports
the oversized request and exits instead of throwing `std::bad_alloc`, even with
`allocator_may_return_null=1`. AddressSanitizer checks the builder's writes into its heap staging buffer but does
not see a read past the used bytes inside the OS mapping; the fault children prove
the read bound. Windows code paths were not
compiled or executed for the pack.
