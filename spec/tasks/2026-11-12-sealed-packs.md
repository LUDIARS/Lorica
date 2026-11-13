---
task: lorica-sealed-packs
project: Lr
kind: implementation
created: 2026-11-12
memory_links: []
---

# Sealed packs

Human instruction: neco asked for "a packager that lets memory be handled faster"
right after naming the existing memory protection (2026-11-12 conversation).
Implement SPEC-LR-PACK in spec/feature/sealed-packs.md, reduced by the performance
and security design reviews of 2026-11-12. Acceptance: header-only builder staging
in ordinary memory, sealed once through the unchanged `detail::sealed_region`;
offset slots minted only by the builder; copy-out `load` and bounds-checked `at`
returning empty; an always-compiled read bound that terminates; neither type
copyable nor movable; refusals as values; unit, compile-time, child fault and
ThreadSanitizer reader tests; a runnable demo that judges checksums only; the
threat-model, cost and `vm.max_map_count` limits written into sealed-values.md.
Not included: new OS code, guard pages, madvise/mlock, references or views into
the mapping, slot identity tags, allocator or pmr interfaces, budgeted_resource.
