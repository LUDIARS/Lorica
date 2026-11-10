include_guard(GLOBAL)

# The header lorica_deprecate_unsafe_apis force-includes, kept as a global property
# so functions called from any directory read the same path: the installed
# package's include directory when LoricaConfig.cmake gives it (it also sets the
# property itself, in case this file was read first through LoricaInject.cmake),
# else this source tree's or an installed prefix's next to this file.
set(_lorica_candidates
    "${CMAKE_CURRENT_LIST_DIR}/../include"
    "${CMAKE_CURRENT_LIST_DIR}/../../../include"
    "${CMAKE_CURRENT_LIST_DIR}/../../../../include")
if(LORICA_INCLUDE_DIR)
    list(PREPEND _lorica_candidates "${LORICA_INCLUDE_DIR}")
endif()
foreach(_lorica_candidate IN LISTS _lorica_candidates)
    set(_lorica_candidate "${_lorica_candidate}/lorica/unsafe_api.hpp")
    cmake_path(NORMAL_PATH _lorica_candidate)
    if(EXISTS "${_lorica_candidate}")
        set_property(GLOBAL PROPERTY LORICA_UNSAFE_API_HEADER "${_lorica_candidate}")
        break()
    endif()
endforeach()
unset(_lorica_candidate)
unset(_lorica_candidates)

# Only concrete, locally compiled targets: imported dependencies must be rebuilt
# and audited separately; a usage requirement cannot retrofit their code.
function(_lorica_require_compiled_target target)
    if(NOT TARGET "${target}")
        message(FATAL_ERROR "Lorica: missing target ${target}")
    endif()
    get_target_property(imported "${target}" IMPORTED)
    get_target_property(alias "${target}" ALIASED_TARGET)
    get_target_property(kind "${target}" TYPE)
    if(imported OR alias OR NOT kind MATCHES "^(EXECUTABLE|STATIC_LIBRARY|SHARED_LIBRARY|MODULE_LIBRARY|OBJECT_LIBRARY)$")
        message(FATAL_ERROR "Lorica: ${target} must be a concrete locally compiled target")
    endif()
endfunction()

# Baseline profile (LR-BUILD-01): stack protection, ASLR/PIE, NX and full RELRO
# or Control Flow Guard.
function(_lorica_apply_baseline target kind)
    if(MSVC AND WIN32)
        target_compile_options("${target}" PRIVATE
            "$<$<COMPILE_LANGUAGE:C,CXX>:/GS>"
            "$<$<COMPILE_LANGUAGE:C,CXX>:/sdl>"
            "$<$<COMPILE_LANGUAGE:C,CXX>:/guard:cf>")
        if(kind MATCHES "^(EXECUTABLE|SHARED_LIBRARY|MODULE_LIBRARY)$")
            target_link_options("${target}" PRIVATE /guard:cf /DYNAMICBASE /NXCOMPAT)
            if(CMAKE_SIZEOF_VOID_P EQUAL 8)
                target_link_options("${target}" PRIVATE /HIGHENTROPYVA)
            endif()
        endif()
    elseif(CMAKE_SYSTEM_NAME STREQUAL "Linux" AND CMAKE_CXX_COMPILER_ID MATCHES "^(GNU|Clang)$")
        target_compile_options("${target}" PRIVATE
            "$<$<COMPILE_LANGUAGE:C,CXX>:-fstack-protector-strong>")
        set_property(TARGET "${target}" PROPERTY POSITION_INDEPENDENT_CODE TRUE)
        if(kind MATCHES "^(EXECUTABLE|SHARED_LIBRARY|MODULE_LIBRARY)$")
            target_link_options("${target}" PRIVATE -Wl,-z,relro,-z,now,-z,noexecstack)
        endif()
        if(kind STREQUAL "EXECUTABLE")
            target_link_options("${target}" PRIVATE -pie)
        endif()
    else()
        message(FATAL_ERROR "Lorica: unsupported hardening toolchain/platform; no silent fallback")
    endif()
endfunction()

# Why the extended profile (LR-BUILD-03) cannot be applied with this toolchain and
# processor, or empty when it can: MSVC 19.44 (Visual Studio 2022 17.14) x64, for
# the STL's hardening and CET compatibility; GCC 12 or Clang 18 on Linux x86-64 or
# AArch64, the first to take every option and, for Clang's libc++, the
# _LIBCPP_HARDENING_MODE macro.
function(_lorica_extended_unsupported out)
    set(reason "")
    if(MSVC AND WIN32)
        if(MSVC_VERSION LESS 1944)
            set(reason "EXTENDED needs MSVC 19.44 (Visual Studio 2022 17.14) or newer for STL hardening")
        elseif(NOT CMAKE_CXX_COMPILER_ARCHITECTURE_ID STREQUAL "x64")
            set(reason "EXTENDED supports MSVC x64 only (CET shadow stack compatibility)")
        endif()
    elseif(CMAKE_SYSTEM_NAME STREQUAL "Linux" AND CMAKE_CXX_COMPILER_ID MATCHES "^(GNU|Clang)$")
        if((CMAKE_CXX_COMPILER_ID STREQUAL "GNU" AND CMAKE_CXX_COMPILER_VERSION VERSION_LESS 12) OR
           (CMAKE_CXX_COMPILER_ID STREQUAL "Clang" AND CMAKE_CXX_COMPILER_VERSION VERSION_LESS 18))
            set(reason "EXTENDED needs GCC 12 or Clang 18 or newer")
        elseif(NOT CMAKE_SYSTEM_PROCESSOR MATCHES "^(x86_64|AMD64|amd64|aarch64|arm64|ARM64)$")
            set(reason "EXTENDED supports x86-64 and AArch64 only, not ${CMAKE_SYSTEM_PROCESSOR}")
        endif()
    else()
        set(reason "unsupported hardening toolchain/platform")
    endif()
    set(${out} "${reason}" PARENT_SCOPE)
endfunction()

# lorica_extended_hardening_supported(<variable>): TRUE when lorica_harden_target
# can apply EXTENDED here, else FALSE with the reason in <variable>_REASON. For
# callers that must report a check as not run instead of failing configuration.
function(lorica_extended_hardening_supported variable)
    _lorica_extended_unsupported(reason)
    if(reason)
        set(${variable} FALSE PARENT_SCOPE)
    else()
        set(${variable} TRUE PARENT_SCOPE)
    endif()
    set(${variable}_REASON "${reason}" PARENT_SCOPE)
endfunction()

# Extended profile (LR-BUILD-03), on top of the baseline: the hardened standard
# library (out-of-range element access, empty front()/back(), an empty optional's
# value and similar preconditions stop the program instead of corrupting memory,
# as C++26 standard library hardening specifies), _FORTIFY_SOURCE=3 in optimized
# configurations, zero-initialized automatic variables, stack clash protection and
# control-flow protection (x86-64 CET, AArch64 PAC/BTI). A toolchain or processor
# that cannot provide all of it fails configuration instead of getting less.
function(_lorica_apply_extended target kind)
    _lorica_extended_unsupported(reason)
    if(reason)
        message(FATAL_ERROR "Lorica: ${reason}; no silent fallback")
    endif()
    if(MSVC AND WIN32)
        target_compile_definitions("${target}" PRIVATE
            "$<$<COMPILE_LANGUAGE:CXX>:_MSVC_STL_HARDENING=1>"
            "$<$<COMPILE_LANGUAGE:CXX>:_MSVC_STL_DESTRUCTOR_TOMBSTONES=1>")
        if(kind MATCHES "^(EXECUTABLE|SHARED_LIBRARY|MODULE_LIBRARY)$")
            target_link_options("${target}" PRIVATE /CETCOMPAT)
        endif()
    else()
        if(CMAKE_SYSTEM_PROCESSOR MATCHES "^(x86_64|AMD64|amd64)$")
            set(control_flow -fcf-protection=full)
        else()
            set(control_flow -mbranch-protection=standard)
        endif()
        set(optimized "$<CONFIG:Release,RelWithDebInfo,MinSizeRel>")
        target_compile_definitions("${target}" PRIVATE
            "$<$<COMPILE_LANGUAGE:CXX>:_GLIBCXX_ASSERTIONS>"
            "$<$<COMPILE_LANGUAGE:CXX>:_LIBCPP_HARDENING_MODE=_LIBCPP_HARDENING_MODE_EXTENSIVE>")
        target_compile_options("${target}" PRIVATE
            "$<$<COMPILE_LANGUAGE:C,CXX>:-ftrivial-auto-var-init=zero>"
            "$<$<COMPILE_LANGUAGE:C,CXX>:-fstack-clash-protection>"
            "$<$<COMPILE_LANGUAGE:C,CXX>:${control_flow}>"
            # glibc checks only optimized code, and warns without optimization.
            "$<$<AND:$<COMPILE_LANGUAGE:C,CXX>,${optimized}>:-U_FORTIFY_SOURCE>"
            "$<$<AND:$<COMPILE_LANGUAGE:C,CXX>,${optimized}>:-D_FORTIFY_SOURCE=3>")
    endif()
endfunction()

# lorica_harden_target(<target> [EXTENDED])
# Apply explicitly to each locally compiled target. Calling it again with EXTENDED
# adds the extended profile to a target that has the baseline; nothing is applied
# twice and nothing is removed.
function(lorica_harden_target target)
    cmake_parse_arguments(PARSE_ARGV 1 arg "EXTENDED" "" "")
    if(arg_UNPARSED_ARGUMENTS)
        message(FATAL_ERROR "Lorica: unknown lorica_harden_target arguments: ${arg_UNPARSED_ARGUMENTS}")
    endif()
    _lorica_require_compiled_target("${target}")
    get_target_property(kind "${target}" TYPE)
    get_target_property(applied "${target}" LORICA_HARDENED)
    if(NOT applied)
        _lorica_apply_baseline("${target}" "${kind}")
        set_property(TARGET "${target}" PROPERTY LORICA_HARDENED TRUE)
        set_property(TARGET "${target}" PROPERTY LORICA_HARDENING_PROFILE baseline)
    endif()
    get_target_property(profile "${target}" LORICA_HARDENING_PROFILE)
    if(arg_EXTENDED AND NOT profile STREQUAL "extended")
        _lorica_apply_extended("${target}" "${kind}")
        set_property(TARGET "${target}" PROPERTY LORICA_HARDENING_PROFILE extended)
    endif()
endfunction()

# Why lorica_deprecate_unsafe_apis (LR-BUILD-04) cannot cover this toolchain, or
# empty when it can. clang-cl does not honour /we4996; MinGW's C library declares
# the functions without any deprecation; with glibc 2.40 or newer Clang takes
# glibc's fortified overloads (pass_object_size), which no earlier declaration
# reaches, so a fortified build would accept the calls.
function(_lorica_unsafe_api_unsupported out)
    set(reason "")
    if(MSVC AND WIN32)
        if(CMAKE_CXX_COMPILER_ID STREQUAL "Clang")
            set(reason "unsafe API rejection does not support clang-cl, which ignores /we4996")
        endif()
    elseif(WIN32)
        set(reason "unsafe API rejection does not support MinGW, whose C library does not deprecate these functions")
    elseif(CMAKE_CXX_COMPILER_ID MATCHES "^(GNU|Clang)$")
        include(CheckCXXSourceCompiles)
        check_cxx_source_compiles([=[
#if defined(__has_include)
#if __has_include(<gnu/libc-version.h>)
#include <features.h>
#if defined(__fortify_use_clang) && __fortify_use_clang
#error "glibc gives Clang separate fortified overloads"
#endif
#endif
#endif
int main() { return 0; }
]=] LORICA_UNSAFE_API_NO_CLANG_FORTIFY_OVERLOADS)
        if(NOT LORICA_UNSAFE_API_NO_CLANG_FORTIFY_OVERLOADS)
            set(reason "unsafe API rejection does not support Clang with glibc 2.40 or newer, whose fortified overloads it cannot reach; use GCC for this check")
        endif()
    else()
        set(reason "unsafe API rejection does not support ${CMAKE_CXX_COMPILER_ID}")
    endif()
    set(${out} "${reason}" PARENT_SCOPE)
endfunction()

# lorica_unsafe_api_rejection_supported(<variable>): TRUE when
# lorica_deprecate_unsafe_apis can apply here, else FALSE with the reason in
# <variable>_REASON.
function(lorica_unsafe_api_rejection_supported variable)
    _lorica_unsafe_api_unsupported(reason)
    if(reason)
        set(${variable} FALSE PARENT_SCOPE)
    else()
        set(${variable} TRUE PARENT_SCOPE)
    endif()
    set(${variable}_REASON "${reason}" PARENT_SCOPE)
endfunction()

# Run when the top-level directory is done, so sources and precompiled headers
# added after lorica_deprecate_unsafe_apis count too: a precompiled header is
# compiled as a system header (CMake marks it so), where deprecations are not
# reported, and C sources do not get the C++ header.
function(_lorica_check_unsafe_api_target target)
    get_target_property(pch "${target}" PRECOMPILE_HEADERS)
    get_target_property(pch_reuse "${target}" PRECOMPILE_HEADERS_REUSE_FROM)
    if(pch OR pch_reuse)
        message(FATAL_ERROR "Lorica: ${target} uses precompiled headers, which unsafe API rejection cannot check; remove them or the rejection")
    endif()
    get_target_property(sources "${target}" SOURCES)
    foreach(source IN LISTS sources)
        if(source MATCHES "^\\$<")
            continue()
        endif()
        get_source_file_property(language "${source}" TARGET_DIRECTORY "${target}" LANGUAGE)
        if(language STREQUAL "C" OR (NOT language AND source MATCHES "\\.c$"))
            message(FATAL_ERROR "Lorica: ${target} has C source ${source}; unsafe API rejection covers C++ sources only, so move C sources to another target")
        endif()
    endforeach()
endfunction()

# lorica_deprecate_unsafe_apis(<target>) (LR-BUILD-04): a use of the unbounded C
# copy and format functions in the target's C++ sources fails to compile. GCC and
# Clang force-include <lorica/unsafe_api.hpp> and make deprecation warnings errors;
# MSVC makes deprecation warning C4996 an error. Either way every deprecation in
# the target becomes an error, not only these six. Unsupported toolchains, targets
# with C sources or precompiled headers, and C++20 module units (which cannot take
# a force-included header) are refused.
function(lorica_deprecate_unsafe_apis target)
    _lorica_require_compiled_target("${target}")
    get_target_property(applied "${target}" LORICA_UNSAFE_APIS_DEPRECATED)
    if(applied)
        return()
    endif()
    _lorica_unsafe_api_unsupported(reason)
    if(reason)
        message(FATAL_ERROR "Lorica: ${reason}; no silent fallback")
    endif()
    if(MSVC AND WIN32)
        target_compile_options("${target}" PRIVATE "$<$<COMPILE_LANGUAGE:CXX>:/we4996>")
    else()
        get_property(header GLOBAL PROPERTY LORICA_UNSAFE_API_HEADER)
        if(NOT EXISTS "${header}")
            message(FATAL_ERROR "Lorica: lorica/unsafe_api.hpp not found; use find_package(Lorica) or set LORICA_INCLUDE_DIR")
        endif()
        target_compile_options("${target}" PRIVATE
            "$<$<COMPILE_LANGUAGE:CXX>:SHELL:-include \"${header}\">"
            "$<$<COMPILE_LANGUAGE:CXX>:-Werror=deprecated-declarations>")
    endif()
    set_property(TARGET "${target}" PROPERTY LORICA_UNSAFE_APIS_DEPRECATED TRUE)
    # A deferred call's arguments are read when it runs, so the name is put in now.
    cmake_language(EVAL CODE
        "cmake_language(DEFER DIRECTORY [[${CMAKE_SOURCE_DIR}]] CALL _lorica_check_unsafe_api_target [[${target}]])")
endfunction()
