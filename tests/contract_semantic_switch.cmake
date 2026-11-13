# SPEC-LR-VERIFY: the evaluation semantic of a target's contracts is chosen from
# the build (LR-CONTRACT-11). One unchanging source holds an in-body contract and
# an overlay and prints how many of their predicates ran: both under a checking
# semantic, none when stripped. Each case configures, builds and runs that project
# for real and is judged by exit status and output. Run with cmake -P:
#   -DLORICA_SOURCE_DIR=<Lorica checkout> -DWORK_DIR=<scratch> -DGENERATOR=<generator>
#   -DCXX_COMPILER=<compiler> [-DCONFIG=<configuration>]
foreach(variable LORICA_SOURCE_DIR WORK_DIR GENERATOR CXX_COMPILER)
    if(NOT ${variable})
        message(FATAL_ERROR "contract_semantic_switch: ${variable} is required")
    endif()
endforeach()
if(NOT CONFIG)
    set(CONFIG Release)
endif()
set(inject "-DCMAKE_PROJECT_TOP_LEVEL_INCLUDES=${LORICA_SOURCE_DIR}/cmake/LoricaInject.cmake"
    -DLORICA_TARGETS=app)

set(cases default by_function injected_over_definition unknown conflict)
# The project says nothing: the header's default, enforce, evaluates both.
set(default_expect "evaluations=2")
# Asking twice for the same semantic is one request.
set(by_function_lines "lorica_set_contract_semantic(app ignore)\nlorica_set_contract_semantic(app ignore)")
set(by_function_expect "evaluations=0")
# Injection replaces what the project itself defines, without a redefinition
# diagnostic (the project builds with warnings as errors).
set(injected_over_definition_lines
    "target_compile_definitions(app PRIVATE LORICA_CONTRACT_EVALUATION_SEMANTIC=enforce)")
set(injected_over_definition_arguments ${inject} -DLORICA_CONTRACT_SEMANTIC=ignore)
set(injected_over_definition_expect "evaluations=0")
set(unknown_arguments ${inject} -DLORICA_CONTRACT_SEMANTIC=strict)
set(unknown_refusal "must be ignore, observe, enforce or quick_enforce")
set(conflict_lines "lorica_set_contract_semantic(app ignore)\nlorica_set_contract_semantic(app observe)")
set(conflict_refusal "already has the contract semantic ignore")

foreach(case IN LISTS cases)
    set(source "${WORK_DIR}/${case}")
    file(REMOVE_RECURSE "${source}")
    file(WRITE "${source}/main.cpp" [=[
#include <lorica/contract_overlay.hpp>
#include <cstdio>
static int evaluations = 0;
static bool counted() { ++evaluations; return true; }
static int in_body(int value) { LORICA_PRE(counted()); return value; }
static int plain(int value) { return value; }
int main() {
    const auto overlaid = LORICA_CONTRACT(plain).pre([](int) { return counted(); }, "counted");
    const int sum = in_body(1) + overlaid(1);
    std::printf("evaluations=%d\n", evaluations);
    return sum == 2 ? 0 : 1;
}
]=])
    file(WRITE "${source}/CMakeLists.txt" "cmake_minimum_required(VERSION 3.24)
project(semantic_switch LANGUAGES CXX)
enable_testing()
add_subdirectory(\"${LORICA_SOURCE_DIR}\" lorica)
add_executable(app main.cpp)
target_link_libraries(app PRIVATE Lorica::contracts)
if(MSVC)
    target_compile_options(app PRIVATE /WX)
else()
    target_compile_options(app PRIVATE -Werror)
endif()
add_test(NAME app COMMAND app)
if(WIN32)
    set_tests_properties(app PROPERTIES ENVIRONMENT_MODIFICATION
        \"PATH=path_list_prepend:$<TARGET_FILE_DIR:Lorica::contracts>\")
endif()
${${case}_lines}
")
    execute_process(COMMAND "${CMAKE_COMMAND}" -S "${source}" -B "${source}/build" -G "${GENERATOR}"
        "-DCMAKE_CXX_COMPILER=${CXX_COMPILER}" "-DCMAKE_BUILD_TYPE=${CONFIG}" ${${case}_arguments}
        RESULT_VARIABLE result OUTPUT_VARIABLE output ERROR_VARIABLE output)
    if(DEFINED ${case}_refusal)
        # CMake wraps long messages; compare without its line breaks.
        string(REGEX REPLACE "[ \t\r\n]+" " " output "${output}")
        if(result EQUAL 0)
            message(FATAL_ERROR "${case} was accepted")
        elseif(NOT output MATCHES "${${case}_refusal}")
            message(FATAL_ERROR "${case} failed without the refusal (${${case}_refusal}):\n${output}")
        endif()
        continue()
    endif()
    if(NOT result EQUAL 0)
        message(FATAL_ERROR "${case} did not configure:\n${output}")
    endif()
    execute_process(COMMAND "${CMAKE_COMMAND}" --build "${source}/build" --config "${CONFIG}"
        RESULT_VARIABLE result OUTPUT_VARIABLE output ERROR_VARIABLE output)
    if(NOT result EQUAL 0)
        message(FATAL_ERROR "${case} did not build:\n${output}")
    endif()
    execute_process(COMMAND "${CMAKE_CTEST_COMMAND}" --test-dir "${source}/build" -C "${CONFIG}" -V
        RESULT_VARIABLE result OUTPUT_VARIABLE output ERROR_VARIABLE output)
    if(NOT result EQUAL 0)
        message(FATAL_ERROR "${case} did not run:\n${output}")
    elseif(NOT output MATCHES "${${case}_expect}")
        message(FATAL_ERROR "${case} ran without ${${case}_expect}:\n${output}")
    endif()
endforeach()
