# Comprehensive review: evidence (2026-11-13)

Executed in an isolated Linux container (Ubuntu 24.04, x86-64, kernel 6.18, glibc 2.39,
GCC 13.3 with ASan/UBSan/TSan, Clang 18.1.3 with libstdc++ 13 and no sanitizer
runtimes, CMake 3.28, Ninja, Python 3.13). Windows code was neither compiled nor run.
Start of the review: 07fdbe2 (the contracts runtime of the unmerged PR #1 merged onto
main, 28 registered tests). Result files of the reviews are working records of this
session and are not committed; ids below refer to them.

## Scope and method

Nine review dimensions, each by one reviewer on a private copy, each finding then
re-verified independently by a second reviewer (falsifier or verifier: confirmed,
partially confirmed with a corrected severity and fix, or refuted) before anything
was changed; only verified findings were applied, in their corrected form:

| Dimension | Review / second review | Findings | Missed by the first reviewer |
| --- | --- | --- | --- |
| C++17 boundary headers | `review-boundary17` / `falsify-boundary17` | 11 | 1 |
| C++20 checked APIs | `review-checked20` / `falsify-checked20` | 18 | 3 |
| Build hardening and packaging (CMake) | `review-cmake` / `verify-cmake` | 16 | 5 |
| Per-function concurrency and memory safety | `review-concurrency-audit` / `falsify-concurrency-audit` | 7 + a 119-row table | 1 |
| Contracts runtime, overlay, semantic switch | `review-contracts` / `falsify-contracts` | 14 | 3 |
| Documentation, registration and waste | `review-docs-waste` / `verify-docs-waste` | 19 | 3 |
| The owner's two premises | `review-premises` / `falsify-premises` | 12 | 3 |
| Write-protected values | `review-protection` / `verify-protection` | 11 | 3 |
| Unsafe API rejection and binary verifier | `review-unsafe-verify` / `falsify-unsafe-verify` | 17 | 3 |

Five adversarial design reviews preceded the two new components, each with a
prototype or measurements and a verdict "sound with changes" (blocking issues and a
cut list each): `design-pack-performance` and `design-pack-security` for sealed
packs; `design-analyze-parsing`, `design-analyze-concurrency` and
`design-analyze-constexpr` for the source analyzer.

## What was added

- Contracts runtime: the `Lorica::contracts` shared library from PR #1 (one handler
  slot for every module of a process), merged at 07fdbe2; then the contract overlay
  (`LORICA_CONTRACT`, conditions laid over an unedited callable, doubling as its test
  oracle, 91ec7fe) and the build-level semantic switch (`lorica_set_contract_semantic`,
  `-DLORICA_CONTRACT_SEMANTIC` through `LoricaInject.cmake`, c3440ba), and the
  `LORICA_BUILD_CONTRACTS` option (6671afc).
- Sealed packs (`pack_builder`, `sealed_pack`): many values, structures and tables in
  one sealed mapping, header-only on the existing protection target with no new OS
  code (8bd9ed8, merged 2a7e70f), cut to that design by the two pack design reviews.
- Source analyzer `tools/lorica_analyze.py` with three subcommands: `complexity`
  (merged 5fb1ad2), `constexpr` (8f6a48f, the only one that starts a compiler) and
  `shared-state` (3f909b3), Python standard library only, failing closed on what it
  cannot parse; self-reports in
  `2026-11-13-constexpr-report.md` and `2026-11-13-shared-state-report.md`.
- This pass: `.github/workflows/ci.yml` (Linux matrix, GCC sanitizers, Windows MSVC)
  in place of the one-off workflow, the sanitizer entry point in
  `spec/test/verification.md`, and the manual parallel-operability and memory-safety
  report (`2026-11-13-parallel-operability-and-memory-safety.md`).

## What was fixed, per dimension

"Apply" is the second reviewer's verdict: in full, in the minimal form it gave, or
not. The commit is where the fixes landed by its message; individual items were not
re-traced in this pass except those of the documentation dimension, which this pass
applied.

| Dimension | Applied | Commit | Not applied, and why |
| --- | --- | --- | --- |
| C++17 boundary | TV-01 (the 11 survivors and a read-before-check mutant killed), BUD-01 (budget not copyable), TV-02; minimal: SEC-01, FUZ-01, PORT-01, TV-03, CON-01, BUD-02; missed LR-VIEW-02 | f692590 | VIEW-01 (an API addition), WASTE-01 (no defect). The fuzz harness is still built only with `-DLORICA_BUILD_FUZZER=ON` |
| C++20 checked APIs | CHK-01, 05, 09, 12, 13, 15; minimal: CHK-02, 03, 04, 06, 07, 11, 14, 16, 17, 18; the three missed findings | f692590 | CHK-08 (an API addition), CHK-10 (a Clang constant-evaluation limit) |
| Build hardening (CMake; the verifier gave no apply field) | UNSAFE-01, TEST-01 to 05, TEST-07, PORT-01 (`LORICA_BUILD_CONTRACTS`), CMAKE-01, PKG-01, DOC-01, DOC-02, WASTE-01 items 1-4; missed findings on `-U_GLIBCXX_ASSERTIONS`, the consumer with an empty build type, `hardening_stops` under ASan | 6671afc, ecb89ae, merged dec6d6b | TEST-06 (CI): this pass. WASTE-02 (probes rerun on every configure by design), PKG-02 (documented: `EXCLUDE_FROM_ALL`); the `-w` and second-module-copy missed findings are documented limits |
| Concurrency and memory safety | CON-01 (one `fprintf` per line); minimal: CON-02, CON-03, CON-05, DOC-01 (spec and header sentences, no new API); missed: per-thread guard test | e65a0fa | MEM-01 and CON-04: already fixed on the head when verified (f692590, 2a7e70f); the refuted row is corrected in the manual report |
| Contracts | CTR-01, CTR-02, CTR-06; minimal: CTR-03, 04, 05, 07, 09, 10, 14; the three missed findings | e65a0fa | CTR-08 (injection precedence kept), CTR-11 (CI; done in this pass), CTR-12 (a Clang C++17 warning), CTR-13 (SHARED-only runtime: owner decision) |
| Documentation, registration and waste | this pass: PRA-01, REG-01, DOC-01, DOC-02, DOC-03 (doc option), WST-01 (and the one-off workflow), WST-02, SAN-01 (corrected fix), CI-01, DOC-05 (this record), missed findings 2 and 3 | this branch | Already fixed on the head: BLD-01, TST-01, DOC-04, DOC-06 (b), DOC-07, TST-02. ABI-01, missed finding 1 (version) and ART-01: owner decisions. REL-01: proposals (fuzz target for the C++20 parsers, CHANGELOG, SECURITY.md, presets) |
| Premises | minimal: CTR-01, CTR-02, CTR-03, CTR-04, TEST-02; HARD-01 and TEST-01 in this pass; missed: README injection build type (this pass) | e65a0fa, 6671afc, this branch | PREM-B-01, PREM-B-02 (reported below), ABI-01 (owner decision), PKG-01 (`LORICA_BUILD_CONTRACTS` exists), CI-01 (owner decision; done in this pass as asked) |
| Write-protected values (no apply field) | SEAL-01 (ENOMEM keeps the page) to SEAL-11; missed: `madvise`/`/proc/self/mem` documented, release order documented, the TSan crash of the proposed test avoided | merged 2a7e70f; `2026-11-13-protection-review-evidence.md` | none |
| Unsafe API and verifier | UA-01, UA-04, UA-05, UA-10; minimal: UA-02, 03, 06, 07, 09, 11, 13, VB-01, VB-02; missed: `SHELL:` de-duplication, a dependency's later `-Wno-deprecated-declarations` | 6671afc, d8326fa, 5d7cd4a | UA-08 (no defect), UA-12 (`stpcpy`/`wcpcpy` not rejected), VB-03 (shared libraries: owner decision), VB-04 (stripped relocations) |

Registered tests: 28 at 07fdbe2, 35 at 54f4e66 (37 with examples), 97 now with
examples (99 in a ThreadSanitizer build with the shared-state oracle).

## Mutation testing

Numbers as the result files and commit messages record them; none was re-run in
this pass.

| Dimension | Before (first reviewer, confirmed by the second) | After |
| --- | --- | --- |
| C++17 boundary | 27 of 38 killed (11 survivors re-applied and confirmed) | f692590: the 11 survivors and a read-before-check mutant killed; no total recorded |
| C++20 checked APIs | 42 of 52 killed (9 non-equivalent survivors confirmed) | not recorded |
| Build hardening (CMake) | 42 of 88 killed | not recorded |
| Contracts | 34 of 56 killed (22 survivors confirmed) | not recorded |
| Write-protected values | 18 of 36 killed (16 survivors confirmed) | `2026-11-13-protection-review-evidence.md`: every earlier survivor killed; removing `handle_segv=0` or the child's own handler is equivalent while the other remains; a consumer test that ignores the exit status is not detected while the consumer succeeds; no total recorded |
| Unsafe API and verifier | 23 of 56 killed (33 survivors) | not recorded |
| Concurrency | 2 survivors in CON-02 (relaxed orders, plain pointer) confirmed; a third (process-wide guard) found by the second reviewer | plain pointer: killed in a TSan build (falsifier); relaxed: equivalent for what the test asserts; guard: killed by the added test (falsifier: 50 of 50) |
| Documentation | none run by the first reviewer; 5 own mutants of the second reviewer all survived (verifier, injection, package, consumer) | the paths are registered as `lorica.verify_binary.*`, `lorica.inject`, `lorica.build_refusals`, `lorica.protection_consumer`; mutants not re-run |
| Premises | none run by the first reviewer; 6 of 7 own mutants of the second reviewer survived | not recorded |

## The owner's two premises

Premise A, "contracts that can be stripped again": now true. Build-level selection
per target (`lorica_set_contract_semantic`) and from outside
(`-DLORICA_CONTRACT_SEMANTIC` with `LoricaInject.cmake`), replacing the project's own
choice; an `ignore` unit references nothing in the runtime library
(`lorica.contracts.ignore` links without it) and an `ignore` overlay is the plain
call. Limits in [contracts.md](../feature/contracts.md): targets sharing inline or
template code with contracts need the same semantic (P2900 mixed mode otherwise); a
target that links `Lorica::contracts` keeps the runtime as a dependency unless the
linker drops unused libraries; `LORICA_POST_RETURN` copies an lvalue and moves an
rvalue once in every semantic; the runtime is a shared library only.

Premise B, "a mechanism that protects from outside the memory a library or
application allocated": does not exist (PREM-B-01, confirmed by the falsifier with
its own 20-probe project). Lorica switches on the toolchain's own run-time checks for
an explicit list of locally compiled targets and keeps private read-only copies of
values, structures and tables; it does not protect, track or check memory that an
application or library allocated. Probes built through `LoricaInject.cmake`,
stopped by an injected check (F FORTIFY, A libstdc++ assertion, S stack protector,
g glibc's own heap check, - not stopped):

| Probe | GCC no Lorica | GCC baseline | GCC extended | GCC extended, library unlisted | GCC Debug extended | Clang no Lorica | Clang baseline | Clang extended | Clang Debug extended |
| --- | --- | --- | --- | --- | --- | --- | --- | --- | --- |
| heap `memcpy` (allocation and copy in one function) | F | F | F | F | - | - | F | F | - |
| heap `memcpy`, block allocated by the library | - | - | - | - | - | - | - | - | - |
| heap `memcpy` done inside the library | - | - | - | - | - | - | - | - | - |
| heap `strcpy` | F | F | F | F | - | - | F | F | - |
| heap loop overflow | - | - | - | - | - | - | - | - | - |
| `vector` index | - | A | A | A | A | - | A | A | A |
| `vector` index inside the library | - | A | A | - | A | - | A | A | A |
| `vector` `data()` / iterator | - | - | - | - | - | - | - | - | - |
| use after free (read, write, dangling vector) | - | - | - | - | - | - | - | - | - |
| double free | g | g | g | g | g | g | g | g | g |
| uninitialized heap | - | - | - | - | - | - | - | - | - |
| uninitialized stack | - | - | - | - | - | - | - | - | - |
| stack `memcpy` | F | F | F | F | S | SEGV | F | F | S |
| stack loop | S | S | S | S | S | SEGV | S | S | S |
| intra-object overflow (`memcpy`, loop) | - | - | - | - | - | - | - | - | - |
| type confusion | - | - | - | - | - | - | - | - | - |

Of 20 probes: GCC no Lorica 4, baseline 6, extended 6, extended with the library
unlisted 5, Debug extended 4; Clang no Lorica 0, baseline 6, extended 6 (the
falsifier: library unlisted 5, Debug extended 4). Ubuntu's GCC already defaults to
FORTIFY 3 and the stack protector, so there the injected baseline adds the two
libstdc++ assertion rows. A GCC ASan+UBSan test build stops 17 of 20; valgrind
flags 11 of the 14 rows EXTENDED misses. Without a build type, the injected build
loses both FORTIFY rows (now stated in the README). EXTENDED zero-fills
uninitialized stack variables, which hides the value but detects nothing.

Possible additions, ranked by measured value over cost (PREM-B-02, proposals only,
none applied; each needs the owner's decision, several a design review):
1. A test-build sanitizer profile (`lorica_sanitize_target`, injection option),
   refused for release installs.
2. A guide to maintained hardened allocators (Scudo, hardened_malloc; PageHeap on
   Windows for tests), after the platform review DEPENDENCIES.md requires.
3. Trap-mode bounds checks in EXTENDED (the falsifier measured one more stopped row
   with GCC and two with Clang, not the four first claimed; cost unmeasured).
4. An allocation annotation (`alloc_size`) for FORTIFY across units (HARD-01 rejected
   the macro; documented as a limit instead).
5. Sealed structures and byte tables: implemented since as sealed packs.
6. `freeze`/`thaw` of application-owned, page-aligned regions: the one form in which
   premise B is attainable (malloc blocks are not eligible); new OS-level
   functionality and a design review.
7. Guard pages around packed values: rejected by the pack design reviews.

## Executed checks (this pass, on the final tree)

Code at 8c11191; the later commits change only `spec/` text. Baseline before this
pass, on dec6d6b with the command below (GCC Release): 96/96 passed.

```sh
cmake -S . -B build-<cell> -G Ninja -DCMAKE_CXX_COMPILER=<g++|clang++> -DCMAKE_BUILD_TYPE=<Release|Debug> \
  -DLORICA_BUILD_TESTS=ON -DLORICA_BUILD_EXAMPLES=ON -DLORICA_TEST_REQUIRE_EXTENDED=ON \
  '-DCMAKE_CXX_FLAGS=-Wall -Wextra -Werror'
cmake --build build-<cell> -j3 && ctest --test-dir build-<cell> --output-on-failure --no-tests=error -j2
```

| Build | Result |
| --- | --- |
| GCC Release | 97/97 passed |
| GCC Debug | 97 tests, 96 passed, `lorica.hardening_stops.fortify` skipped (no FORTIFY in Debug) |
| Clang Release | 97/97 passed |
| Clang Debug | 97 tests, 96 passed, `lorica.hardening_stops.fortify` skipped |
| GCC Release, `-fsanitize=address,undefined -fno-sanitize-recover=all -fno-omit-frame-pointer` (with the flags above, without `LORICA_TEST_REQUIRE_EXTENDED`) | 97 tests, 96 passed, `lorica.hardening_stops.fortify` skipped (ASan stops the copy first); no sanitizer report |
| GCC Release, `-fsanitize=thread`, `-DLORICA_ANALYSIS_TSAN_ORACLE=ON` (same) | 99/99 passed, including `lorica.pack.readers_tsan` and `lorica.analysis.shared_state.tsan` |

The sanitizer builds are exactly the two jobs of `.github/workflows/ci.yml`, run here
without the workflow's `sysctl vm.mmap_rnd_bits=28` (this host's ThreadSanitizer runs
without it); no test needs to be excluded under either.

Install and standalone examples (GCC Release, `-DCMAKE_BUILD_TYPE=Release`, then
`cmake --install <build> --prefix <prefix>`): the prefix holds the 13 headers,
`liblorica_contracts.so.0`, `liblorica_protection.a` and the seven package files.
`examples/consumer` configured through the installed `LoricaInject.cmake` with
`-DLORICA_PROFILE=extended -DLORICA_DEPRECATE_UNSAFE_APIS=ON` built (its command
line carries `-ftrivial-auto-var-init=zero`, `-D_FORTIFY_SOURCE=3` and the unsafe API
header), ran with exit 0 and passed `tools/verify_binary.py`. `examples/contracts`
(2/2), `examples/packing` (1/1) and `tests/contract_modules` (1/1) configured, built
and passed against the same prefix.

Analyzer self-runs:

```console
$ python3 tools/lorica_analyze.py complexity --strict include src tests examples --exclude '*/tests/analysis/fixtures/*'
lorica-analyze complexity: files 41, functions analysed 224, unparsed regions 0, lines not analysed 0
result: pass, findings 0, suppressed 0
$ python3 tools/lorica_analyze.py shared-state --strict include src
lorica-analyze shared-state: files 16, functions analysed 105, data 46, unparsed regions 0, lines not analysed 0
result: pass, findings 0, suppressed 0
$ python3 tools/lorica_analyze.py constexpr include src --compile-commands build-cdb/compile_commands.json \
    --exclude '*_probes/*' --exclude '*/tests/contracts_rejected.cpp' --std 17 --std 20 --std 23 --jobs 2
lorica-analyze constexpr: files 16, functions analysed 31, unparsed regions 0, lines not analysed 0
...
result: pass, findings 0, suppressed 0
```

All three exit 0; the constexpr run (g++ 13.3, a `-DLORICA_BUILD_TESTS=ON
-DCMAKE_EXPORT_COMPILE_COMMANDS=ON` configure, 53 entries; 26/29/32 units at C++17/20/23)
took 26 s and reports nothing witnessed (no witness file given). Without the second
`--exclude` it ends `incomplete` with exit 2: the contracts' must-not-compile probes
do not compile.

Consistency checks: every tracked file under `include/`, `src/`, `tests/`, `tools/`,
`examples/`, `cmake/` and the root `CMakeLists.txt` (216) matches exactly one
`spec/domains` pattern and one `.anatomia/layers.json` layer (a script over
`git ls-files`); the 27 `praesidium.json` units compile as declared with
`g++`/`gcc -fsyntax-only -Wall -Wextra -Werror` and pass the replayed Praesidium
command (`clang++ --analyze ... -Wall -Wextra -Werror`) without a diagnostic, and no
built `.c`/`.cpp` file outside `tests/analysis/fixtures/` is unlisted; the seven C++
blocks of the README compile with `g++` and `clang++` (`-fsyntax-only -Wall -Wextra
-Werror`, at the standard each needs), the schematic ones with declarations for the
names they leave to the reader; test names in the README and specs exist in
`ctest -N` (the two TSan-only ones in a TSan build); `.github/workflows/ci.yml` parses
with PyYAML; `git diff --check` is clean.

Re-run ThreadSanitizer experiments of the manual audit: see
`2026-11-13-parallel-operability-and-memory-safety.md`.

## Not executed

- Anything on Windows/MSVC: the MSVC hardening options, `/we4996` probes, the
  contracts DLL and its deployment, `__fastfail`, the CRT settings, the Windows
  sealed region and packs, the Python analysis tests' paths and line ends there,
  `lorica.contracts.semantic_switch` with a Visual Studio generator (two `/D` for one
  macro under `/WX`). Until `.github/workflows/ci.yml` has run, none of it is
  evidence.
- libc++ (every run used libstdc++ 13); glibc 2.40+ with Clang (only simulated by an
  earlier record); AArch64 (branch protection, the effect of memory orders); 32-bit
  and non-4 KiB page targets; libFuzzer and Clang sanitizers (no compiler-rt on this
  host; the fuzz harness was compiled by hand only in an earlier review).
- The workflow itself (YAML parsed locally with PyYAML; no runner).
- Praesidium and Anatomia CLIs (the Praesidium rule and compiler command were
  replayed by hand over the manifest).
- Performance on a quiet host: `lorica.demo.packing` judges checksums only; no
  number is promised.

## Open owner decisions

- The SHARED-only contracts runtime (static or fully static programs cannot use a
  checking semantic; CTR-13).
- Its SONAME/ABI policy: SONAME 0 and `SameMajorVersion` for every 0.x, and an
  exported signature already changed under it on this branch (ABI-01).
- The package version: still 0.1.0, the same as tag v0.1.0, which has neither
  `Lorica::contracts` nor `Lorica::protection` (missed findings of the docs and
  premises reviews).
- A LICENSE (none is granted without the owner's choice, DEPENDENCIES.md).
- Verifier support for shared libraries and DLLs, so Lorica's own runtime can be
  checked (ART-01, VB-03).
- Whether line atomicity of the default handler becomes a stated guarantee with its
  own test (CON-01).
- The analyzer fixtures under `tests/analysis/fixtures/` keep a repository-scope
  Praesidium run at `native.configuration-required`: an exclusion in Revisor or
  another file extension.
- Premise B: whether to start any of the additions above, in particular
  `freeze`/`thaw` (item 6).
- A warning in `LoricaInject.cmake` for an empty build type with a single-config
  generator (premises review, optional).
