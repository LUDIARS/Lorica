---
task: lorica-source-analysis
project: Lr
kind: implementation
created: 2026-11-12
memory_links: []
---

# Source analysis

Human instruction: neco asked (2026-11-12 conversation) for tools that detect code
complexity; detect, per function, whether it can operate in parallel and whether
memory barriers are needed; and detect places convertible to constexpr. The tools
are used like assertions and leave the analysed code untouched.
Implement SPEC-LR-ANALYZE in spec/feature/source-analysis.md. First part (this
task): the Python standard-library extractor that fails closed to unparsed regions,
and the complexity analysis (cyclomatic, cognitive, nesting, parameters, NLOC) with
thresholds, a baseline, reasoned suppressions, text and JSON reports and exit codes
0/1/2. Acceptance: hermetic `lorica.analysis.*` tests, zero unparsed regions on
Lorica's own sources, a pinned list of Lorica's functions cross-checked against
clang-tidy-18, a documented comparison with clang-tidy on libstdc++, an adoption
example whose README output is tested.
Following parts, built on the extractor by other engineers: shared-state and
synchronization evidence findings; a compiler-driven constexpr try-driver.
Not included: memory-safety indicators, cross-file member resolution, CMake helper
functions, a LoricaInject option, markdown output, MSVC paths.
