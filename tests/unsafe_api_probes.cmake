# SPEC-LR-VERIFY: lorica_deprecate_unsafe_apis rejects each way of reaching an
# unbounded C copy/format function and accepts bounded code. Each probe is a real
# target with the real function applied; its test builds it through
# run_build_probe.cmake (nothing is run), which requires a failed build with the
# expected diagnostic for a rejected probe. The probes live here, not in a C++
# source, because they are deliberately unsafe. A toolchain the rejection does not
# support registers them disabled, so CTest reports them as not run.

set(_lorica_probe_accepted_bounded [=[
#include <cstdio>
#include <cstring>
#include <lorica/bounded_text.hpp>
int main() {
    char buffer[8];
    std::snprintf(buffer, sizeof buffer, "%d", 1);
    return static_cast<int>(lorica::copy_string(buffer, "ok").value_or(0) + std::strlen(buffer));
}
]=])
set(_lorica_probe_rejected_function_pointer [=[
#include <cstring>
int main() { char* (*copy)(char*, const char*) = &std::strcpy; return copy == nullptr; }
]=])
set(_lorica_probe_rejected_macro_alias [=[
#include <cstdio>
#define FORMAT std::sprintf
int main() { char buffer[8]; return FORMAT(buffer, "%d", 1); }
]=])
set(_lorica_probe_rejected_parenthesized [=[
#include <cwchar>
int main() { wchar_t buffer[8] = L"a"; return (::wcscat)(buffer, L"b") == nullptr; }
]=])
set(_lorica_probe_rejected_definition_alias [=[
#include <cstring>
int main() { char buffer[8] = "a"; return COPY(buffer, "b") == nullptr; }
]=])
set(_lorica_probe_rejected_direct_call [=[
#include <cstring>
int main() { char buffer[8]; return std::strcpy(buffer, "a") == nullptr; }
]=])
set(_lorica_probe_rejected_late_header [=[
int main() { return 0; }
]=])
set(_lorica_probe_rejected_variadic_list [=[
#include <cstdarg>
#include <cstdio>
int format(char* out, const char* text, ...) {
    std::va_list list;
    va_start(list, text);
    const int written = std::vsprintf(out, text, list);
    va_end(list);
    return written;
}
int main() { char buffer[8]; return format(buffer, "%d", 1); }
]=])

function(lorica_add_unsafe_api_probes)
    set(directory "${CMAKE_CURRENT_BINARY_DIR}/unsafe_api_probes")
    set(probes accepted_bounded rejected_direct_call rejected_function_pointer rejected_macro_alias
               rejected_parenthesized rejected_definition_alias rejected_variadic_list rejected_late_header)
    lorica_unsafe_api_rejection_supported(supported)
    if(NOT supported)
        message(STATUS "Lorica: lorica.unsafe_api.* not run: ${supported_REASON}")
    endif()
    # A C library header that comes before the force-included one (here through an
    # earlier -include) must stop compilation, not leave the calls unchecked.
    file(CONFIGURE OUTPUT "${directory}/early_c_header.h" CONTENT "#include <cstring>\n" @ONLY)
    foreach(probe IN LISTS probes)
        set(target "lorica_probe_${probe}")
        set(test "lorica.unsafe_api.${probe}")
        if(NOT supported)
            add_test(NAME "${test}" COMMAND "${CMAKE_COMMAND}" -E false)
            set_tests_properties("${test}" PROPERTIES DISABLED TRUE)
            continue()
        endif()
        file(CONFIGURE OUTPUT "${directory}/${probe}.cpp" CONTENT "${_lorica_probe_${probe}}" @ONLY)
        add_executable("${target}" EXCLUDE_FROM_ALL "${directory}/${probe}.cpp")
        target_link_libraries("${target}" PRIVATE Lorica::boundary)
        target_compile_features("${target}" PRIVATE cxx_std_20)
        if(probe STREQUAL "rejected_late_header" AND NOT MSVC)
            target_compile_options("${target}" PRIVATE "SHELL:-include \"${directory}/early_c_header.h\"")
        endif()
        lorica_deprecate_unsafe_apis("${target}")
        if(probe STREQUAL "rejected_definition_alias")
            target_compile_definitions("${target}" PRIVATE "COPY=std::strcat")
        endif()
        set(expect accept)
        set(diagnostic "")
        if(probe STREQUAL "rejected_late_header")
            set(expect reject)
            set(diagnostic "must come before any C library header")
            if(MSVC)
                set(expect accept)
            endif()
        elseif(probe MATCHES "^rejected_")
            set(expect reject)
            set(diagnostic "is deprecated: Lorica|C4996")
        endif()
        add_test(NAME "${test}" COMMAND "${CMAKE_COMMAND}" "-DBUILD_DIR=${CMAKE_BINARY_DIR}"
            "-DTARGET=${target}" "-DCONFIG=$<CONFIG>" "-DEXPECT=${expect}" "-DDIAGNOSTIC=${diagnostic}"
            -P "${CMAKE_CURRENT_SOURCE_DIR}/tests/run_build_probe.cmake")
        # Builds share the tree, so they run one at a time.
        set_tests_properties("${test}" PROPERTIES RESOURCE_LOCK lorica_build_tree)
    endforeach()
    set(test lorica.unsafe_api.refusals)
    if(supported)
        add_test(NAME "${test}" COMMAND "${CMAKE_COMMAND}"
            "-DLORICA_CMAKE_DIR=${CMAKE_CURRENT_SOURCE_DIR}/cmake" "-DWORK_DIR=${directory}/refusals"
            "-DGENERATOR=${CMAKE_GENERATOR}" "-DCXX_COMPILER=${CMAKE_CXX_COMPILER}"
            -P "${CMAKE_CURRENT_SOURCE_DIR}/tests/unsafe_api_refusals.cmake")
    else()
        add_test(NAME "${test}" COMMAND "${CMAKE_COMMAND}" -E false)
        set_tests_properties("${test}" PROPERTIES DISABLED TRUE)
    endif()
endfunction()
