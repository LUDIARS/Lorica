# Complexity gate on an unchanged source

`sample.cpp` stands for a consumer's code. `parse_flags` is deliberately over the
limit. The analyser reads the file as text: nothing is compiled, executed or
edited. The commands run from this directory; the blocks below are checked
against the real output by `tests/analysis/test_example.py`.

A threshold run fails (exit status 1) and names the lines that contributed:

```console
$ python3 ../../tools/lorica_analyze.py complexity sample.cpp --max-cognitive 10
lorica-analyze complexity: files 1, functions analysed 3, unparsed regions 0, lines not analysed 0
FAIL sample.cpp:11 parse_flags: cognitive 11 > 10
    line 13: +1 for
    line 14: +2 if (nesting 1)
    line 15: +3 if (nesting 2)
    line 15: +1 &&
    line 18: +1 else if
    line 18: +1 ||
    line 20: +1 else if
    line 22: +1 else
result: fail, findings 1, suppressed 0
$ echo $?
1
```

Adopting the gate on existing code: record a baseline once, commit it, and the
same limit passes until a function gets worse or a new function exceeds it:

```console
$ python3 ../../tools/lorica_analyze.py complexity sample.cpp --write-baseline analysis-baseline.json
lorica-analyze complexity: files 1, functions analysed 3, unparsed regions 0, lines not analysed 0
result: pass, findings 0, suppressed 0
$ python3 ../../tools/lorica_analyze.py complexity sample.cpp --max-cognitive 10 --baseline analysis-baseline.json
lorica-analyze complexity: files 1, functions analysed 3, unparsed regions 0, lines not analysed 0
result: pass, findings 0, suppressed 0
$ echo $?
0
```

Every metric of every function, with `--all` (`--json` for a machine-readable report):

```console
$ python3 ../../tools/lorica_analyze.py complexity sample.cpp --all
lorica-analyze complexity: files 1, functions analysed 3, unparsed regions 0, lines not analysed 0
cyclomatic  cognitive  nesting  parameters  nloc  function
         3          2        1           1     4  sample.cpp:6 clamp_percent
         8         11        3           1    17  sample.cpp:11 parse_flags
         2          1        1           1     5  sample.cpp:29 checksum
result: pass, findings 0, suppressed 0
```

In a CMake project the gate is an ordinary test. Lorica's own build runs this
example twice, as `lorica.analysis.example.over_threshold` (expected to fail) and
`lorica.analysis.example.baseline` (`tests/analysis/CMakeLists.txt`). A consumer:

```cmake
add_test(NAME myapp.complexity COMMAND ${Python3_EXECUTABLE}
    ${LORICA_SOURCE_DIR}/tools/lorica_analyze.py complexity --strict
    --max-cognitive 15 --max-cyclomatic 10
    --baseline ${CMAKE_CURRENT_SOURCE_DIR}/analysis-baseline.json
    ${CMAKE_CURRENT_SOURCE_DIR}/src)
```

A single function can be exempted, with a reason, on its declaration line:
`int legacy(int x) { // lorica-analyze: ignore(cognitive) generated table, reviewed`.
