# SPEC-LR-VERIFY: lorica_deprecate_unsafe_apis refuses targets it cannot check:
# precompiled headers (compiled as system headers, where deprecations are not
# reported) and C sources (which do not get the C++ header), also when they are
# added after the call. Each case configures a small project and must fail with
# the refusal; the control must configure. Run with cmake -P:
#   -DLORICA_CMAKE_DIR=<cmake dir> -DWORK_DIR=<scratch> -DGENERATOR=<generator>
#   -DCXX_COMPILER=<compiler>
foreach(variable LORICA_CMAKE_DIR WORK_DIR GENERATOR CXX_COMPILER)
    if(NOT ${variable})
        message(FATAL_ERROR "unsafe_api_refusals: ${variable} is required")
    endif()
endforeach()
set(cases control precompiled_header c_source)
set(control_lines "")
set(precompiled_header_lines "target_precompile_headers(app PRIVATE <cstring>)")
set(c_source_lines "target_sources(app PRIVATE legacy.c)")
set(control_expect "")
set(precompiled_header_expect "uses precompiled headers")
set(c_source_expect "has C source")
foreach(case IN LISTS cases)
    set(source "${WORK_DIR}/${case}")
    file(REMOVE_RECURSE "${source}")
    file(WRITE "${source}/main.cpp" "int main() { return 0; }\n")
    file(WRITE "${source}/legacy.c" "int legacy(void) { return 0; }\n")
    file(WRITE "${source}/CMakeLists.txt" "cmake_minimum_required(VERSION 3.24)
project(refusal LANGUAGES C CXX)
include(\"${LORICA_CMAKE_DIR}/LoricaHardening.cmake\")
add_executable(app main.cpp)
lorica_deprecate_unsafe_apis(app)
${${case}_lines}
")
    execute_process(COMMAND "${CMAKE_COMMAND}" -S "${source}" -B "${source}/build" -G "${GENERATOR}"
        "-DCMAKE_CXX_COMPILER=${CXX_COMPILER}"
        RESULT_VARIABLE result OUTPUT_VARIABLE output ERROR_VARIABLE output)
    if(case STREQUAL "control")
        if(NOT result EQUAL 0)
            message(FATAL_ERROR "the control project did not configure:\n${output}")
        endif()
    elseif(result EQUAL 0)
        message(FATAL_ERROR "${case} was accepted")
    elseif(NOT output MATCHES "${${case}_expect}")
        message(FATAL_ERROR "${case} failed without the refusal (${${case}_expect}):\n${output}")
    endif()
endforeach()
