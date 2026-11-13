# SPEC-LR-VERIFY: lorica_deprecate_unsafe_apis rejects each way of reaching an
# unbounded C copy/format function and accepts bounded code. Each probe is a real
# target with the real function applied; its test builds it through
# run_build_probe.cmake (nothing is run), which requires a failed build with the
# expected diagnostic for a rejected probe. The probes live here, not in a C++
# source, because they are deliberately unsafe. A toolchain the rejection does not
# support registers them disabled, so CTest reports them as not run. The probes are
# hardened (fortified in optimized configurations) and built with -Wno-error, so only
# Lorica's own promotion can turn the deprecation into an error.

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
set(_lorica_probe_rejected_wide_copy [=[
#include <cwchar>
int main() { wchar_t buffer[8]; return std::wcscpy(buffer, L"a") == nullptr; }
]=])
# Clang reports no deprecation inside a deprecated declaration.
set(_lorica_probe_rejected_deprecated_context [=[
#include <cstring>
[[deprecated]] int legacy(char* b) { return std::strcpy(b, "a") == nullptr; }
int main() { return 0; }
]=])
# The header comes only through a precompiled header of a linked target.
set(_lorica_probe_rejected_inherited_pch [=[
#include "legacy_copy.h"
int main() { char buffer[8]; return legacy_copy(buffer, "a") == nullptr; }
]=])
set(_lorica_probe_rejected_warning_disabled "${_lorica_probe_rejected_direct_call}")
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
               rejected_parenthesized rejected_definition_alias rejected_variadic_list rejected_wide_copy
               rejected_inherited_pch)
    # GCC/Clang only: the C library headers whose guards the header's order check
    # reads, Clang's deprecated context and a later -Wno-deprecated-declarations.
    set(gnu_probes rejected_late_cstring rejected_late_cstdio rejected_late_cwchar
                   rejected_deprecated_context rejected_warning_disabled)
    if(MSVC)
        foreach(probe IN LISTS gnu_probes)
            lorica_add_disabled_test("lorica.unsafe_api.${probe}")
        endforeach()
    else()
        list(APPEND probes ${gnu_probes})
    endif()
    lorica_unsafe_api_rejection_supported(supported)
    if(NOT supported)
        message(STATUS "Lorica: lorica.unsafe_api.* not run: ${supported_REASON}")
        list(APPEND probes refusals harness_reject_built harness_reject_diagnostic)
        foreach(probe IN LISTS probes)
            lorica_add_disabled_test("lorica.unsafe_api.${probe}")
        endforeach()
        return()
    endif()
    file(CONFIGURE OUTPUT "${directory}/legacy_copy.h" CONTENT [=[
#pragma once
#include <cstring>
inline char* legacy_copy(char* out, const char* in) { return std::strcpy(out, in); }
]=] @ONLY)
    add_library(lorica_probe_pch_dependency INTERFACE)
    target_precompile_headers(lorica_probe_pch_dependency INTERFACE "${directory}/legacy_copy.h")
    foreach(probe IN LISTS probes)
        set(target "lorica_probe_${probe}")
        set(test "lorica.unsafe_api.${probe}")
        set(source "${_lorica_probe_${probe}}")
        set(expect reject)
        set(diagnostic "is deprecated: Lorica|C4996")
        if(probe MATCHES "^rejected_late_(.*)$")
            # A C library header that comes before the force-included one (here
            # through an earlier -include) must stop compilation, not leave the calls
            # unchecked.
            file(CONFIGURE OUTPUT "${directory}/early_${CMAKE_MATCH_1}.h" CONTENT "#include <${CMAKE_MATCH_1}>\n" @ONLY)
            set(source "${_lorica_probe_rejected_late_header}")
            set(diagnostic "must come before any C library header")
        elseif(probe STREQUAL "rejected_deprecated_context")
            set(diagnostic "Lorica: unbounded")
        elseif(probe STREQUAL "accepted_bounded")
            set(expect accept)
            set(diagnostic "")
        endif()
        file(CONFIGURE OUTPUT "${directory}/${probe}.cpp" CONTENT "${source}" @ONLY)
        add_executable("${target}" EXCLUDE_FROM_ALL "${directory}/${probe}.cpp")
        target_link_libraries("${target}" PRIVATE Lorica::boundary)
        target_compile_features("${target}" PRIVATE cxx_std_20)
        lorica_harden_target("${target}")
        if(NOT MSVC)
            target_compile_options("${target}" PRIVATE -Wno-error)
        endif()
        if(probe MATCHES "^rejected_late_(.*)$")
            target_compile_options("${target}" PRIVATE "SHELL:-include \"${directory}/early_${CMAKE_MATCH_1}.h\"")
        elseif(probe STREQUAL "rejected_inherited_pch")
            target_include_directories("${target}" PRIVATE "${directory}")
            target_link_libraries("${target}" PRIVATE lorica_probe_pch_dependency)
        endif()
        lorica_deprecate_unsafe_apis("${target}")
        if(probe STREQUAL "rejected_definition_alias")
            target_compile_definitions("${target}" PRIVATE "COPY=std::strcat")
        elseif(probe STREQUAL "rejected_warning_disabled")
            # After Lorica's options, as a linked target's usage requirement would be.
            target_compile_options("${target}" PRIVATE -Wno-deprecated-declarations)
        endif()
        add_test(NAME "${test}" COMMAND "${CMAKE_COMMAND}" "-DBUILD_DIR=${CMAKE_BINARY_DIR}"
            "-DTARGET=${target}" "-DCONFIG=$<CONFIG>" "-DEXPECT=${expect}" "-DDIAGNOSTIC=${diagnostic}"
            -P "${CMAKE_CURRENT_SOURCE_DIR}/tests/run_build_probe.cmake")
        # Builds share the tree, so they run one at a time.
        set_tests_properties("${test}" PROPERTIES RESOURCE_LOCK lorica_build_tree)
    endforeach()
    # Controls: the runner must report a built probe and a missing diagnostic.
    add_test(NAME lorica.unsafe_api.harness_reject_built COMMAND "${CMAKE_COMMAND}"
        "-DBUILD_DIR=${CMAKE_BINARY_DIR}" "-DTARGET=lorica_probe_accepted_bounded" "-DCONFIG=$<CONFIG>"
        "-DEXPECT=reject" "-DDIAGNOSTIC=." -P "${CMAKE_CURRENT_SOURCE_DIR}/tests/run_build_probe.cmake")
    add_test(NAME lorica.unsafe_api.harness_reject_diagnostic COMMAND "${CMAKE_COMMAND}"
        "-DBUILD_DIR=${CMAKE_BINARY_DIR}" "-DTARGET=lorica_probe_rejected_direct_call" "-DCONFIG=$<CONFIG>"
        "-DEXPECT=reject" "-DDIAGNOSTIC=no such diagnostic" -P "${CMAKE_CURRENT_SOURCE_DIR}/tests/run_build_probe.cmake")
    set_tests_properties(lorica.unsafe_api.harness_reject_built PROPERTIES RESOURCE_LOCK lorica_build_tree
        PASS_REGULAR_EXPRESSION "lorica_probe_accepted_bounded was built, but must be rejected")
    set_tests_properties(lorica.unsafe_api.harness_reject_diagnostic PROPERTIES RESOURCE_LOCK lorica_build_tree
        PASS_REGULAR_EXPRESSION "lorica_probe_rejected_direct_call failed without the expected diagnostic")
    lorica_add_build_refusals(lorica.unsafe_api.refusals unsafe_api)
endfunction()
