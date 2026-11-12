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

## Overlay: a contract laid over an existing callable {#SPEC-LR-CONTRACT-OVERLAY}

Human instruction (neco, 2026-11-12): contracts must be implementable by overlaying,
as the referenced JavaScript `contract(func)` wrapper does (preconditions,
postconditions that take the result first, a failure delegate), without changing
behaviour, and must double as a test mechanism.

`<lorica/contract_overlay.hpp>` (C++17, templates over the same runtime) attaches
conditions to a callable from outside. The callable's body is not edited, so the
contract can be added to code one does not own and taken off again:

```cpp
int divide(int dividend, int divisor);                       // unchanged
const auto checked_divide = LORICA_CONTRACT(divide)
    .pre([](int, int divisor) { return divisor != 0; }, "divisor is not zero")
    .post([](int quotient, int dividend, int divisor) {
        return quotient * divisor <= dividend; }, "quotient is rounded down");
checked_divide(6, 3);          // divide(6, 3), with both conditions checked
checked_divide.test(1, 0);     // {precondition_failed, "divisor is not zero"}; no call
```

`LORICA_CONTRACT(callable)` uses the translation unit's evaluation semantic;
`LORICA_CONTRACT_WITH(semantic, callable)` names one. Functions, function objects,
lambdas and pointers to members (object first, as `std::invoke`) are accepted and
held by value. `pre`, `post` and `on_violation` each return a new overlay; an
overlay is immutable, so concurrent calls are as safe as the callable and the
predicates are.

| ID | Guaranteed behaviour |
| --- | --- |
| LR-OVERLAY-01 | While its conditions hold, a call through the overlay has the callable's result type, value category, result and exceptions; arguments are forwarded unchanged and the callable runs once |
| LR-OVERLAY-02 | Each condition is one contract assertion under the overlay's semantic (LR-CONTRACT-01 to 08 apply), reported with its kind, its message as comment, the callable as written, and the file and line where the overlay was started |
| LR-OVERLAY-03 | `ignore`: no condition is evaluated and the call is the callable's own, including its `noexcept` and a result that cannot be moved; the unit references nothing in the runtime library. A condition that cannot take the call's arguments still fails to compile |
| LR-OVERLAY-04 | A postcondition takes the result first (nothing for `void`) and then the arguments, and is checked on normal return only |
| LR-OVERLAY-05 | `on_violation(delegate)` sends that overlay's violations to the delegate in place of the installed handler; `enforce` still terminates when it returns, `quick_enforce` calls neither |
| LR-OVERLAY-06 | `test(arguments...)` evaluates the conditions under every semantic, `ignore` included, reports the first that does not hold (`satisfied`, `precondition_failed`, `postcondition_failed` and its message), calls no handler or delegate, and does not call the callable when a precondition fails |
| LR-OVERLAY-07 | An overlay over a `constexpr` callable is usable in constant evaluation, as is `test`; a violated condition there is ill-formed |

The test mechanism is LR-OVERLAY-06: conditions written once are the callable's
oracle. A test feeds arguments to `test` and compares the outcome, also for calls
the contract refuses, which the product could only observe by terminating. The
same conditions can be laid over a second implementation of the same interface.
`on_violation` is for tests that run the overlay in place inside a larger system.

Deliberate differences from the JavaScript model:

- No argument-rewriting fail-safe. A contract that repairs arguments changes
  behaviour and cannot be stripped; repair or reject input at the boundary
  (`Lorica::boundary`).
- A violation never replaces the result with a null value: the semantic decides
  (terminate, or report and continue), as for the in-body macros. `test` is the
  form that reports without calling.
- Setters return a new overlay instead of mutating, which makes chaining and
  sharing between threads safe.
- No invariants, as in the model and in P2900.

Limits of the overlay:

- It checks calls made through it. C++ cannot rebind a function's name, so a
  direct call to the function is unchecked; hand out the overlay where the
  contract must hold.
- The callable must be callable as `const`; wrap a stateful object in `std::ref`.
- Postconditions see the arguments as the call left them (moved from, or
  written through a reference).
- Under a checking semantic an overlay with postconditions keeps the result in a
  local, so the result type must be movable or copyable. `ignore` has no such need.
- A violation's location is where the overlay was started, not the line of the
  single condition; the message identifies the condition.
- A pointer to member is callable in constant evaluation from C++20 only.

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

`tests/contracts_overlay.cpp` (C++17/20/23, observe) covers LR-OVERLAY-01, 02 and
04 to 07; `tests/contracts_ignore.cpp` covers LR-OVERLAY-03 and 06 under `ignore`;
`tests/contracts_termination.cpp` is built a second time with the contract as an
overlay (`LORICA_TEST_OVERLAY`) and must end exactly as the in-body form does,
plus a delegate that returns under `enforce`. `examples/contracts` is the demo:
one contract over a correct and a defective implementation, run as a test table,
built with `enforce` and with `ignore` (both runs must report every outcome as
expected).

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
