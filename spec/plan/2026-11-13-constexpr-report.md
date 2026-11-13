# constexpr subcommand on Lorica itself (2026-11-13)

Spec: `spec/feature/source-analysis.md` (`## constexpr`). Host: Ubuntu 24.04 x86-64,
GCC 13.3.0, Clang 18.1.3 with libstdc++ 13, Python 3.13. Nothing in Lorica was changed.

## What was tried

Two compilation databases, configured with `-DCMAKE_EXPORT_COMPILE_COMMANDS=ON
-DLORICA_BUILD_TESTS=ON` for `g++` and for `clang++` (38 entries each). The probe units
(`*_probes/*`: unsafe-API rejections, sealed-type and runtime-format probes) are
designed not to compile and were excluded; the 32 other units were compiled.

```sh
python3 tools/lorica_analyze.py constexpr include src \
    --compile-commands <build>/compile_commands.json --exclude '*_probes/*' \
    --std 17 --std 20 --std 23 --witnesses lorica-witnesses.json --show-hidden --all --jobs 2
```

Units per standard (both compilers): C++17 20 (6 configured for C++20/23 skipped),
C++20 23 (3 skipped), C++23 26. Every unit compiled unchanged under the strict flags
(`-fsyntax-only -pedantic-errors -Werror=invalid-constexpr -H`, Clang also
`-Wno-error=#pragma-messages`); no flag had to be removed; no unit read an original
instead of the copy; exit status 0, no error, no unparsed region; 36 s (g++) and 43 s
(clang++) with 2 jobs.

`lorica-witnesses.json` (scratch file, not committed) held witnesses for the functions
the review found accepted but never constant, taken from the review's
`mut/wit/w_*.cpp`: `trap`, `contract_violated_during_constant_evaluation`,
`sealed_region::data`, the `contract_violation` accessors `kind`, `semantic`, `mode`,
`comment`, `is_terminating`, `sealed_value`'s constructor and `load`, and, inside
`src/contract_violation.cpp`, `handler_scope`'s constructor and `write_text`. Each is a
`static_assert` over a `constexpr` helper that calls the function.

## Locator

42 functions in `include/lorica` and `src` are not declared constexpr (62 are): 31
tried, 11 excluded as "defined in a source file with external linkage: constexpr
implies inline, so the definition would have to move to a header, which changes
linkage and exported symbols": the three `contracts::to_string` overloads,
`set_violation_handler`, `get_violation_handler`,
`invoke_default_contract_violation_handler`, `detail::handle_violation`, and the
`sealed_region` constructor and destructor in `sealed_region_linux.cpp` and
`sealed_region_windows.cpp`. Of the 31 tried, 21 are hidden by default (12 templates or
members of class templates, 9 members of a class without a constexpr constructor).

## Results (R rejected, A accepted only, W witnessed, - not compiled in that configuration)

| Function | Hidden | g++ 17 | g++ 20 | g++ 23 | clang++ 17 | clang++ 20 | clang++ 23 |
| --- | --- | --- | --- | --- | --- | --- | --- |
| `format_into` (`include/lorica/bounded_text.hpp:144`) | template | - | A | A | - | A | A |
| `contract_violation::contract_violation` (`include/lorica/contract_violation.hpp:42`) |  | R | R | R | R | R | R |
| `contract_violation::kind` (`include/lorica/contract_violation.hpp:50`) | non-literal member | A | A | A | A | A | A |
| `contract_violation::semantic` (`include/lorica/contract_violation.hpp:51`) | non-literal member | A | A | A | A | A | A |
| `contract_violation::mode` (`include/lorica/contract_violation.hpp:52`) | non-literal member | A | A | A | A | A | A |
| `contract_violation::comment` (`include/lorica/contract_violation.hpp:54`) | non-literal member | A | A | A | A | A | A |
| `contract_violation::location` (`include/lorica/contract_violation.hpp:55`) | non-literal member | A | A | A | A | A | A |
| `contract_violation::evaluation_exception` (`include/lorica/contract_violation.hpp:57`) | non-literal member | R | R | R | R | R | R |
| `contract_violation::is_terminating` (`include/lorica/contract_violation.hpp:61`) | non-literal member | A | A | A | A | A | A |
| `detail::trap` (`include/lorica/contracts.hpp:50`) |  | A | A | A | R | R | R |
| `detail::contract_violated_during_constant_evaluation` (`include/lorica/contracts.hpp:60`) |  | A | A | A | R | R | R |
| `detail::evaluate_at_runtime` (`include/lorica/contracts.hpp:63`) | template | R | A | A | R | R | A |
| `detail::post_guard::post_guard` (`include/lorica/contracts.hpp:133`) | template | A | A | A | A | A | A |
| `detail::post_guard::~post_guard` (`include/lorica/contracts.hpp:147`) | template | R | A | A | R | R | A |
| `detail::make_post_guard` (`include/lorica/contracts.hpp:164`) | template | A | A | A | A | A | A |
| `detail::sealed_region::data` (`include/lorica/detail/sealed_region.hpp:15`) | non-literal member | A | A | A | A | A | A |
| `pack_builder::pack_builder` (`include/lorica/sealed_pack.hpp:76`) |  | R | R | A | A | A | A |
| `pack_builder::add` (`include/lorica/sealed_pack.hpp:86`) | template | A | A | A | A | A | A |
| `pack_builder::add_array` (`include/lorica/sealed_pack.hpp:94`) | template | A | A | A | A | A | A |
| `pack_builder::used` (`include/lorica/sealed_pack.hpp:102`) | non-literal member | A | A | A | A | A | A |
| `pack_builder::capacity` (`include/lorica/sealed_pack.hpp:103`) | non-literal member | A | A | A | A | A | A |
| `pack_builder::reserve` (`include/lorica/sealed_pack.hpp:107`) | non-literal member | R | R | A | A | A | A |
| `sealed_pack::sealed_pack` (`include/lorica/sealed_pack.hpp:126`) |  | R | R | R | R | R | R |
| `sealed_pack::load` (`include/lorica/sealed_pack.hpp:138`) | template | A | A | A | A | A | A |
| `sealed_pack::at` (`include/lorica/sealed_pack.hpp:141`) | template | A | A | A | A | A | A |
| `sealed_pack::read` (`include/lorica/sealed_pack.hpp:148`) | template | A | A | A | A | A | A |
| `sealed_value::sealed_value` (`include/lorica/sealed_value.hpp:14`) | template | A | A | A | A | A | A |
| `sealed_value::load` (`include/lorica/sealed_value.hpp:19`) | template | A | A | A | A | A | A |
| `(anon)::handler_scope::handler_scope` (`src/contract_violation.cpp:16`) |  | A | A | A | R | R | R |
| `(anon)::handler_scope::~handler_scope` (`src/contract_violation.cpp:17`) |  | R | A | A | R | R | R |
| `(anon)::write_text` (`src/contract_violation.cpp:22`) |  | A | A | A | R | R | R |

Counts per configuration (31 tried):

| | g++ 17 | g++ 20 | g++ 23 | clang++ 17 | clang++ 20 | clang++ 23 |
| --- | --- | --- | --- | --- | --- | --- |
| witnessed | 0 | 0 | 0 | 0 | 0 | 0 |
| accepted (not verified) | 22 | 26 | 28 | 20 | 21 | 23 |
| rejected | 8 | 5 | 3 | 10 | 10 | 8 |
| inactive | 1 | 0 | 0 | 1 | 0 | 0 |

Every supplied witness failed (21 witness compiles on g++, 16 on clang++, the others
not run because the function was rejected there): "non-constant condition for static
assertion", "variable of non-literal type ... only available with -std=c++2b", or a
call to the non-constexpr `contract_violation` / `sealed_region` constructor. `format_into`
is inactive in C++17 because no C++17 unit compiles it.

## Conclusion

Zero actionable candidates in `include/lorica` and `src`, on both compilers and all
three standards: nothing is witnessed, so nothing is called convertible, and
`--emit-patch` writes an empty diff. This agrees with the design review. In detail:

- The three `to_string` overloads are excluded with the ABI reason, not reported as
  candidates (the review showed that moving them into the header removes three
  exported symbols and breaks binaries built against the library).
- Accepted but never constant, as the review found: `sealed_region::data` and the
  `contract_violation` accessors (all six configurations), `trap` and
  `contract_violated_during_constant_evaluation` (GCC only), `handler_scope` and
  `write_text` (GCC only), the templates. Their witnesses fail, so they stay
  `accepted`, never verified.
- Rejected everywhere: the `contract_violation` constructor and
  `evaluation_exception` (`std::exception_ptr` is not a literal type), and the
  `sealed_pack` constructor.
- Not in the review's mutation sets: `pack_builder`'s constructor and `reserve` are
  rejected by GCC in C++17/20 (`unique_ptr` members are not constexpr before C++23)
  and accepted elsewhere; no witness, so accepted only.
- One apparent difference: the review reports its batch m5 (`evaluate_at_runtime`,
  the `post_guard` constructor and destructor, `make_post_guard`, `sealed_value`,
  `format_into`) as rejected in C++17 by both compilers. The batch was judged as a
  whole; this tool attributes each error to its function: in C++17 the rejections
  are `evaluate_at_runtime` (try) and `~post_guard` (constexpr destructor), while
  the `post_guard` constructor, `make_post_guard` and `sealed_value` are accepted on
  their own. Neither the review nor the tool is wrong; the granularity differs. All
  of them are templates, so acceptance means nothing for them anyway.

`contract_violated_during_constant_evaluation` is documented as deliberately not
constexpr but carries no marker, so the tool tries it (accepted on GCC only, witness
fails). Making that decision visible to the tool would take, on its declaration line
in `include/lorica/contracts.hpp`:
`// lorica-analyze: ignore(constexpr) must stay non-constexpr: reaching it during constant evaluation is the diagnostic`.
This file was not changed here.

The review also found that `byte_view::make/size/at/subview` and `input_budget`'s
constructor, `consume`, `permits_depth` and `remaining` are declared constexpr but
have no compile-time witness in `tests/`; the review's `static_assert` block for
`tests/boundary.cpp` closes that gap. It is outside this subcommand (which looks only
at functions not declared constexpr) and was not added.

Not executed: MSVC (no MSVC path exists); `src/sealed_region_windows.cpp` and the
`_MSC_VER` branches (inactive on this host; the Windows file is excluded anyway);
libc++.
