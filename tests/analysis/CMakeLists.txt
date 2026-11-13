# Source analyser (tools/lorica_analyze.py): Python standard library tests, no
# compiler needed, plus the adoption example and the gate on Lorica itself.
foreach(suite IN ITEMS lexer preprocess extract complexity cli example)
    add_test(NAME lorica.analysis.${suite}
        COMMAND ${Python3_EXECUTABLE} -B ${CMAKE_CURRENT_SOURCE_DIR}/test_${suite}.py)
endforeach()
set(lorica_analyze ${Python3_EXECUTABLE} -B ${PROJECT_SOURCE_DIR}/tools/lorica_analyze.py complexity)
set(lorica_example ${PROJECT_SOURCE_DIR}/examples/analysis)
# parse_flags is over the limit: the plain gate fails, the baselined gate passes.
add_test(NAME lorica.analysis.example.over_threshold
    COMMAND ${lorica_analyze} --max-cognitive 10 ${lorica_example}/sample.cpp)
set_tests_properties(lorica.analysis.example.over_threshold PROPERTIES
    PASS_REGULAR_EXPRESSION "FAIL [^\n]*sample.cpp:11 parse_flags: cognitive 11 > 10\n")
add_test(NAME lorica.analysis.example.baseline
    COMMAND ${lorica_analyze} --strict --max-cognitive 10
        --baseline ${lorica_example}/analysis-baseline.json ${lorica_example}/sample.cpp)
# Every Lorica source is read without an unparsed region.
add_test(NAME lorica.analysis.self
    COMMAND ${lorica_analyze} --strict ${PROJECT_SOURCE_DIR}/include ${PROJECT_SOURCE_DIR}/src
        ${PROJECT_SOURCE_DIR}/tests ${PROJECT_SOURCE_DIR}/examples
        --exclude */tests/analysis/fixtures/*)
