# Runtime contracts (C++26 contract emulation) {#SPEC-LR-CONTRACTS}

Human instruction (neco, 2026-11-10): implement the standard contract model as a
library ahead of compiler support. Contracts are C++26 (P2900, adopted 2025-02),
not C++23; this component tracks P2900 and works from C++17 upward.

Purpose: the Rust analogue of `assert!`/`debug_assert!` + `panic`. A contract states an
invariant of a correct program. A violation is a bug, never expected hostile input:
reject input through ordinary error paths (`Lorica::boundary`, `optional`/`expected`)
and do not encode input validation as a contract, because `ignore` removes it.

## API (`Lorica::contracts`, `<lorica/contracts.hpp>`)

| Macro | P2900 equivalent | Notes |
| --- | --- | --- |
| `LORICA_PRE(pred)` | `pre(pred)` | First statement of the body |
| `LORICA_POST(pred)` | `post(pred)` | Scope guard; checked on normal exit only; not constexpr |
| `return LORICA_POST_RETURN(expr, r, pred);` | `post(r: pred)` | Forwards the value; constexpr |
| `LORICA_CONTRACT_ASSERT(pred)` | `contract_assert(pred)` | |

`<lorica/contract_violation.hpp>` mirrors `<contracts>`: `assertion_kind`,
`evaluation_semantic`, `detection_mode`, non-copyable `contract_violation` (`kind`,
`semantic`, `mode`, `comment` = predicate text, `location`, `evaluation_exception`,
`is_terminating`), `invoke_default_contract_violation_handler`. The replaceable
`::handle_contract_violation` is emulated by `set_violation_handler` (atomic,
returns the previous handler, `nullptr` = default): the one process-wide mutable
value in Lorica, comparable to `std::set_terminate`. Every participating executable and plugin must dynamically
link the same loaded instance of `Lorica::contracts`. That runtime owns both the
atomic handler (exchange with acquire-release, load with acquire) and the
per-thread re-entry guard. Independent runtime copies, static embeddings and
separate loader namespaces have independent state and are outside this guarantee.

Ship the runtime DLL next to the executable on Windows (link the import library);
on Linux deploy the SONAME in the loader search path. Rebuild and relink all
consumers of the former static archive. Use compatible C++ ABIs and standard
libraries; on MSVC use matching configurations and the shared CRT (/MD or /MDd)
across modules, including plugins whose handlers throw. Replacing the handler
does not wait for callbacks in flight. Before unloading a handler's plugin,
quiesce callers, remove its handler, and wait for any outstanding calls.

## Evaluation semantics

Selected per translation unit by `LORICA_CONTRACT_EVALUATION_SEMANTIC`
(`ignore|observe|enforce|quick_enforce`, default `enforce`). An unknown value fails
to compile. Mixed semantics across TUs for inline/template code follow P2900 mixed
mode: which definition the linker keeps is unspecified, so use one per program.

| ID | Guaranteed behaviour |
| --- | --- |
| LR-CONTRACT-01 | `ignore`: predicate compiled but never evaluated, handler never called |
| LR-CONTRACT-02 | `observe`: handler called once per violation; execution continues when it returns |
| LR-CONTRACT-03 | `enforce`: handler called, then `std::abort` (no unwinding, no terminate handler) |
| LR-CONTRACT-04 | `quick_enforce`: no handler, no I/O; `__builtin_trap` / `__fastfail(7)` |
| LR-CONTRACT-05 | A predicate that throws is a violation with `evaluation_exception` and the captured `exception_ptr`; it does not escape |
| LR-CONTRACT-06 | A handler may throw; the exception propagates from the checking site |
| LR-CONTRACT-07 | A violation raised while a handler runs on the same thread aborts without recursion |
| LR-CONTRACT-08 | In constant evaluation a violated contract makes the expression ill-formed |
| LR-CONTRACT-09 | `LORICA_POST` is skipped when the scope exits by exception |
| LR-CONTRACT-10 | `-fno-exceptions` builds compile and enforce; no evaluation-exception path exists |

Constant evaluation uses `std::is_constant_evaluated` (C++20) or the
`__builtin_is_constant_evaluated` builtin (GCC, Clang, MSVC 19.25+) in C++17. Without
either, contracts are runtime-only and a constexpr function containing one cannot be
constant-evaluated.

## Limits (differences from native contracts)

- Statement macros, not declaration syntax: preconditions are not visible to callers
  or tools at the declaration, and virtual-function contracts are not modelled.
- `LORICA_POST` sees parameters and earlier locals by reference; a predicate over a
  parameter that the body modifies sees the modified value (P2900 requires const).
  Multiple `LORICA_POST` in one scope are checked in reverse declaration order.
- `LORICA_POST_RETURN` copies (not moves) an lvalue local; do not use it in a
  function returning a reference to a temporary.
- In a `noexcept` function a throwing observe handler calls `std::terminate`.
- No stack trace: the default handler prints `file:line: function: contract
  violation: <kind> (<semantic>, <mode>): <predicate>` and allocates nothing.
  `std::stacktrace` (C++23) is a follow-up that needs per-toolchain link flags.

## Migration

When toolchains define `__cpp_contracts`, replace the macros with `pre`/`post` on
declarations and `contract_assert`, and the handler with `::handle_contract_violation`.
The enumerators and accessor names are kept identical to make that mechanical.

## Verification

`tests/contracts_observe.cpp` (C++17/20/23), `tests/contracts_ignore.cpp`, and
`tests/contracts_termination.cpp` run in children by `tests/contract_termination.py`
for enforce, quick_enforce and enforce with `-fno-exceptions` (abort with diagnostic,
custom returning handler still aborts, re-entry abort, trap with empty stderr).

`tests/contract_modules` also builds against an installed Lorica package. Two
shared libraries independently set, read and reset the handler and raise observe
violations. With a shared runtime two writers also check atomic exchange ordering
across threads and modules. On Linux the test binds locally defined functions so that symbol
interposition cannot hide a statically embedded copy.

To reproduce the old behaviour, install unmodified PR #1 to a fresh prefix,
then build the new fixture as a standalone consumer:

```sh
cmake -S tests/contract_modules -B probe -DCMAKE_PREFIX_PATH=<absolute-prefix> -DLORICA_TEST_HANDLER_STATE=split
cmake --build probe --config Release
ctest --test-dir probe -C Release -V
```

For a Linux default-binding observation use a fresh build with
`-DLORICA_TEST_BIND_LOCAL=OFF -DLORICA_TEST_HANDLER_STATE=probe`. For a fixed
installation omit both overrides: the default oracle requires shared state.
