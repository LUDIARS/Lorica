---
task: lorica-extended-hardening-and-checked-apis
project: Lr
kind: implementation
created: 2026-11-10
memory_links: []
---

# Extended hardening profile and checked APIs

Human instructions: strengthen vulnerability defenses for the move to C++, doing
the basic defenses through standard-library override mechanisms where possible
and using C++23/26 and concepts (Revisor Praesidium hardening session); the
product-side parts were kept out of Revisor. Then: "commit the implementation
Lorica needs" (2026-11-10 conversation).

Scope: the standard library hardening and toolchain options the initial profile
listed as unclaimed (opt-in EXTENDED profile), compile-time rejection of the
unbounded C copy/format APIs that Revisor's Praesidium rejects at review time,
and C++20 replacements for them (checked integers, bounded text, byte reading).
No allocator replacement, secure erasure, cryptography or service migration
(AGENTS.md design-review items). Existing C++17 headers and the baseline profile
are unchanged.

Acceptance:
- `lorica_harden_target(<target> EXTENDED)` and `LORICA_PROFILE=extended` apply
  the documented options or fail configuration; nothing is applied twice.
- `lorica_deprecate_unsafe_apis` rejects each indirect use, also in fortified builds.
- Checked API contracts LR-INT/LR-TEXT/LR-READ hold in tests as C++20 and C++23.
- The extended profile's stops are observed from outside the process.
- Checks the toolchain cannot run are reported as not run, never passed.
- Hardened Praesidium (Revisor) passes in repository and changed scope.
- Executed and unexecuted checks are recorded separately.
