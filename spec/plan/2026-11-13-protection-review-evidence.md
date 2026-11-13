# Read-only value review fixes: evidence

Executed in an isolated Linux container (Ubuntu 24.04, x86-64, kernel 6.18,
glibc 2.39, GCC 13.3, Clang 18.1.3 with libstdc++ 13, CMake 3.28, Ninja,
Python 3.13, `vm.max_map_count` 65530), on the tree merged with sealed packs.
Windows code was neither compiled nor run.

Executed:
- GCC and Clang, Release and Debug, `-Wall -Wextra -Werror`, tests and examples:
  configure, build and CTest 53/53 passed in each of the four builds.
- GCC Release with `-fsanitize=address,undefined -fno-sanitize-recover=all`, and
  with `-fsanitize=thread`: `ctest -R '^lorica\.(protection|pack|demo\.packing)'`
  15/15 and 16/16 passed, including `lorica.protection_write_denied` and the four
  concurrent readers in `lorica.protection` without a ThreadSanitizer report.
- `LORICA_BUILD_PROTECTION=OFF`: CTest 38/38 passed; the install holds the boundary
  and contracts headers, `liblorica_contracts.so`, the CMake package files and an
  empty `include/lorica/detail`, and no sealed header; the package exports
  `Lorica::boundary` and `Lorica::contracts`.
- Mutation, one mutant at a time, rebuilt and judged by the protection and pack
  tests: every mutant that survived the earlier review (mmap/mprotect permissions
  and flags, failure paths, release, partial seal, error code, type and ownership
  exclusions, a child writing elsewhere, loosened fault harness) is now killed.
  Removing `handle_segv=0` from the fault driver is equivalent while the child
  installs its own handler, and the reverse holds too; both are kept. A consumer
  test that ignores the program's exit status is not detected while the consumer
  succeeds; a failing consumer is caught by the unmodified test.
- Destructor at the mapping limit: 140,000 `sealed_value<int>`, then every other
  one destroyed. Before the fix the process aborted (status 134); after it, all
  70,000 destructions return and the remaining values read back unchanged.
- Observed on a sealed value, as root and as an unprivileged user: `madvise`
  `MADV_DONTNEED` succeeds and the value reads 0 with the page still `r--p`;
  `MADV_FREE` succeeds and the value is unchanged at once; `pwrite` to
  `/proc/self/mem` replaces the value with the page still `r--p`.

Not executed: anything on Windows, Clang sanitizer runtimes (absent on this host),
32-bit or non-4 KiB page targets, a raised or lowered `vm.max_map_count`, and the
deferred discard after `MADV_FREE`.
