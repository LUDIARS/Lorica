---
task: lorica-variable-protection
project: Lr
kind: implementation
created: 2026-10-28
memory_links: []
---

# Immutable variable protection

Human instruction: neco requested more tool proposals and memory/variable protection,
then selected OS write prohibition (2026-10-28 conversation).
Implement the contract in spec/feature/sealed-values.md. Preserve boundary-only use.
Acceptance: dedicated non-executable read-only mappings, immutable scalar API,
explicit OS failures, ownership cleanup, isolated write-fault test, build/install
integration, documented limitations and proposals. No production-service migration,
general allocator, cryptography, runtime test execution by this session or thread
ordering API is included. Submit through Revisor and track the review outcome.
