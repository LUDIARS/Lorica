# Shared-state report on Lorica itself (2026-11-13)

Spec: SPEC-LR-ANALYZE, section "Shared state and synchronization"
(`spec/feature/source-analysis.md`). Task: `spec/tasks/2026-11-12-source-analysis.md`.
Lexical, per analysed file set: not a proof of the absence of data races.

## The owner's question

"Can each function run in parallel, and does it need a memory barrier?" For Lorica:
the only process-wide mutable object is `installed_handler`, a `std::atomic` used with
`exchange(acq_rel)` and `load(acquire)`; the only other non-member variable is the
`thread_local` re-entry guard `handling_violation`. Neither needs a barrier: a fence
(`std::atomic_thread_fence`) never repairs a data race on a non-atomic object, it
orders nothing without an atomic object, and the atomic already gives the
release/acquire pairing that publishes the handler. Every other datum is a member of
an object the caller owns: those classes are caller-synchronized (concurrent reads of
one object are fine, a concurrent write needs the caller's lock), as the standard
library's own types are. The one place threads can visibly interfere is the default
violation handler's output, one message built from thirteen stdio calls on `stderr`
(eleven `fputs` through `write_text`, one `fprintf`, one `fflush`):
data-race-free, but lines from two threads can interleave. The memory-safety half of
the question is answered by the separate manual audit, not here.

## Commands

```sh
python3 tools/lorica_analyze.py shared-state include src --strict
python3 tools/lorica_analyze.py shared-state include src --strict --all    # the table below
python3 tools/lorica_analyze.py shared-state include src --strict --json   # every access
```

```console
$ python3 tools/lorica_analyze.py shared-state include src --strict
lorica-analyze shared-state: files 16, functions analysed 104, data 46, unparsed regions 0, lines not analysed 0
result: pass, findings 0, suppressed 0
```

Exit status 0 with no limit; with every finding limited
(`--max-<finding> 0` for all eleven kinds except `unknown`) also 0. With
`--max-unknown 0` it fails on the 13 functions listed below, by design.

## Findings

None. No `inconsistent-locking`, `unsynchronized`, `write-under-shared-lock`,
`reference-escapes-lock`, `const-writes-mutable`, `lock-not-held`,
`relaxed-publication`, `invalid-order`, `fence-without-atomic` or `mt-unsafe-call`.
Lorica holds no mutex, so the lock rules have nothing to check here.

## Data (46 rows)

Each access as `line kind lockset function`; `{}` is the empty lockset. Accesses in
constructors and destructors of the datum's class are exempt (summarised). Line
numbers are in the declaring file unless a file is named.

| Datum | Declared | Kind | synchronization | Accesses (line, kind, lockset, function) |
| --- | --- | --- | --- | --- |
| `byte_reader::bytes_` | byte_reader.hpp:88 | member `std::span<const std::byte>` | caller-must-synchronize | 34 read {} size; 36 read {} remaining; 41 call {} take |
| `byte_reader::offset_` | byte_reader.hpp:89 | member `std::size_t` | caller-must-synchronize | 35 read {} offset; 36 read {} remaining; 41 call {} take; 42 rmw {} take; 79 read {} read_prefixed; 83 write {} read_prefixed |
| `byte_view::data_` | byte_view.hpp:33 | member `const std::byte*` | not-needed (read-only in the analysed set) | 21 read {} at; 27 read {} subview |
| `byte_view::size_` | byte_view.hpp:34 | member `std::size_t` | not-needed (read-only in the analysed set) | 18 read {} size; 20 read {} at; 25 read {} subview |
| `contracts::test_result::status` | contract_overlay.hpp:34 | member `test_status` | not-needed (read-only in the analysed set) | 38 read {} operator bool |
| `contracts::test_result::condition` | contract_overlay.hpp:36 | member `const char*` | not-needed (not accessed in the analysed set) | none |
| `contracts::detail::condition::predicate` | contract_overlay.hpp:45 | member `Predicate` | not-needed (not accessed in the analysed set) | none |
| `contracts::detail::condition::message` | contract_overlay.hpp:46 | member `const char*` | not-needed (not accessed in the analysed set) | none |
| `contracts::overlay::callable_` | contract_overlay.hpp:262 | member `Callable` | caller-must-synchronize | 112 call {} pre; 126 call {} post; 142 call {} on_violation; 159 read {} operator(); 163 read {} operator(); 165 read {} operator(); 168 read {} operator(); 192 read {} test; 195 read {} test |
| `contracts::overlay::pre_` | contract_overlay.hpp:263 | member `Pre` | caller-must-synchronize | 113 call {} pre; 126 call {} post; 142 call {} on_violation; 161 read {} operator(); 187 read {} test |
| `contracts::overlay::post_` | contract_overlay.hpp:264 | member `Post` | caller-must-synchronize | 113 call {} pre; 127 call {} post; 142 call {} on_violation; 166 read {} operator(); 169 read {} operator(); 193 read {} test; 196 read {} test |
| `contracts::overlay::delegate_` | contract_overlay.hpp:265 | member `Delegate` | caller-must-synchronize | 114 call {} pre; 128 call {} post; 246 read {} check |
| `contracts::overlay::location_` | contract_overlay.hpp:266 | member `source_location` | not-needed (read-only in the analysed set) | 225 read {} rebuild; 246 read {} check |
| `contracts::source_location::file` | contract_violation.hpp:30 | member `const char*` | not-needed (read-only in the analysed set) | 34 read {} file_name |
| `contracts::source_location::function` | contract_violation.hpp:31 | member `const char*` | not-needed (read-only in the analysed set) | 35 read {} function_name |
| `contracts::source_location::line_number` | contract_violation.hpp:32 | member `std::uint_least32_t` | not-needed (read-only in the analysed set) | 36 read {} line |
| `contracts::contract_violation::kind_` | contract_violation.hpp:67 | member `assertion_kind` | not-needed (read-only in the analysed set) | 50 read {} kind |
| `contracts::contract_violation::semantic_` | contract_violation.hpp:68 | member `evaluation_semantic` | not-needed (read-only in the analysed set) | 51 read {} semantic; 62 read {} is_terminating; 63 read {} is_terminating |
| `contracts::contract_violation::mode_` | contract_violation.hpp:69 | member `detection_mode` | not-needed (read-only in the analysed set) | 52 read {} mode |
| `contracts::contract_violation::comment_` | contract_violation.hpp:70 | member `const char*` | not-needed (read-only in the analysed set) | 54 read {} comment |
| `contracts::contract_violation::location_` | contract_violation.hpp:71 | member `source_location` | not-needed (read-only in the analysed set) | 55 read {} location |
| `contracts::contract_violation::evaluation_exception_` | contract_violation.hpp:72 | member `std::exception_ptr` | not-needed (read-only in the analysed set) | 58 read {} evaluation_exception |
| `contracts::detail::post_guard::predicate_` | contracts.hpp:155 | member `Predicate` | not-needed (only in initialisation or destruction) | 1 in ~post_guard (exempt) |
| `contracts::detail::post_guard::comment_` | contracts.hpp:156 | member `const char*` | not-needed (only in initialisation or destruction) | 1 in ~post_guard (exempt) |
| `contracts::detail::post_guard::location_` | contracts.hpp:157 | member `source_location` | not-needed (only in initialisation or destruction) | 1 in ~post_guard (exempt) |
| `contracts::detail::post_guard::exceptions_on_entry_` | contracts.hpp:159 | member `int` | not-needed (only in initialisation or destruction) | 1 in ~post_guard (exempt) |
| `detail::sealed_region::data_` | detail/sealed_region.hpp:17 | member `void*` | not-needed (read-only in the analysed set) | 15 read {} data; 17 in sealed_region, ~sealed_region of sealed_region_linux.cpp, sealed_region_windows.cpp (exempt) |
| `detail::sealed_region::size_` | detail/sealed_region.hpp:18 | member `std::size_t` | not-needed (only in initialisation or destruction) | 8 in sealed_region, ~sealed_region of sealed_region_linux.cpp, sealed_region_windows.cpp (exempt) |
| `budget_limits::bytes` | input_budget.hpp:7 | member `std::size_t` | not-needed (not accessed in the analysed set) | none |
| `budget_limits::elements` | input_budget.hpp:8 | member `std::size_t` | not-needed (not accessed in the analysed set) | none |
| `budget_limits::allocations` | input_budget.hpp:9 | member `std::size_t` | not-needed (not accessed in the analysed set) | none |
| `budget_limits::depth` | input_budget.hpp:10 | member `std::size_t` | not-needed (not accessed in the analysed set) | none |
| `input_budget::remaining_` | input_budget.hpp:42 | member `budget_limits` | caller-must-synchronize | 24 read {} consume; 25 read {} consume; 26 rmw {} consume; 27 rmw {} consume; 28 rmw {} consume; 37 read {} permits_depth; 39 read {} remaining |
| `detail::pack_place::offset` | sealed_pack.hpp:25 | member `std::size_t` | not-needed (not accessed in the analysed set) | none |
| `detail::pack_place::end` | sealed_pack.hpp:26 | member `std::size_t` | not-needed (not accessed in the analysed set) | none |
| `pack_slot::offset_` | sealed_pack.hpp:55 | member `std::size_t` | not-needed (not accessed in the analysed set) | none |
| `pack_array_slot::offset_` | sealed_pack.hpp:67 | member `std::size_t` | not-needed (not accessed in the analysed set) | none |
| `pack_array_slot::count_` | sealed_pack.hpp:68 | member `std::size_t` | not-needed (read-only in the analysed set) | 62 read {} size |
| `pack_builder::staging_` | sealed_pack.hpp:113 | member `std::unique_ptr<unsigned char[]>` | not-needed (read-only in the analysed set) | 90 read {} add; 99 read {} add_array; 108 read {} reserve; 1 in pack_builder (exempt) |
| `pack_builder::capacity_` | sealed_pack.hpp:114 | member `std::size_t` | caller-must-synchronize | 103 read {} capacity; 109 call {} reserve |
| `pack_builder::used_` | sealed_pack.hpp:115 | member `std::size_t` | caller-must-synchronize | 102 read {} used; 109 call {} reserve; 110 write {} reserve |
| `sealed_pack::region_` | sealed_pack.hpp:155 | member `detail::sealed_region` | not-needed (read-only in the analysed set) | 152 read {} read |
| `sealed_pack::used_` | sealed_pack.hpp:156 | member `std::size_t` | not-needed (read-only in the analysed set) | 150 read {} read |
| `sealed_value::storage_` | sealed_value.hpp:25 | member `detail::sealed_region` | not-needed (read-only in the analysed set) | 21 read {} load |
| `contracts::(anonymous namespace)::installed_handler` | src/contract_violation.cpp:9 | global `std::atomic<violation_handler>` | atomic:acq_rel,acquire | 29 atomic {} set_violation_handler; 34 atomic {} get_violation_handler |
| `contracts::(anonymous namespace)::handling_violation` | src/contract_violation.cpp:12 | global `bool` | not-needed (thread_local) | 16 write {} handler_scope; 17 write {} ~handler_scope; 92 read {} handle_violation |

Counts: `not-needed` 36 (19 read-only in the set, 11 not accessed, 5 only in
initialisation or destruction, 1 thread_local), `caller-must-synchronize` 9,
`atomic:acq_rel,acquire` 1; `lock:`, `inconsistent`, `missing`, `unknown`: 0.

## Functions by `sharing` (104)

| sharing | Functions |
| --- | --- |
| no-shared-state | 36 |
| caller-synchronized:read | 30 |
| caller-synchronized:write | 23 |
| self-synchronized(unverified) | 2: `set_violation_handler`, `get_violation_handler` |
| unknown | 13 (below) |
| thread-hostile | 0 |

Flags: `shared-stream` on `invoke_default_contract_violation_handler`;
`process-global-effect` on the four `sealed_region` constructors and destructors
(Linux and Windows: `mmap`/`mprotect`/`munmap`, `VirtualAlloc`/`VirtualProtect`/`VirtualFree`).

`unknown`, each checked against the code:

| Function | Why unknown | Correct? |
| --- | --- | --- |
| `contracts::detail::call` (contract_overlay.hpp:54) | calls the user callable through `std::invoke` and `static_cast<Callable&&>(callable)(...)` | yes: user code |
| `detail::first_failed` (:77), `overlay::check` (:240) | `std::apply` over the user predicates | yes |
| `overlay::operator()` (:153), `overlay::test` (:184) | through `call`, `check`, `first_failed` | yes |
| `detail::evaluate_at_runtime`, `detail::check`, `detail::check_result` (contracts.hpp:63, 96, 119) | call the predicate parameter; `check` also the macro `LORICA_DETAIL_IS_CONSTANT_EVALUATED` | yes |
| `post_guard::~post_guard` (contracts.hpp:147) | through `detail::check` | yes |
| `detail::trap` (contracts.hpp:50), `contract_violated_during_constant_evaluation` (:60) | `__fastfail` in the MSVC branch, kept because both branches are bracket-neutral | conservative: the intrinsic terminates the process and touches nothing shared |
| `detail::handle_violation` (contract_violation.cpp:87) | calls the `sink` parameter and the installed `handler` | yes: user code runs here |
| `sealed_region::sealed_region` (sealed_region_windows.cpp:13) | `GetLastError` is not in the analysed set | conservative: it reads a per-thread value |

## Analysis

Checked line by line against `include/` and `src/`; three tool defects found during
this check were corrected in the tool, not in the table: an access in another file
now names its file (the `sealed_region` constructors live in two `.cpp` files); a
pointer member returned by value (`source_location::file_name`,
`contract_violation::comment`, `sealed_region::data`) is a read, not an escape; and a
callable invoked through a cast or `std::invoke`/`std::apply` makes the function
unknown instead of caller-synchronized.

- The review predicted "two data items and one stream". The tool agrees: the only
  non-member rows are `installed_handler` and `handling_violation`, and the only
  `shared-stream` function is `invoke_default_contract_violation_handler`
  (`handle_violation` writes one line and then calls that handler; two separate
  messages are not flagged). The table is longer because the orchestrator asked for
  every datum: the other 44 rows are members, all of objects the caller owns.
- `installed_handler`: `exchange(acq_rel)` in `set_violation_handler`, `load(acquire)`
  in `get_violation_handler`, no other access. The atomic does not guard other data
  (no function writes shared data before storing it or tests it before accessing
  shared data), so no order would be a finding; these orders are nevertheless the
  ones needed to publish whatever the handler pointer refers to.
- `handling_violation`: written by `handler_scope`'s constructor and destructor and
  read in `handle_violation`, all on the calling thread; its address never escapes.
- Members marked `caller-must-synchronize` (`byte_reader`, `input_budget`,
  `pack_builder`, `overlay`'s parts) are written by non-const members. That matches
  their documented contract (`input_budget.hpp` says so in one line; `byte_reader`
  and `pack_builder` are single-owner cursors and builders).
- Members marked `not-needed (read-only in the analysed set)` are written only in
  constructors; the implicitly declared copy/move assignments that could also write
  them are invisible to a lexical tool (most are deleted: `sealed_value`,
  `sealed_pack`, `input_budget`, `post_guard`). Their readers are still
  `caller-synchronized:read`, not `no-shared-state`: the object is the caller's.
- `budget_limits::*`, `pack_place::*`, `pack_slot::offset_`,
  `pack_array_slot::offset_`, `test_result::condition`, `condition::*` show "not
  accessed": they are read through another object (`remaining_.bytes`,
  `slot.offset_`, `place->end`, `each.predicate`), which the tool attributes to the
  enclosing datum (`remaining_`) or, for a parameter or local, to nothing. This is
  the documented aliasing limit, harmless here because those objects are values
  passed by copy.
- `pack_builder::staging_` is `read-only` although `add` writes the staging bytes:
  the bytes are the pointee of a `unique_ptr`, a separate object the tool does not
  follow. `pack_builder` is caller-synchronized either way.
- Nothing in Lorica takes a lock, so `lock:`, `inconsistent` and the guard rules are
  exercised only by the fixtures (`tests/analysis/fixtures/shared_state/`).

Not executed: the analyser over a Windows build configuration (only the textual
union of `#if` branches is read), and any runtime check of Lorica itself under
ThreadSanitizer (the design review's ad-hoc run reported 0 races; a registered test
remains open in `spec/test/verification.md`).
