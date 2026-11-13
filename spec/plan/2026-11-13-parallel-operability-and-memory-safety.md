# Parallel operability and memory safety: manual investigation (2026-11-13)

Owner's request: "detect per-function parallel operability, and investigate and
report memory safety and whether memory barriers are needed". The tool half is
`tools/lorica_analyze.py shared-state` ([self-report](2026-11-13-shared-state-report.md)).
This is the manual half: every function definition in `include/lorica/` and `src/`
read and judged by hand, backed by ThreadSanitizer and AddressSanitizer experiments.

Method: a per-function audit at 54f4e66 (119 rows), spot-checked by a second
reviewer who recounted the inventory, re-derived 30 rows and refuted one; carried to this tree by mapping
each row to its current line, re-reading every function changed since, applying the
correction and adding 26 rows for functions added since (`sealed_pack.hpp`,
`detail::holds`, the deleted constructors of `byte_reader` and `input_budget`).
145 rows (appendix): 105 functions with a body, the same set the shared-state tool
analyses (checked by file and line), plus 34 deleted functions, 1 defaulted
constructor and 5 lambdas written inside header functions. Not rows: implicitly
declared special members, the six C library declarations in `unsafe_api.hpp`, and
the lambdas the `LORICA_*` macros create at a caller's site.

Vocabulary. Parallel safety: `reentrant` (no state beyond arguments), `const-read`
(reads its own object, which nothing writes after construction), `caller-data-read`
(reads caller memory or calls caller code), `object-confined` (writes its own object
or the caller's destination), `internally-synchronized`, `process-global-effect`
(address space, stderr, termination). Barrier: `none`; `publication-only` (the object
must be published to the other thread by ordinary C++ synchronization: thread
start, a mutex, a release store read by an acquire load); `caller-must-synchronize`
(concurrent use of one object needs the caller's lock); `present-and-sufficient`
(Lorica synchronizes itself).

## A fence does not repair a data race

A memory barrier (`std::atomic_thread_fence`) never repairs a data race on a
non-atomic object. Two unsynchronized accesses to the same non-atomic object, one of
them a write, are undefined behaviour whatever fences surround them; a fence orders
only through an atomic object that both threads access. Shared plain data needs
`std::atomic` or the same lock at every access. Lorica adds no fence anywhere and
none of its functions needs one: the one atomic (the violation handler slot) carries
its own release/acquire ordering, and everything else is either immutable after a
safe publication or owned by one thread at a time.

## Answer per component

| Component | One instance shared between threads | Barrier / synchronization | Memory-safety preconditions left with the caller |
| --- | --- | --- | --- |
| `checked_size.hpp`, `checked_integer.hpp` | No instance: pure functions of their arguments, callable from any number of threads | None | None for memory. The `size_t` overloads convert operands by the language rules first (a negative or wider value is not detected) |
| `byte_view` | Yes, read-only, after safe publication | Publication of the view only (the falsifier's correction for `at`) | The declared size is the real extent of a live object; the bytes stay alive and are not written while viewed. Pointer validity, lifetime and provenance are not checked |
| `byte_reader` | No. Every read is a check followed by a cursor update: shared without a lock, TSan reports the race in `take` and at `-O0` the offset passed the end, `remaining()` wrapped and a 4096-byte view of a 64-byte buffer was granted. One reader per thread: `take()` a part per worker and give each its own reader (stated in the header since the review) | The caller's lock, or one reader per thread | As `byte_view`; a temporary container no longer compiles |
| `input_budget` | No. Shared without a lock, `consume` over-granted in 13,640 of 20,000 rounds at `-O2` and wrapped `remaining().bytes` at `-O0`. `permits_depth` alone races with nothing (it reads only the depth, which `consume` never writes); `remaining()` races with `consume`. Not copyable since the review | The caller's lock around `consume`, or one budget per request | Charges must precede the work they pay for; depth must be the true absolute depth |
| `copy_string`, `append_string`, `format_into` | Different destinations: yes. One destination: the caller's lock | None of their own | A pointer source is a live terminated string (null is rejected). `copy_string`/`append_string` accept a source inside the destination; `format_into` arguments must not refer to the destination (a `const char*` into it can still be read past the buffer, MEM-01, documented) |
| `sealed_value` | Yes: `load()` from any number of threads without a lock once the owner is safely published (LR-PACK-09 checks it under TSan); constructing and destroying different values on different threads is fine | Publication of the owner; destruction must not race a `load()` | The owner outlives every read: a `load()` racing the destructor is not a C++ data race (the destructor writes no C++ object, so TSan reports none) but a use-after-unmap that faulted, and a stale owner read another value once the page was reused |
| `pack_builder`, `sealed_pack` | Builder: one thread. Pack: as `sealed_value` | Builder: the caller's lock if shared; pack: publication only | `add_array` data holds `count` live elements; a slot's origin is the caller's (a slot from another or a destroyed pack that falls inside this one reads it, possibly as the wrong type); the staging buffer and returned copies are ordinary writable memory |
| Contracts runtime (`set_violation_handler`, `get_violation_handler`, `handle_violation`) | Yes: the slot is one `std::atomic` | `exchange(acq_rel)` and `load(acquire)`: present and needed, not for the pointer (relaxed is equally atomic and gives the same x86-64 code) but for what it publishes: with relaxed orders a handler reading state its installer wrote before installing it is a data race (TSan). Sufficient: no seq_cst needed for one atomic | A handler can run on several threads at once and must be safe for that. Replacing it does not wait for calls already inside it: before unloading a handler's module, stop the threads that can violate a contract or forward through a handler the host owns (a plugin unloaded while its handler ran crashed; a host-owned forwarder with an in-flight count did not). A handler that leaves by `longjmp` would leave the per-thread guard set (by reading, not run) |
| Default violation handler | Yes | stdio's stream lock: one `fprintf` per line since the review (before: 2,949 of 20,000 lines interleaved with 4 threads) | Not async-signal-safe (stdio). The first violation on a new thread of a runtime loaded with `dlopen` allocated once (thread-local storage); later ones allocate nothing |
| In-body macros (`LORICA_PRE`, `LORICA_POST`, `LORICA_POST_RETURN`, `LORICA_CONTRACT_ASSERT`) | No state of their own: the predicate runs on the calling thread | None | `LORICA_POST` sees parameters and locals by reference (it runs after the return value is constructed); `LORICA_POST_RETURN` passes an rvalue on by value since the review, so no reference to a temporary escapes |
| Overlay (`LORICA_CONTRACT`) | Yes: immutable after construction; concurrent calls are as safe as the callable, the predicates and the delegate (one shared `static const` overlay from 4 threads, with and without a delegate, and `test()`: TSan clean) | Publication of the overlay | A message is not copied and must outlive the overlay (normally a string literal); the callable must be callable as `const` |

Process-wide mutable state in the whole library: exactly two namespace-scope objects,
both in `src/contract_violation.cpp`: `std::atomic<violation_handler>
installed_handler` (constant-initialized, lock-free on x86-64) and `thread_local bool
handling_violation`. No static locals, no `mutable` members. Process-wide effects:
`stderr`, `abort`/trap, and the address space (`mmap`/`mprotect`/`munmap`,
`VirtualAlloc`/`VirtualProtect`/`VirtualFree`).

Totals over the 145 rows. Parallel safety: reentrant 65, const-read 28,
object-confined 26, caller-data-read 13, process-global-effect 10,
internally-synchronized 3; none is thread-hostile. Barrier: none 87,
publication-only 33, caller-must-synchronize 20, present-and-sufficient 5. (The
54f4e66 audit's own summary totals did not add up to its 119 rows; these counts are
taken from the rows.)

## Experiments

Recorded at 54f4e66 by the audit (GCC 13.3, glibc 2.39, x86-64; drivers in the
reviewer's scratch copy, run from its `exp/` directory with `-I../include`):

| What | Command | Outcome as recorded |
| --- | --- | --- |
| `sealed_value::load` from 8 threads on three shared values while 4 of them construct and destroy their own | `g++ -std=c++20 -O1 -g -fsanitize=thread sealed_load.cpp ../src/sealed_region_linux.cpp && ./sealed_load_tsan` | Clean, all values correct (8 x 200,000 loads); same without TSan at `-O2` |
| Owner destroyed while another thread loads | `... sealed_destroy_race.cpp ...` | No data-race report; the reader dies with `SEGV ... in sealed_value<int>::load()`, exit 66 (139 without TSan). Single-threaded reuse: `stale load() = 7777` |
| One `input_budget` shared by 4 threads, `consume(1,1,1)` | `... budget_race.cpp` | Race reported in `consume`. Without TSan: `-O2` over-granted 13,640 of 20,000 rounds; `-O0` `remaining.bytes=18446744073709551615` |
| `permits_depth` / `remaining()` concurrent with `consume` | `... budget_depth.cpp; ./depth_tsan; ./depth_tsan x` | `permits_depth`: no report; `remaining()`: race |
| One `byte_reader` shared by 4 threads, `take(1)` | `... reader_race.cpp; reader_race2.cpp at -O0/-O2` | Race in `remaining()`/`take`; at `-O0` offset 166 over a 64-byte buffer and `take(4096)` granted; at `-O2` no overshoot in 200,000 rounds |
| Handler slot: 2 installers, 4 violating threads, in-body macros and one shared overlay with and without a delegate, `test()` | `... contracts_mt.cpp ../src/contract_violation.cpp` | Clean; `raised=33376 handled a=30401 b=2975`, delegate exactly its share |
| `tests/contract_modules` rebuilt with TSan as three shared objects | `g++ -fsanitize=thread -fPIC -shared ...; ./modules_tsan shared` (5 runs) | Clean |
| Do the slot's orders matter? Installer writes a plain int, then installs a handler that reads it | `... publish.cpp <variant>` | Shipped orders: clean. Relaxed and plain-pointer mutants: data race in the handler |
| Slot stress with a start barrier | `... setget.cpp <variant>` | Shipped and relaxed: clean; plain pointer: races in set/get |
| The repository's threaded test against the two mutants, without TSan | `ctest -R contracts.modules` and 3,000 direct runs | Both mutants pass (CON-02): only a TSan build detects a non-atomic slot |
| Default handler, 4 threads x 5,000 violations | `default_interleave.cpp` against the Release runtime; `strace -f -e trace=write` | 2,949 of 20,000 lines malformed, 12 `write(2)` per violation; with one `fprintf`: 0 malformed (CON-01) |
| Plugin handler still running when its module is unloaded | `unload.cpp` + `libplugin.so` (`set_violation_handler(nullptr)`, `dlclose`) | Segmentation fault, exit 139 (CON-03, kept as the documented contract) |

Recorded by the falsifier: the CON-01 fix gives 0 malformed lines in 4 runs and 0
`malloc` calls during 100 violations; the plain-pointer mutant fails
`lorica.contracts.modules` in a `-fsanitize=thread` build of the tree; a host-owned
forwarding handler with an in-flight count survives the unload 3 of 3 times; making
the re-entry guard process-wide passed all registered tests and aborted any program
in which two threads violate at once (the killing test was added to
`tests/contract_modules`); with the runtime loaded by `dlopen`, the first violation
of a new thread made 1 allocation and the second 0.

Re-run on this tree (GCC 13.3, `g++ -std=c++20 -O1 -g -fsanitize=thread
-I<tree>/include <driver> [<tree>/src/<file>] -pthread`, drivers copied from the audit):

| Driver | Outcome |
| --- | --- |
| `sealed_load.cpp` + `sealed_region_linux.cpp` | exit 0, 0 warnings, `sealed_load: ok` |
| `sealed_destroy_race.cpp` + `sealed_region_linux.cpp` | exit 66, 0 data-race warnings, `ThreadSanitizer: SEGV` in `sealed_value<int>::load() const include/lorica/sealed_value.hpp:21` |
| `budget_race.cpp` | exit 66, 6 warnings, races at `input_budget.hpp:26`, `:27`, `:28` in `consume` |
| `budget_depth.cpp`; same with argument `x` | exit 0, 0 warnings, `budget_depth: 1 0`; with `x`: exit 66, race at `input_budget.hpp:39` in `remaining() const` |
| `reader_race.cpp` | exit 66, 2 warnings, race at `byte_reader.hpp:44` in `take` |
| `contracts_mt.cpp` + `contract_violation.cpp` | exit 0, 0 warnings, `raised=1278836 handled a=735440 b=543396 (default got the rest: 0); delegate=639418` |
| `publish.cpp` + `contract_violation.cpp` | exit 0, 0 warnings, `seen=1420371` |

And the registered suite under the sanitizers on this tree
([SPEC-LR-SANITIZERS](../test/verification.md)): GCC `-fsanitize=thread` with
`-DLORICA_ANALYSIS_TSAN_ORACLE=ON`, 99 of 99 passed, including
`lorica.pack.readers_tsan` (eight unsynchronized readers of a pack and a sealed
value), `lorica.protection` (four concurrent readers), `lorica.contracts.modules`
(exchanges from two threads through two modules, a violation on a second thread while
a handler runs) and `lorica.analysis.shared_state.tsan`; GCC
`-fsanitize=address,undefined -fno-sanitize-recover=all`, 97 tests, 96 passed and
`lorica.hardening_stops.fortify` skipped, no sanitizer report.

## The manual table and the shared-state tool

Same functions: the tool's 105 analysed functions are exactly the manual table's
rows with a body. Where they agree: the tool's two `self-synchronized(unverified)`
functions are the manual table's internally synchronized `set_violation_handler`
and `get_violation_handler`; its 46 data hold the same two non-member objects (the
atomic, `acq_rel,acquire`, and the `thread_local`, not shared); its
`caller-must-synchronize` members (`byte_reader`, `input_budget`, `pack_builder`,
the overlay's parts) are the classes the manual table marks object-confined or
caller-must-synchronize; 28 of its 36 `no-shared-state` functions are the manual
table's reentrant ones; it flags the default handler's `stderr` as a shared stream.

Where the tool is more conservative: the by-value parameters that `contract`,
`make_post_guard` and the `const&` overloads of `pre`/`post`/`on_violation` move
from are counted as caller data written (`caller-synchronized:write`); the manual
table reads them as the function's own copies. Its 13 `unknown` functions call a
callable, predicate, handler or intrinsic it cannot resolve; the manual table
resolves them from the call sites (the macros and the overlay create the predicate
closure per evaluation, so it is never shared).

What the tool cannot see, and the manual table and the experiments supply:
- memory safety: lifetime, provenance, the real extent behind a pointer, aliasing
  between a destination and an argument, use after unmap; the tool reads text and
  judges synchronization only;
- process-wide effects through a call into another file: it marks the
  `sealed_value` constructor `no-shared-state` although it maps memory through
  `sealed_region`, and it does not flag `write_text`'s `fputs` to `stderr` as a
  shared stream;
- whether an order is sufficient (it says `unverified`), whether a race happens
  (TSan does), line atomicity of stdio output (only the experiment showed CON-01),
  how long a handler's code stays loaded (CON-03);
- deleted and defaulted functions, lambdas, and code paths of a Windows build
  beyond their text.

## Not executed

- Windows: `src/sealed_region_windows.cpp`, the `__fastfail` path and the MSVC STL
  were read, not compiled or run here; the two Windows rows are judgement only.
  `.github/workflows/ci.yml` builds and runs the suite with MSVC from its first run.
- Clang ThreadSanitizer and AddressSanitizer (no compiler-rt on this host); every
  sanitizer result here is GCC 13.3 libtsan/libasan.
- Non-x86 targets: on x86-64 every order gives the same code; that acquire/release
  differs from relaxed in generated code on AArch64 or POWER was not compiled or run.
- The standard's wording for `set_terminate`, quoted from memory by the audit.
- A handler leaving by `longjmp`, `LORICA_POST` in a coroutine resumed on another
  thread, thread cancellation inside stdio, contracts violated in signal handlers:
  reasoned, not run. No document claims any of them.
- Helgrind/DRD; 32-bit targets; `sealed_pack` on Windows.

## Appendix: per-function table

Location is the line on this tree. Line references `Lnn` inside a row are lines of
the row's own file on this tree; rows marked unchanged keep the 54f4e66 wording.

| # | Function | Location (head) | Shared state | Parallel safety | Barrier | Memory safety | Since 54f4e66 |
| --- | --- | --- | --- | --- | --- | --- | --- |
| 1 | `lorica::detail::source_text<C,S>(const S&)` | include/lorica/bounded_text.hpp:51 | Reads caller memory through source: the array elements, or the characters reached through the string/view/pointer it converts to. No globals. | caller-data-read | none | Array branch bounded by std::extent (L53). Otherwise a basic_string_view is built from S (L60): a null pointer source now returns empty (L57-59, rejected at compile time for nullptr_t by text_source); a non-null const C* is an unbounded strlen and must be terminated; a view must refer to live storage. An embedded terminator is refused (L61). | changed: null pointer source rejected |
| 2 | `lorica::detail::put_text<C>(std::span<C>, std::size_t, std::basic_string_view<C>)` | include/lorica/bounded_text.hpp:69 | Writes caller memory out[at .. at+text.size()]; reads text. | object-confined | none | Not checked inside: out.data()+at (L70) and out[at+text.size()] (L71) rely on at+text.size() < out.size(). Both callers establish it (L103, L122). char_traits::move tolerates overlap. | unchanged |
| 3 | `lorica::copy_string<D,S>(D&&, const S&)` | include/lorica/bounded_text.hpp:98 | Writes the destination range; reads source (see source_text). | object-confined | none | Writes are checked: empty destination rejected (L101), size compared before writing (L103). Reads inherit source_text's strlen precondition for pointer sources. | unchanged |
| 4 | `lorica::append_string<D,S>(D&&, const S&)` | include/lorica/bounded_text.hpp:116 | Reads and writes the destination range; reads source. | object-confined | none | Checked: the terminator search is bounded by the span (L120), remaining room compared before writing (L122). The source is now read even when the destination is full (L121), so a pointer source must meet source_text's precondition in every call. | changed |
| 5 | `lorica::format_into<D,Args...>(D&&, std::format_string<Args...>, Args&&...)` | include/lorica/bounded_text.hpp:144 | Writes the destination range; reads the arguments and whatever their formatters read (the global locale for an L specifier; a heap buffer inside the library on some paths). | object-confined | none | Writes are bounded: format_to_n limited to size-1 (L152, L159), the size checked (L162) and output holding a terminator refused (L167). The early terminator write was removed, and arguments must not refer to the destination (documented precondition, as for snprintf): a const char* argument into the destination can still be read past it (MEM-01 case 1); a view of the current content now returns a consistent result. | changed: MEM-01 fixed as documented precondition |
| 6 | `lorica::byte_reader::byte_reader() [defaulted]` | include/lorica/byte_reader.hpp:29 | Initialises its own members (empty span, offset 0). | reentrant | none | No memory access. | unchanged |
| 7 | `lorica::byte_reader::byte_reader(std::span<const std::byte>)` | include/lorica/byte_reader.hpp:30 | Stores the caller's span (pointer and size); no dereference. | reentrant | none | No access; the stored view must stay alive and unchanged for the reader's lifetime (class comment L26-23). | unchanged |
| 8 | `lorica::byte_reader::byte_reader<R>(R&&) = delete` | include/lorica/byte_reader.hpp:34 | None (deleted: a temporary container would die before the first read). | reentrant | none | No body. | new since 54f4e66 |
| 9 | `lorica::byte_reader::size() const` | include/lorica/byte_reader.hpp:36 | Reads this->bytes_, which no member function writes after construction (only whole-object assignment does). | const-read | publication-only | No dereference. | unchanged |
| 10 | `lorica::byte_reader::offset() const` | include/lorica/byte_reader.hpp:37 | Reads this->offset_, which take/skip/read*/read_prefixed write. | object-confined | caller-must-synchronize | No dereference. | unchanged |
| 11 | `lorica::byte_reader::remaining() const` | include/lorica/byte_reader.hpp:38 | Reads this->bytes_ and this->offset_. | object-confined | caller-must-synchronize | No dereference, but bytes_.size() - offset_ (L38) wraps to a huge value if the invariant offset_ <= size is broken; observed after a race: remaining()=18446744073709551514. | unchanged |
| 12 | `lorica::byte_reader::take(std::size_t)` | include/lorica/byte_reader.hpp:41 | Reads bytes_, reads and writes this->offset_; returns a view into caller memory (no dereference). | object-confined | caller-must-synchronize | Checked on one thread: count > remaining() rejected (L42) before subspan (L43) and the increment (L44). The check-then-add is not atomic: shared across threads at -O0 the offset reached 166 for a 64-byte buffer and take(4096) was then granted. | unchanged |
| 13 | `lorica::byte_reader::skip(std::size_t)` | include/lorica/byte_reader.hpp:48 | As take(): reads and writes this->offset_. | object-confined | caller-must-synchronize | Checked through take(). | unchanged |
| 14 | `lorica::byte_reader::read<T,Order>()` | include/lorica/byte_reader.hpp:53 | As take(), and dereferences sizeof(T) bytes of the caller's buffer. | object-confined | caller-must-synchronize | Checked: the bytes come from take(sizeof(T)) (L63-56) and the index is < sizeof(T) (L66-61). The caller's buffer must be live and unchanged. | unchanged |
| 15 | `lorica::byte_reader::read_big_endian<T>()` | include/lorica/byte_reader.hpp:68 | As read(). | object-confined | caller-must-synchronize | Checked through read(). | unchanged |
| 16 | `lorica::byte_reader::read_little_endian<T>()` | include/lorica/byte_reader.hpp:72 | As read(). | object-confined | caller-must-synchronize | Checked through read(). | unchanged |
| 17 | `lorica::byte_reader::read_prefixed<Length,Order>()` | include/lorica/byte_reader.hpp:80 | Reads and writes this->offset_ several times, including a rollback; dereferences the length bytes. | object-confined | caller-must-synchronize | Checked on one thread: length through narrow<size_t> (L83), body through take (L84), offset restored on failure (L85). | unchanged |
| 18 | `lorica::byte_view::make(const std::byte*, std::size_t, std::size_t) [static]` | include/lorica/byte_view.hpp:12 | None: arguments only; the pointer is stored, not dereferenced. | reentrant | none | No access. Rejects size > maximum and null with non-zero size (L14); it cannot verify that data really has size bytes (class comment L8-9). | unchanged |
| 19 | `lorica::byte_view::size() const` | include/lorica/byte_view.hpp:18 | Reads this->size_ (set in the constructor; changed only by whole-object assignment). | const-read | publication-only | No dereference. | unchanged |
| 20 | `lorica::byte_view::at(std::size_t) const` | include/lorica/byte_view.hpp:19 | Reads this->data_/size_ and one byte of caller memory. | caller-data-read | publication-only | Checked against the declared size (L20) before data_[index] (L21); the declared size and the lifetime of the storage are the caller's precondition. | corrected by the falsifier: reads this->data_/size_, so the view needs safe publication; the underlying bytes must not be written concurrently |
| 21 | `lorica::byte_view::subview(std::size_t, std::size_t) const` | include/lorica/byte_view.hpp:23 | Reads this->data_/size_; no dereference. | const-read | publication-only | Pointer arithmetic data_ + offset only after contains_range (L25-27), and not at all for offset 0, so null + 0 is avoided. | unchanged |
| 22 | `lorica::byte_view::byte_view(const std::byte*, std::size_t) [private]` | include/lorica/byte_view.hpp:31 | Initialises its own members. | reentrant | none | No access. | unchanged |
| 23 | `lorica::narrow<To,From>(From)` | include/lorica/checked_integer.hpp:32 | None. | reentrant | none | No memory access (values only). | signature: From deduced only (int&...) |
| 24 | `lorica::checked_add<int&...,L,R>(L, R) = delete` | include/lorica/checked_integer.hpp:51 | None (deleted: no body, cannot be called). | reentrant | none | n/a (no body). | unchanged |
| 25 | `lorica::checked_subtract<int&...,L,R>(L, R) = delete` | include/lorica/checked_integer.hpp:52 | None (deleted: no body, cannot be called). | reentrant | none | n/a (no body). | unchanged |
| 26 | `lorica::checked_multiply<int&...,L,R>(L, R) = delete` | include/lorica/checked_integer.hpp:53 | None (deleted: no body, cannot be called). | reentrant | none | n/a (no body). | unchanged |
| 27 | `lorica::checked_divide<int&...,L,R>(L, R) = delete` | include/lorica/checked_integer.hpp:54 | None (deleted: no body, cannot be called). | reentrant | none | n/a (no body). | unchanged |
| 28 | `lorica::saturating_add<int&...,L,R>(L, R) = delete` | include/lorica/checked_integer.hpp:55 | None (deleted: no body, cannot be called). | reentrant | none | n/a (no body). | unchanged |
| 29 | `lorica::saturating_subtract<int&...,L,R>(L, R) = delete` | include/lorica/checked_integer.hpp:56 | None (deleted: no body, cannot be called). | reentrant | none | n/a (no body). | unchanged |
| 30 | `lorica::saturating_multiply<int&...,L,R>(L, R) = delete` | include/lorica/checked_integer.hpp:57 | None (deleted: no body, cannot be called). | reentrant | none | n/a (no body). | unchanged |
| 31 | `lorica::checked_add<int&...,T,U>(T, U)` | include/lorica/checked_integer.hpp:64 | None. | reentrant | none | No memory access (values only). | unchanged |
| 32 | `lorica::checked_subtract<int&...,T,U>(T, U)` | include/lorica/checked_integer.hpp:77 | None. | reentrant | none | No memory access (values only). | unchanged |
| 33 | `lorica::checked_multiply<int&...,T,U>(T, U)` | include/lorica/checked_integer.hpp:90 | None. | reentrant | none | No memory access (values only). | unchanged |
| 34 | `lorica::checked_divide<int&...,T,U>(T, U)` | include/lorica/checked_integer.hpp:110 | None. | reentrant | none | No memory access (values only). | unchanged |
| 35 | `lorica::saturating_add<int&...,T,U>(T, U)` | include/lorica/checked_integer.hpp:123 | None. | reentrant | none | No memory access (values only). | changed: always computed from checked_add<>, no <numeric> path |
| 36 | `lorica::saturating_subtract<int&...,T,U>(T, U)` | include/lorica/checked_integer.hpp:131 | None. | reentrant | none | No memory access (values only). | changed: always computed from checked_subtract, no <numeric> path |
| 37 | `lorica::saturating_multiply<int&...,T,U>(T, U)` | include/lorica/checked_integer.hpp:139 | None. | reentrant | none | No memory access (values only). | changed: always computed from checked_multiply<>, no <numeric> path |
| 38 | `lorica::saturate_cast<To,From>(From)` | include/lorica/checked_integer.hpp:147 | None. | reentrant | none | No memory access (values only). | signature: From deduced only (int&...); no <numeric> path |
| 39 | `lorica::checked_add(std::size_t, std::size_t)` | include/lorica/checked_size.hpp:12 | None. | reentrant | none | No memory access (values only). | unchanged |
| 40 | `lorica::checked_multiply(std::size_t, std::size_t)` | include/lorica/checked_size.hpp:18 | None. | reentrant | none | No memory access (values only). | unchanged |
| 41 | `lorica::contains_range(std::size_t, std::size_t, std::size_t)` | include/lorica/checked_size.hpp:25 | None. | reentrant | none | No memory access (values only). | unchanged |
| 42 | `lorica::input_budget::input_budget(budget_limits)` | include/lorica/input_budget.hpp:17 | Initialises its own member remaining_. | reentrant | none | No memory access. | unchanged |
| 43 | `lorica::input_budget::input_budget(const input_budget&) = delete` | include/lorica/input_budget.hpp:19 | None (deleted: a copy would be a second budget). | reentrant | none | No body. | new since 54f4e66 |
| 44 | `lorica::input_budget::operator=(const input_budget&) = delete` | include/lorica/input_budget.hpp:20 | None (deleted). | reentrant | none | No body. | new since 54f4e66 |
| 45 | `lorica::input_budget::consume(std::size_t, std::size_t, std::size_t)` | include/lorica/input_budget.hpp:22 | Reads and writes this->remaining_.bytes/.elements/.allocations (not .depth). | object-confined | caller-must-synchronize | No pointer access. The check (L27-25) and the three subtractions (L29-28) are not atomic: shared by 4 threads, 13640 of 20000 rounds granted more than the limit (-O2) and at -O0 remaining.bytes wrapped to 18446744073709551615. | unchanged |
| 46 | `lorica::input_budget::permits_depth(std::size_t) const` | include/lorica/input_budget.hpp:36 | Reads this->remaining_.depth, which no member function writes after construction. | const-read | publication-only | No memory access beyond the member. | unchanged |
| 47 | `lorica::input_budget::remaining() const` | include/lorica/input_budget.hpp:39 | Reads all four members of this->remaining_. | object-confined | caller-must-synchronize | No memory access beyond the members. | unchanged |
| 48 | `lorica::sealed_value<T>::sealed_value(T)` | include/lorica/sealed_value.hpp:14 | Creates a private read-only OS mapping (process address space) through detail::sealed_region; reads its own by-value parameter. | process-global-effect | publication-only | Passes &value and sizeof(value) of its own parameter (L14): size and pointer cannot be wrong. | unchanged |
| 49 | `lorica::sealed_value<T>::sealed_value(const sealed_value&) = delete` | include/lorica/sealed_value.hpp:15 | None (deleted: no body, cannot be called). | reentrant | none | n/a (no body). | unchanged |
| 50 | `lorica::sealed_value<T>::operator=(const sealed_value&) = delete` | include/lorica/sealed_value.hpp:16 | None (deleted: no body, cannot be called). | reentrant | none | n/a (no body). | unchanged |
| 51 | `lorica::sealed_value<T>::sealed_value(sealed_value&&) = delete` | include/lorica/sealed_value.hpp:17 | None (deleted: no body, cannot be called). | reentrant | none | n/a (no body). | unchanged |
| 52 | `lorica::sealed_value<T>::operator=(sealed_value&&) = delete` | include/lorica/sealed_value.hpp:18 | None (deleted: no body, cannot be called). | reentrant | none | n/a (no body). | unchanged |
| 53 | `lorica::sealed_value<T>::load() const` | include/lorica/sealed_value.hpp:19 | Reads this->storage_.data_ and sizeof(T) bytes of the read-only mapping. | const-read | publication-only | memcpy of exactly sizeof(T) from the mapping (L21): safe while the owner is alive. After destruction the read faults (SIGSEGV observed) or, if the page was handed out again, silently returns the other value (7777 observed). | unchanged |
| 54 | `lorica::detail::place_in_pack(std::size_t, std::size_t, std::size_t, std::size_t, std::size_t)` | include/lorica/sealed_pack.hpp:32 | None. | reentrant | none | Values only: checked_multiply, checked_add, contains_range (L34-40); alignment must be a power of two (callers pass alignof(T)). | new since 54f4e66 |
| 55 | `lorica::pack_slot<T>::pack_slot(std::size_t) [private]` | include/lorica/sealed_pack.hpp:54 | Initialises its own member. | reentrant | none | No memory access. | new since 54f4e66 |
| 56 | `lorica::pack_array_slot<T>::size() const` | include/lorica/sealed_pack.hpp:62 | Reads this->count_ (never written after construction). | const-read | publication-only | No memory access beyond the member. | new since 54f4e66 |
| 57 | `lorica::pack_array_slot<T>::pack_array_slot(std::size_t, std::size_t) [private]` | include/lorica/sealed_pack.hpp:66 | Initialises its own members. | reentrant | none | No memory access. | new since 54f4e66 |
| 58 | `lorica::pack_builder::pack_builder(std::size_t)` | include/lorica/sealed_pack.hpp:76 | Allocates its own zeroed staging buffer (new[], L78); the global heap is internally synchronized. | reentrant | none | Throws invalid_argument for 0 and bad_alloc when the heap refuses; the capacity is the caller's to bound (trusted configuration or an input_budget). | new since 54f4e66 |
| 59 | `lorica::pack_builder::pack_builder(const pack_builder&) = delete` | include/lorica/sealed_pack.hpp:80 | None (deleted). | reentrant | none | No body. | new since 54f4e66 |
| 60 | `lorica::pack_builder::operator=(const pack_builder&) = delete` | include/lorica/sealed_pack.hpp:81 | None (deleted). | reentrant | none | No body. | new since 54f4e66 |
| 61 | `lorica::pack_builder::pack_builder(pack_builder&&) = delete` | include/lorica/sealed_pack.hpp:82 | None (deleted). | reentrant | none | No body. | new since 54f4e66 |
| 62 | `lorica::pack_builder::operator=(pack_builder&&) = delete` | include/lorica/sealed_pack.hpp:83 | None (deleted). | reentrant | none | No body. | new since 54f4e66 |
| 63 | `lorica::pack_builder::add<T>(const T&)` | include/lorica/sealed_pack.hpp:86 | Reads and writes this->used_ (through reserve) and the staging bytes; reads the caller's value. | object-confined | caller-must-synchronize | memcpy of sizeof(T) bytes at an offset reserve() proved inside capacity (L88-90); the value must be a live T. | new since 54f4e66 |
| 64 | `lorica::pack_builder::add_array<T>(const T*, std::size_t)` | include/lorica/sealed_pack.hpp:94 | As add; reads count elements of caller memory. | object-confined | caller-must-synchronize | Null with a nonzero count is refused (L96) and count*sizeof(T) is checked (place_in_pack); that data really holds count live elements is the caller's precondition. | new since 54f4e66 |
| 65 | `lorica::pack_builder::used() const` | include/lorica/sealed_pack.hpp:102 | Reads this->used_, which add and sealing write. | object-confined | caller-must-synchronize | No memory access beyond the member. | new since 54f4e66 |
| 66 | `lorica::pack_builder::capacity() const` | include/lorica/sealed_pack.hpp:103 | Reads this->capacity_, which sealing writes. | object-confined | caller-must-synchronize | No memory access beyond the member. | new since 54f4e66 |
| 67 | `lorica::pack_builder::reserve(std::size_t, std::size_t, std::size_t) [private]` | include/lorica/sealed_pack.hpp:107 | Reads staging_, used_, capacity_; writes used_. | object-confined | caller-must-synchronize | A consumed builder refuses (L108). | new since 54f4e66 |
| 68 | `lorica::sealed_pack::sealed_pack(pack_builder&&)` | include/lorica/sealed_pack.hpp:126 | Creates one OS mapping through sealed_region (process address space); reads, then empties the builder (L127-130). | process-global-effect | publication-only (pack); the builder must not be used concurrently | Copies exactly builder.used_ bytes from the builder's own staging buffer; nothing added (used_ 0) throws in sealed_region, leaving the builder unchanged. | new since 54f4e66 |
| 69 | `lorica::sealed_pack::sealed_pack(const sealed_pack&) = delete` | include/lorica/sealed_pack.hpp:132 | None (deleted). | reentrant | none | No body. | new since 54f4e66 |
| 70 | `lorica::sealed_pack::operator=(const sealed_pack&) = delete` | include/lorica/sealed_pack.hpp:133 | None (deleted). | reentrant | none | No body. | new since 54f4e66 |
| 71 | `lorica::sealed_pack::sealed_pack(sealed_pack&&) = delete` | include/lorica/sealed_pack.hpp:134 | None (deleted). | reentrant | none | No body. | new since 54f4e66 |
| 72 | `lorica::sealed_pack::operator=(sealed_pack&&) = delete` | include/lorica/sealed_pack.hpp:135 | None (deleted). | reentrant | none | No body. | new since 54f4e66 |
| 73 | `lorica::sealed_pack::load<T>(pack_slot<T>) const` | include/lorica/sealed_pack.hpp:138 | Reads this->region_, used_ and the sealed mapping (immutable after construction). | const-read | publication-only | Bounded by read() (terminates outside the used bytes); a slot from another or a destroyed pack that falls inside is not detected (slot origin is the caller's precondition). | new since 54f4e66 |
| 74 | `lorica::sealed_pack::at<T>(pack_array_slot<T>, std::size_t) const` | include/lorica/sealed_pack.hpp:141 | As load. | const-read | publication-only | index < count is a value check (L142); offset + index*sizeof(T) is bounded again by read(), also if it wrapped. | new since 54f4e66 |
| 75 | `lorica::sealed_pack::read<T>(std::size_t) const [private]` | include/lorica/sealed_pack.hpp:148 | Reads used_, region_.data() and sizeof(T) sealed bytes. | const-read | publication-only | contains_range(used_, offset, sizeof(T)) or std::terminate (L150), then memcpy into a local (L151-152). | new since 54f4e66 |
| 76 | `lorica::detail::sealed_region::sealed_region(const sealed_region&) = delete` | include/lorica/detail/sealed_region.hpp:11 | None (deleted: no body, cannot be called). | reentrant | none | n/a (no body). | unchanged |
| 77 | `lorica::detail::sealed_region::operator=(const sealed_region&) = delete` | include/lorica/detail/sealed_region.hpp:12 | None (deleted: no body, cannot be called). | reentrant | none | n/a (no body). | unchanged |
| 78 | `lorica::detail::sealed_region::sealed_region(sealed_region&&) = delete` | include/lorica/detail/sealed_region.hpp:13 | None (deleted: no body, cannot be called). | reentrant | none | n/a (no body). | unchanged |
| 79 | `lorica::detail::sealed_region::operator=(sealed_region&&) = delete` | include/lorica/detail/sealed_region.hpp:14 | None (deleted: no body, cannot be called). | reentrant | none | n/a (no body). | unchanged |
| 80 | `lorica::detail::sealed_region::data() const` | include/lorica/detail/sealed_region.hpp:15 | Reads this->data_ (written only by the constructor). | const-read | publication-only | Returns the mapping address as const void*; no dereference. The pointer dangles after the destructor (data_ is not cleared). | unchanged |
| 81 | `lorica::detail::sealed_region::sealed_region(const void*, std::size_t) [Linux]` | src/sealed_region_linux.cpp:12 | Process address space (mmap, mprotect, munmap on failure); errno (thread-local); reads size bytes through source; writes its own members. | process-global-effect | publication-only | memcpy(data_, source, size_) (L19) trusts that source has size bytes (null and zero rejected at L13; library callers pass sizeof(T) or a builder's used bytes). The page is writable between mmap (L14) and mprotect (L20). The unreachable null-address branch was removed. | changed |
| 82 | `lorica::detail::sealed_region::~sealed_region() [Linux]` | src/sealed_region_linux.cpp:28 | Process address space (munmap); reads this->data_/size_. | process-global-effect | caller-must-synchronize | Unmaps without clearing data_ (L29): a reader still running or arriving later is a use-after-unmap. A refusal with ENOMEM (a merged mapping split at vm.max_map_count) leaves the page mapped read-only (L32); any other failure terminates (L33). | changed: ENOMEM keeps the page |
| 83 | `lorica::detail::sealed_region::sealed_region(const void*, std::size_t) [Windows]` | src/sealed_region_windows.cpp:13 | Process address space (VirtualAlloc, VirtualProtect, VirtualFree on failure); GetLastError (thread-local); reads size bytes through source; writes its own members. | process-global-effect | publication-only | memcpy(data_, source, size_) (L18) trusts the caller's size, as on Linux. Writable between VirtualAlloc (L15) and VirtualProtect (L20). | unchanged |
| 84 | `lorica::detail::sealed_region::~sealed_region() [Windows]` | src/sealed_region_windows.cpp:28 | Process address space (VirtualFree); reads this->data_. | process-global-effect | caller-must-synchronize | Releases the region without clearing data_ (L30); later reads are use-after-free. std::terminate if VirtualFree fails. | unchanged |
| 85 | `lorica::contracts::source_location::file_name() const` | include/lorica/contract_violation.hpp:34 | Reads this->file (public member of an aggregate). | const-read | publication-only | Returns the stored pointer; no dereference. The string must outlive every use (a __FILE__ literal when produced by the macros). | unchanged |
| 86 | `lorica::contracts::source_location::function_name() const` | include/lorica/contract_violation.hpp:35 | Reads this->function. | const-read | publication-only | Returns the stored pointer; no dereference. | unchanged |
| 87 | `lorica::contracts::source_location::line() const` | include/lorica/contract_violation.hpp:36 | Reads this->line_number. | const-read | publication-only | No pointer access. | unchanged |
| 88 | `lorica::contracts::contract_violation::contract_violation(assertion_kind, evaluation_semantic, detection_mode, const char*, source_location, std::exception_ptr)` | include/lorica/contract_violation.hpp:42 | Initialises its own members; copies the exception_ptr (the standard library's atomic reference count on the exception object). | reentrant | none | Stores comment and the location strings as raw pointers without copying; they must outlive the object. | unchanged |
| 89 | `lorica::contracts::contract_violation::contract_violation(const contract_violation&) = delete` | include/lorica/contract_violation.hpp:47 | None (deleted: no body, cannot be called). | reentrant | none | n/a (no body). | unchanged |
| 90 | `lorica::contracts::contract_violation::operator=(const contract_violation&) = delete` | include/lorica/contract_violation.hpp:48 | None (deleted: no body, cannot be called). | reentrant | none | n/a (no body). | unchanged |
| 91 | `lorica::contracts::contract_violation::kind() const` | include/lorica/contract_violation.hpp:50 | Reads this->kind_ (immutable after construction). | const-read | publication-only | No pointer access. | unchanged |
| 92 | `lorica::contracts::contract_violation::semantic() const` | include/lorica/contract_violation.hpp:51 | Reads this->semantic_ (immutable after construction). | const-read | publication-only | No pointer access. | unchanged |
| 93 | `lorica::contracts::contract_violation::mode() const` | include/lorica/contract_violation.hpp:52 | Reads this->mode_ (immutable after construction). | const-read | publication-only | No pointer access. | unchanged |
| 94 | `lorica::contracts::contract_violation::comment() const` | include/lorica/contract_violation.hpp:54 | Reads this->comment_ (immutable after construction). | const-read | publication-only | Returns the raw pointer given at the checking site: a literal for the macros, the caller's message pointer for an overlay (must still be alive). | unchanged |
| 95 | `lorica::contracts::contract_violation::location() const` | include/lorica/contract_violation.hpp:55 | Reads this->location_ (immutable after construction). | const-read | publication-only | Copies three scalars; the two string pointers are not dereferenced. | unchanged |
| 96 | `lorica::contracts::contract_violation::evaluation_exception() const` | include/lorica/contract_violation.hpp:57 | Reads this->evaluation_exception_ and increments the exception object's reference count (atomic inside the standard library). | const-read | publication-only | Returns an owning exception_ptr copy; safe. | unchanged |
| 97 | `lorica::contracts::contract_violation::is_terminating() const` | include/lorica/contract_violation.hpp:61 | Reads this->semantic_. | const-read | publication-only | No pointer access. | unchanged |
| 98 | `lorica::contracts::(anonymous namespace)::handler_scope::handler_scope()` | src/contract_violation.cpp:16 | Writes the thread_local flag handling_violation (L12). | object-confined | none | No pointer access. | unchanged |
| 99 | `lorica::contracts::(anonymous namespace)::handler_scope::~handler_scope()` | src/contract_violation.cpp:17 | Writes the thread_local flag handling_violation. | object-confined | none | No pointer access. | unchanged |
| 100 | `lorica::contracts::(anonymous namespace)::handler_scope::handler_scope(const handler_scope&) = delete` | src/contract_violation.cpp:18 | None (deleted: no body, cannot be called). | reentrant | none | n/a (no body). | unchanged |
| 101 | `lorica::contracts::(anonymous namespace)::handler_scope::operator=(const handler_scope&) = delete` | src/contract_violation.cpp:19 | None (deleted: no body, cannot be called). | reentrant | none | n/a (no body). | unchanged |
| 102 | `lorica::contracts::(anonymous namespace)::write_text(const char*)` | src/contract_violation.cpp:22 | Writes to stderr (one fputs, locked by stdio for this call); reads the caller's string. Since the default handler became one fprintf, it is used only for the re-entry message (contract_violation.cpp:90). | process-global-effect | present-and-sufficient | fputs reads text up to its terminator (L23): the pointer must be a live terminated string; null is replaced by "(null)". | changed caller |
| 103 | `lorica::contracts::set_violation_handler(violation_handler)` | src/contract_violation.cpp:28 | Reads and writes the process-wide std::atomic<violation_handler> installed_handler (L9). | internally-synchronized | present-and-sufficient | Stores a function pointer; no dereference. The code it points to must stay loaded as long as any thread can still call it. | unchanged |
| 104 | `lorica::contracts::get_violation_handler()` | src/contract_violation.cpp:33 | Reads the process-wide std::atomic<violation_handler> installed_handler (L9). | internally-synchronized | present-and-sufficient | Returns a function pointer; no dereference. | unchanged |
| 105 | `lorica::contracts::to_string(assertion_kind)` | src/contract_violation.cpp:38 | None; returns pointers to string literals. | reentrant | none | No pointer access; an out-of-range enumerator returns "unknown" (L44). | unchanged |
| 106 | `lorica::contracts::to_string(evaluation_semantic)` | src/contract_violation.cpp:48 | None; returns pointers to string literals. | reentrant | none | No pointer access; out-of-range returns "unknown" (L55). | unchanged |
| 107 | `lorica::contracts::to_string(detection_mode)` | src/contract_violation.cpp:59 | None; returns pointers to string literals. | reentrant | none | No pointer access; out-of-range returns "unknown" (L64). | unchanged |
| 108 | `lorica::contracts::invoke_default_contract_violation_handler(const contract_violation&)` | src/contract_violation.cpp:68 | Writes one line to stderr with one fprintf and flushes it; reads the violation and the strings it points to. | process-global-effect | present-and-sufficient | Dereferences file, function and comment strings through fprintf %s (L74-77): live terminated strings; null is printed as (null) (L71). | changed: CON-01 fixed; one stdio call holds the stream lock for the whole line |
| 109 | `lorica::contracts::detail::handle_violation(violation_sink, const void*, assertion_kind, evaluation_semantic, detection_mode, const char*, source_location, std::exception_ptr)` | src/contract_violation.cpp:83 | Reads installed_handler (atomic, through get_violation_handler); reads and writes the thread_local handling_violation; calls the handler or the sink (arbitrary code); writes stderr; may abort the process. | internally-synchronized | present-and-sufficient for the slot; a handler's lifetime is the caller's | Calls sink(context, ...) (L98) and handler(...) (L100) through pointers whose code and state it does not keep alive; the violation object lives on this stack frame only (L86). | CON-03 kept as the documented contract (falsifier): the header now says a handler can run on several threads at once and replacing it does not wait for calls in flight |
| 110 | `lorica::contracts::detail::trap()` | include/lorica/contracts.hpp:50 | Terminates the process (__builtin_trap / __fastfail(7)). | process-global-effect | none | No memory access. | unchanged |
| 111 | `lorica::contracts::detail::contract_violated_during_constant_evaluation()` | include/lorica/contracts.hpp:60 | Terminates the process through trap() if ever reached at run time. | process-global-effect | none | No memory access. | unchanged |
| 112 | `lorica::contracts::detail::holds<Condition>(const Condition&)` | include/lorica/contracts.hpp:65 | Reads the caller's condition value; may call its operator bool. | caller-data-read | none | No memory access of its own. | new since 54f4e66 |
| 113 | `lorica::contracts::detail::evaluate_at_runtime<Semantic,Predicate>(assertion_kind, Predicate&, const char*, source_location, violation_sink, const void*)` | include/lorica/contracts.hpp:68 | Calls the caller's predicate through a non-const reference; uses the thread's current-exception state; on a violation calls handle_violation (see that row) or trap. | caller-data-read | none | No pointer arithmetic; forwards comment, location, sink and context unchanged. The handler now runs inside the catch block of the predicate's exception (L74-82), so std::current_exception is the predicate's. | changed: P2900 handler-inside-catch |
| 114 | `lorica::contracts::detail::check<Semantic,Predicate>(assertion_kind, Predicate&&, const char*, source_location, violation_sink, const void*)` | include/lorica/contracts.hpp:98 | As evaluate_at_runtime; nothing under ignore. | caller-data-read | none | No pointer access of its own. | unchanged |
| 115 | `lorica::contracts::detail::check_result<Semantic,Value,Predicate>(Value&&, Predicate&&, const char*, source_location)` | include/lorica/contracts.hpp:122 | Reads the caller's value through a reference and calls the caller's predicate. | caller-data-read | none | Returns Value (L122, L128): an lvalue operand stays a reference, an rvalue is moved once into a value, so no reference to a temporary leaves the return statement. | changed: by-value result for rvalues |
| 116 | `lambda in check_result: [&]() -> bool` | include/lorica/contracts.hpp:127 | Reads the enclosing call's value and predicate by reference. | caller-data-read | none | The captures refer to parameters of the enclosing call, which outlive the closure. | unchanged |
| 117 | `lorica::contracts::detail::post_guard<Semantic,Predicate>::post_guard(Predicate, const char*, source_location)` | include/lorica/contracts.hpp:136 | Initialises its own members; reads std::uncaught_exceptions() (per-thread count) except under ignore (L140-141). | object-confined | none | Moves the predicate in; stores comment and location pointers (literals from the macro). | changed: ignore reads nothing |
| 118 | `lorica::contracts::detail::post_guard<Semantic,Predicate>::post_guard(const post_guard&) = delete` | include/lorica/contracts.hpp:145 | None (deleted: no body, cannot be called). | reentrant | none | n/a (no body). | unchanged |
| 119 | `lorica::contracts::detail::post_guard<Semantic,Predicate>::operator=(const post_guard&) = delete` | include/lorica/contracts.hpp:146 | None (deleted: no body, cannot be called). | reentrant | none | n/a (no body). | unchanged |
| 120 | `lorica::contracts::detail::post_guard<Semantic,Predicate>::post_guard(post_guard&&) = delete` | include/lorica/contracts.hpp:147 | None (deleted: no body, cannot be called). | reentrant | none | n/a (no body). | unchanged |
| 121 | `lorica::contracts::detail::post_guard<Semantic,Predicate>::operator=(post_guard&&) = delete` | include/lorica/contracts.hpp:148 | None (deleted: no body, cannot be called). | reentrant | none | n/a (no body). | unchanged |
| 122 | `lorica::contracts::detail::post_guard<Semantic,Predicate>::~post_guard() noexcept(false)` | include/lorica/contracts.hpp:151 | Under ignore nothing (L153). Otherwise reads its own members and std::uncaught_exceptions() (per-thread) and evaluates the predicate, which reads the enclosing function's parameters and locals by reference. | object-confined | none | The predicate's reference captures are valid because the guard is destroyed before the locals declared ahead of it. | changed: ignore evaluates nothing |
| 123 | `lorica::contracts::detail::make_post_guard<Semantic,Predicate>(Predicate&&, const char*, source_location)` | include/lorica/contracts.hpp:171 | None beyond its arguments. | reentrant | none | Forwards the predicate into the guard; no pointer access. | unchanged |
| 124 | `lorica::contracts::test_result::operator bool() const` | include/lorica/contract_overlay.hpp:37 | Reads this->status. | const-read | publication-only | No pointer access. | unchanged |
| 125 | `lorica::contracts::detail::call<Callable,Args...>(Callable&&, Args&&...)` | include/lorica/contract_overlay.hpp:54 | Invokes the caller's callable with the caller's arguments. | caller-data-read | none | Perfect forwarding only; no pointer access of its own. | unchanged |
| 126 | `lorica::contracts::detail::first_failed<Conditions,Values...>(const Conditions&, const Values&...)` | include/lorica/contract_overlay.hpp:77 | Reads the condition tuple and the values by const reference and calls each predicate. | caller-data-read | none | Returns one of the stored message pointers, or null; no dereference. | unchanged |
| 127 | `lambda in first_failed: [&](const auto&... each)` | include/lorica/contract_overlay.hpp:80 | Reads the conditions and values; writes the enclosing call's local 'failed'. | caller-data-read | none | The captures refer to the enclosing call's locals and parameters, which outlive the closure. | unchanged |
| 128 | `lorica::contracts::contract<Semantic,Callable>(Callable&&, source_location)` | include/lorica/contract_overlay.hpp:97 | None beyond its arguments; copies or moves the callable into a new overlay. | reentrant | none | The callable is held by value; a std::ref or a function pointer inside it must outlive the overlay. | unchanged |
| 129 | `lorica::contracts::overlay<...>::pre<Predicate>(Predicate, const char*) &&` | include/lorica/contract_overlay.hpp:112 | Moves from this->callable_, pre_, post_ and delegate_. | object-confined | caller-must-synchronize | Stores the message pointer without copying it; it must outlive the new overlay. | unchanged |
| 130 | `lorica::contracts::overlay<...>::pre<Predicate>(Predicate, const char*) const&` | include/lorica/contract_overlay.hpp:118 | Reads *this (copies it). | const-read | publication-only | As the && form: the message pointer is stored raw. | unchanged |
| 131 | `lorica::contracts::overlay<...>::post<Predicate>(Predicate, const char*) &&` | include/lorica/contract_overlay.hpp:126 | Moves from this->callable_, pre_, post_ and delegate_. | object-confined | caller-must-synchronize | Stores the message pointer without copying it. | unchanged |
| 132 | `lorica::contracts::overlay<...>::post<Predicate>(Predicate, const char*) const&` | include/lorica/contract_overlay.hpp:132 | Reads *this (copies it). | const-read | publication-only | As the && form. | unchanged |
| 133 | `lorica::contracts::overlay<...>::on_violation<Handler>(Handler) &&` | include/lorica/contract_overlay.hpp:140 | Moves from this->callable_, pre_ and post_. | object-confined | caller-must-synchronize | The delegate is held by value in the new overlay. | unchanged |
| 134 | `lorica::contracts::overlay<...>::on_violation<Handler>(Handler) const&` | include/lorica/contract_overlay.hpp:147 | Reads *this (copies it). | const-read | publication-only | As the && form. | unchanged |
| 135 | `lorica::contracts::overlay<...>::operator()<Args...>(Args&&...) const` | include/lorica/contract_overlay.hpp:155 | Reads this->callable_, pre_, post_, delegate_ and location_ (all immutable after construction); calls the callable, the predicates and, on a violation, handle_violation with &delegate_. | const-read | publication-only | No pointer arithmetic. A reference result is passed through (L174-173); under a checking semantic with postconditions the result is held in a local (L170) and returned. | constrained to invocable arguments (SFINAE); no state change |
| 136 | `lorica::contracts::overlay<...>::test<Args...>(Args&&...) const` | include/lorica/contract_overlay.hpp:187 | Reads this->pre_, callable_ and post_; calls the predicates and the callable; no handler, no delegate. | const-read | publication-only | Returns one of the stored message pointers in test_result.condition; no dereference. | constrained to invocable arguments (SFINAE); no state change |
| 137 | `lorica::contracts::overlay<...>::overlay(Callable, Pre, Post, Delegate, source_location) [private]` | include/lorica/contract_overlay.hpp:211 | Initialises its own members. | reentrant | none | Moves its by-value arguments in; no pointer access. | unchanged |
| 138 | `lorica::contracts::overlay<...>::extend<Predicates...,Predicate>(std::tuple<detail::condition<Predicates>...>, Predicate, const char*) [static, private]` | include/lorica/contract_overlay.hpp:217 | None beyond its by-value arguments. | reentrant | none | Stores the message pointer in the new condition without copying it. | unchanged |
| 139 | `lorica::contracts::overlay<...>::rebuild<NewPre,NewPost,NewDelegate>(Callable, NewPre, NewPost, NewDelegate) const [private]` | include/lorica/contract_overlay.hpp:225 | Reads this->location_. | const-read | publication-only | Moves its by-value arguments into a new overlay; no pointer access. | unchanged |
| 140 | `lorica::contracts::overlay<...>::require_callable_conditions<Result,Args...>() [static, private]` | include/lorica/contract_overlay.hpp:234 | None. | reentrant | none | No memory access (static_asserts only). | unchanged |
| 141 | `lorica::contracts::overlay<...>::check<Conditions,Values...>(assertion_kind, const Conditions&, const Values&...) const [private]` | include/lorica/contract_overlay.hpp:243 | Reads the given conditions, this->location_ and takes the address of this->delegate_; each condition goes through detail::check. | const-read | publication-only | Passes &delegate_ as the opaque context together with sink() (L249); the pointer is valid while the overlay object is alive, which the running member call requires anyway. | unchanged |
| 142 | `lambda in overlay::check: [&](const auto&... each)` | include/lorica/contract_overlay.hpp:246 | Reads the conditions, the values and the overlay (this) by reference. | caller-data-read | none | The captures refer to the enclosing call's parameters and to *this, which outlive the closure. | unchanged |
| 143 | `lambda in overlay::check: [&]() -> bool (the predicate handed to detail::check)` | include/lorica/contract_overlay.hpp:248 | Reads one condition and the values by reference and calls the condition's predicate as const. | caller-data-read | none | The captures refer to objects that outlive the detail::check call. | unchanged |
| 144 | `lorica::contracts::overlay<...>::sink() const [private]` | include/lorica/contract_overlay.hpp:255 | None (reads no member). | reentrant | none | Returns nullptr or the function pointer of a captureless lambda (static code). | unchanged |
| 145 | `lambda in overlay::sink: [](const void* context, const contract_violation&)` | include/lorica/contract_overlay.hpp:259 | Reads the delegate object through the context pointer and calls it as const. | caller-data-read | none | static_cast<const Delegate*>(context) (L260) is type-correct only because sink() and &delegate_ of the same overlay type are paired privately at L249; handle_violation cannot check it. | unchanged |
