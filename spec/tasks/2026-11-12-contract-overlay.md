---
task: lorica-contract-overlay
project: Lr
kind: implementation
created: 2026-11-12
memory_links: []
---

# Contract overlay

Human instruction: neco asked that contracts be implementable by overlaying, like
the referenced JavaScript `contract(func)` wrapper, without changing behaviour,
and that the same mechanism serve as a test mechanism (2026-11-12 conversation).
Implement SPEC-LR-CONTRACT-OVERLAY in spec/feature/contracts.md on top of the
existing contracts runtime. Acceptance: conditions attach from outside to an
unedited callable; a call through the overlay is the callable's own while they
hold; violations follow the four evaluation semantics; `ignore` is the plain call
and needs no runtime library; a delegate per overlay; `test` reports without
handling and without making a refused call; usable in constant evaluation;
C++17/20/23 tests, termination tests shared with the in-body form, a runnable demo.
Not included: argument-rewriting fail-safe, invariants, rebinding of function names.
