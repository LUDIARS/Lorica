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
# shared-state: the concurrency review's decision rules as fixtures, the gate and
# Lorica's own self-report (no compiler needed); the adoption example fails on its
# two findings and passes with its baseline.
add_test(NAME lorica.analysis.shared_state
    COMMAND ${Python3_EXECUTABLE} -B ${CMAKE_CURRENT_SOURCE_DIR}/test_shared_state.py)
set(lorica_shared_state ${Python3_EXECUTABLE} -B ${PROJECT_SOURCE_DIR}/tools/lorica_analyze.py shared-state)
add_test(NAME lorica.analysis.example.shared_state
    COMMAND ${lorica_shared_state} --max-inconsistent-locking 0 --max-unsynchronized 0 ${lorica_example}/shared.cpp)
set_tests_properties(lorica.analysis.example.shared_state PROPERTIES
    PASS_REGULAR_EXPRESSION "FAIL [^\n]*shared.cpp:15 registry::hits_: inconsistent-locking 1 > 0\n")
add_test(NAME lorica.analysis.example.shared_state.baseline
    COMMAND ${lorica_shared_state} --strict --max-inconsistent-locking 0 --max-unsynchronized 0
        --baseline ${lorica_example}/shared-state-baseline.json ${lorica_example}/shared.cpp)
# Opt-in: the same fixtures under ThreadSanitizer, which must agree with each
# `// tsan:` marker; skipped (77) when the compiler cannot run -fsanitize=thread.
option(LORICA_ANALYSIS_TSAN_ORACLE "Check the shared-state fixtures with ThreadSanitizer" OFF)
if(LORICA_ANALYSIS_TSAN_ORACLE)
    add_test(NAME lorica.analysis.shared_state.tsan
        COMMAND ${Python3_EXECUTABLE} -B ${CMAKE_CURRENT_SOURCE_DIR}/tsan_oracle.py
            --compiler ${CMAKE_CXX_COMPILER} --jobs 2)
    set_tests_properties(lorica.analysis.shared_state.tsan PROPERTIES SKIP_RETURN_CODE 77 TIMEOUT 1800)
endif()
