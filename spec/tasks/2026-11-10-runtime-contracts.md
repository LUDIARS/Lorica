---
task: lorica-runtime-contracts
project: Lr
kind: implementation
created: 2026-11-10
memory_links: []
---

# Runtime contracts

Human instruction: neco asked to implement the C++ standard contract model as a
library ahead of compiler support (stated as C++23; the feature is C++26 / P2900).
Implement spec/feature/contracts.md. Acceptance: four evaluation semantics, handler
replacement, evaluation-exception detection, re-entry abort, constexpr behaviour,
`-fno-exceptions` build, C++17/20/23 tests, isolated termination tests.
Executed in the session container (Linux GCC 13, Clang 18, GCC ASan/UBSan): all
contract tests passed. Not executed: Windows MSVC (fastfail path, /W4). This
predates the shared runtime; the record for the merged tree is
spec/plan/2026-11-13-comprehensive-review-evidence.md.
