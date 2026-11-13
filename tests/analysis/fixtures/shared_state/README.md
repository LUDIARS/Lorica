# Shared-state fixtures

One file per decision rule of the concurrency design review (C1 to C16, its
fixtures f01 to f29 in brackets). `tests/analysis/test_shared_state.py` checks every
`// expect:` line exactly:

- `// expect: datum <name> <synchronization>`: every datum of the file has one;
- `// expect: finding <kind> <entry>`: the file's findings are exactly these;
- `// expect: sharing <function> <value>` and `// expect: flag <function> <flag>`.

`tests/analysis/tsan_oracle.py` builds each `// tsan: <race|clean> | <thread 1> | <thread 2>`
line into a two-thread driver (`// setup:` lines run first; `i` is the loop index,
`sink()` consumes a value through a volatile) and requires ThreadSanitizer to agree.
`// tsan: not-observable(<reason>)` lines are listed and not run.
