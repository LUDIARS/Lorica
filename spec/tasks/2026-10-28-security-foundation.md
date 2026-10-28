---
task: lorica-security-foundation
project: Lr
kind: implementation
created: 2026-10-28
memory_links: []
---

# Lorica security library collection

Human instructions: create externally adoptable C++ memory protection components;
consult Fable and suggest additional defenses; create an independent repository
for security libraries; name it Lorica (2026-10-28 conversation).

Scope: independent repository/registration, initial boundary headers and build
hardening modules, install/export, artifact inspection, documented limits, tests
as review artifacts. No production-service migration, custom allocator, crypto,
authentication, automatic test execution or direct feature-branch publication.

Acceptance:
- LUDIARS/Lorica private repository and Cc Lr registration exist.
- Individually usable C++17 headers cover checked arithmetic, view bounds and budgets.
- CMake supports explicit target protection and external allowlisted injection.
- Unsupported prerequisites fail explicitly and prebuilt/lifetime limits are documented.
- Windows build and installed consumer configure/build complete.
- Runtime tests, fuzzing and Linux checks have distinct execution records; absence
  of execution must not be reported as a pass.
- Submit implementation through the workspace Revisor workflow.
