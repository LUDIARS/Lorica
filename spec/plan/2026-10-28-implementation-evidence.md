# Initial implementation evidence

Observed on Windows, MSVC 19.39.33523.0, x64, Windows SDK 10.0.19041.0:

- CMake configure with LORICA_BUILD_TESTS=ON: exit 0.
- Release build of boundary test executable: exit 0; constexpr static assertions
  compiled. The executable was **not run**.
- CMake installation into a local staging prefix: exit 0.
- Independent examples/consumer find_package against the installed prefix plus
  external LoricaInject.cmake: configure and Release compile/link exit 0.
- `py -3 tools/verify_binary.py build-consumer/Release/lorica_consumer.exe`:
  selected PE ASLR/high-entropy/NX/CFG flags present. This is metadata inspection,
  not execution of the consumer or proof of CFG instrumentation completeness.
- `git diff --check`: no whitespace errors at initial inspection.

Not executed: boundary runtime tests, Python unit tests, fuzzing, sanitizer runs,
Linux compile/runtime/artifact checks, CMake negative cases, production service
integration and performance measurements. Workspace policy requires explicit
test execution authorization. These are review/release gates, not successes.

Dependency and memory-safety inspection: see DEPENDENCIES.md. No third-party
runtime packages, transitive packages or install-time download scripts were added.

Environment issues resolved: `python.exe` WindowsApps alias was inaccessible;
the installed `py -3` launcher works. Exact local repository/worktree paths were
added to Git safe.directory to resolve the sandbox-created ownership mismatch.

## Local PR 3512 classification correction

The first review stopped before LLM review/runtime tests because the initial
repository had no domain definitions. Added responsibility-specific definitions,
program-layer mapping, specification annotations and the exact libFuzzer entry
point declaration. No runtime behavior or dependencies changed.

Anatomia ephemeral `pr-review --base main` after the correction reports:
- target domains present; no unassigned or unclassified changed anchors;
- program/spec dual-layer checks pass;
- no changed orphan functions or source files missing specification links;
- rule_conformance, duplication, spec_linkage and coupling_delta pass;
- convention_drift remains advisory: the libFuzzer-mandated exported symbol uses
  different casing than C++ main/require. Renaming it would break the framework ABI.

This is static analysis, not executed boundary tests, fuzzing or a security
certification. Actio task-links returned no linked task for this session; task
status is therefore unknown, not completed. No unrelated task was substituted.

## Local PR 3512 native preflight configuration

The next review stopped at Praesidium `native.configuration-required` before
registered tests: the initial repository lacked the native analysis manifest.
Added `praesidium.json` enumerating all three C++ translation units with C++17
and the repository-local include directory. The boundary headers are included
by these units. No external include packages, defines, exclusions or gate changes
were introduced; Web contracts are empty because Lorica has no Web runtime.

Ran the Revisor-owned Praesidium CLI as static compiler analysis (no produced
program execution). It returned exit 0, status passed, zero findings, six source
files inspected and three native units passed: consumer, boundary and fuzz entry.
Runtime tests, fuzzing, Linux validation and full security review remain separate
unverified gates. Dependency and memory-lifetime contracts are unchanged.
