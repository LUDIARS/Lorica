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

include(CheckCompilerFlag)
include(CheckSourceCompiles)
include(CheckLinkerFlag)
include(CMakePushCheckState)

# CMake's check modules cache by result name. Share probes between targets,
# but recheck after reconfiguration or a subdirectory's toolchain flag change.
function(_lorica_prepare_checks)
    set(configs ${CMAKE_CONFIGURATION_TYPES} "${CMAKE_BUILD_TYPE}" "${CMAKE_TRY_COMPILE_CONFIGURATION}")
    list(APPEND configs Debug Release RelWithDebInfo MinSizeRel)
    set(inputs "${CMAKE_SYSROOT};${CMAKE_SYSROOT_COMPILE};${CMAKE_SYSROOT_LINK};${CMAKE_TRY_COMPILE_TARGET_TYPE}")
    foreach(lang C CXX EXE_LINKER)
        list(APPEND inputs "${CMAKE_${lang}_COMPILER}" "${CMAKE_${lang}_COMPILER_TARGET}" "${CMAKE_${lang}_FLAGS}")
        foreach(config IN LISTS configs)
            string(TOUPPER "${config}" config)
            list(APPEND inputs "${config}=${CMAKE_${lang}_FLAGS_${config}}")
        endforeach()
    endforeach()
    string(SHA256 signature "${inputs}")
    get_property(previous GLOBAL PROPERTY _LORICA_PROBE_SIGNATURE)
    if(NOT signature STREQUAL previous)
        get_cmake_property(keys CACHE_VARIABLES)
        foreach(key IN LISTS keys)
            if(key MATCHES "^_LORICA_PROBE_")
                unset(${key} CACHE)
            endif()
        endforeach()
        set_property(GLOBAL PROPERTY _LORICA_PROBE_SIGNATURE "${signature}")
    endif()
endfunction()

function(_lorica_warn_once key detail)
    get_property(reported GLOBAL PROPERTY "_LORICA_WARNED_${key}")
    if(NOT reported)
        message(WARNING "Lorica baseline: ${detail}")
        set_property(GLOBAL PROPERTY "_LORICA_WARNED_${key}" TRUE)
    endif()
endfunction()

# Probe libc's effective level using this configuration's actual optimization.
function(_lorica_fortify_level lang config preferred out)
    # A custom multi-config list may include MinSizeRel, which Ninja's default
    # inner try_compile project would otherwise omit.
    list(APPEND CMAKE_TRY_COMPILE_PLATFORM_VARIABLES CMAKE_CONFIGURATION_TYPES)
    set(CMAKE_TRY_COMPILE_CONFIGURATION "${config}")
    string(TOUPPER "${config}" upper)
    set(levels "${preferred}" 2)
    list(REMOVE_DUPLICATES levels)
    foreach(level IN LISTS levels)
        set(probe "_LORICA_PROBE_${lang}_${upper}_FORTIFY_${level}")
        # Lorica's -U/-D pair follows the toolchain's config-specific -D flags.
        check_source_compiles(${lang} "
            #undef _FORTIFY_SOURCE
            #define _FORTIFY_SOURCE ${level}
            #include <string.h>
            #if !defined(__USE_FORTIFY_LEVEL) || __USE_FORTIFY_LEVEL != ${level}
            #error requested libc fortification is inactive
            #endif
            int main(void) { return 0; }" ${probe})
        if(${probe})
            set(${out} "${level}" PARENT_SCOPE)
            return()
        endif()
    endforeach()
    set(${out} 0 PARENT_SCOPE)
endfunction()

# A consumer may select another standard library in only one configuration.
function(_lorica_check_extended_stdlib config out)
    cmake_push_check_state(RESET)
    list(APPEND CMAKE_TRY_COMPILE_PLATFORM_VARIABLES CMAKE_CONFIGURATION_TYPES)
    set(CMAKE_TRY_COMPILE_CONFIGURATION "${config}")
    string(MAKE_C_IDENTIFIER "${config}_STDLIB" key)
    set(probe "_LORICA_PROBE_EXTENSIVE_${key}")
    check_source_compiles(CXX [=[
        #undef _GLIBCXX_ASSERTIONS
        #define _GLIBCXX_ASSERTIONS 1
        #undef _LIBCPP_HARDENING_MODE
        #define _LIBCPP_HARDENING_MODE _LIBCPP_HARDENING_MODE_EXTENSIVE
        #include <cstddef>
        static_assert(sizeof(void*) == 8, "EXTENDED needs a 64-bit ABI");
        #if defined(_LIBCPP_VERSION)
        #if !defined(_LIBCPP_HARDENING_MODE_EXTENSIVE) || _LIBCPP_HARDENING_MODE != _LIBCPP_HARDENING_MODE_EXTENSIVE
        #error libc++ lacks extensive hardening
        #endif
        #elif !defined(__GLIBCXX__) || !defined(__glibcxx_assert)
        #error unsupported standard library
        #endif
        int main() { return 0; }
    ]=] ${probe})
    cmake_pop_check_state()
    set(${out} "${${probe}}" PARENT_SCOPE)
endfunction()

# With a target, emit baseline options. Without one, check the same capabilities
# for EXTENDED and return the first missing requirement. Use each enabled driver:
# a downstream C library need not use the same compiler as its C++ consumer.
function(_lorica_linux_capabilities target out)
    _lorica_prepare_checks()
    cmake_push_check_state(RESET)
    set(${out} "" PARENT_SCOPE)
    set(flags -fstack-clash-protection)
    if(CMAKE_SYSTEM_PROCESSOR MATCHES "^(aarch64|arm64|ARM64)$")
        list(APPEND flags -mbranch-protection=standard)
    else()
        list(APPEND flags -fcf-protection=full)
    endif()
    if("${target}" STREQUAL "")
        list(APPEND flags -fstack-protector-strong -ftrivial-auto-var-init=zero)
    endif()
    get_property(multi GLOBAL PROPERTY GENERATOR_IS_MULTI_CONFIG)
    if(multi)
        set(configs ${CMAKE_CONFIGURATION_TYPES})
    else()
        set(configs ${CMAKE_BUILD_TYPE})
    endif()

    foreach(lang C CXX)
        if(NOT CMAKE_${lang}_COMPILER_LOADED)
            continue()
        endif()
        foreach(flag IN LISTS flags)
            string(MAKE_C_IDENTIFIER "${flag}" key)
            set(probe "_LORICA_PROBE_${lang}_${key}")
            check_compiler_flag(${lang} "${flag}" ${probe})
            if(${probe})
                if(NOT "${target}" STREQUAL "")
                    target_compile_options("${target}" PRIVATE "$<$<COMPILE_LANGUAGE:${lang}>:${flag}>")
                endif()
            elseif(NOT "${target}" STREQUAL "")
                _lorica_warn_once("${probe}" "${lang} does not support ${flag}, omitting it")
            else()
                set(${out} "EXTENDED requires ${flag} for ${lang}" PARENT_SCOPE)
                return()
            endif()
        endforeach()

        foreach(config IN LISTS configs)
            string(TOUPPER "${config}" upper)
            if(NOT upper MATCHES "^(RELEASE|RELWITHDEBINFO|MINSIZEREL)$")
                continue()
            endif()
            set(preferred 2)
            if(CMAKE_${lang}_COMPILER_VERSION VERSION_GREATER_EQUAL 12)
                set(preferred 3)
            endif()
            _lorica_fortify_level("${lang}" "${config}" "${preferred}" selected)
            if(NOT "${target}" STREQUAL "")
                if(selected)
                    target_compile_options("${target}" PRIVATE
                        "$<$<AND:$<COMPILE_LANGUAGE:${lang}>,$<CONFIG:${config}>>:SHELL:-U_FORTIFY_SOURCE -D_FORTIFY_SOURCE=${selected}>")
                endif()
                if(NOT selected STREQUAL preferred)
                    _lorica_warn_once("${lang}_${upper}_FORTIFY"
                        "${lang} ${config} cannot enable FORTIFY ${preferred} (selected level ${selected})")
                endif()
            elseif(NOT selected STREQUAL "3")
                set(${out} "EXTENDED requires effective _FORTIFY_SOURCE=3 for ${lang} ${config}" PARENT_SCOPE)
                return()
            endif()
        endforeach()
    endforeach()
    cmake_pop_check_state()
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
        _lorica_linux_capabilities("${target}" unused_reason)
        # Read the final profile at generation time, including a later upgrade.
        set(extended "$<STREQUAL:$<TARGET_PROPERTY:LORICA_HARDENING_PROFILE>,extended>")
        set(mode "$<IF:${extended},_LIBCPP_HARDENING_MODE_EXTENSIVE,_LIBCPP_HARDENING_MODE_FAST>")
        target_compile_options("${target}" PRIVATE
            "$<$<COMPILE_LANGUAGE:CXX>:SHELL:-U_GLIBCXX_ASSERTIONS -D_GLIBCXX_ASSERTIONS>"
            "$<$<COMPILE_LANGUAGE:CXX>:SHELL:-U_LIBCPP_HARDENING_MODE -D_LIBCPP_HARDENING_MODE=${mode}>")
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
    _lorica_prepare_checks()
    set(reason "")
    if(NOT CMAKE_CXX_COMPILER_LOADED)
        set(reason "the CXX language is not enabled; Lorica's build functions require it")
    elseif(MSVC AND WIN32)
        if(NOT CMAKE_CXX_COMPILER_ID STREQUAL "MSVC" OR MSVC_VERSION LESS 1944)
            set(reason "EXTENDED needs MSVC 19.44 (Visual Studio 2022 17.14) or newer for STL hardening")
        elseif(NOT CMAKE_CXX_COMPILER_ARCHITECTURE_ID STREQUAL "x64")
            set(reason "EXTENDED supports MSVC x64 only (CET shadow stack compatibility)")
        else()
            cmake_push_check_state(RESET)
            check_source_compiles(CXX [=[
                #undef _MSVC_STL_HARDENING
                #undef _MSVC_STL_DESTRUCTOR_TOMBSTONES
                #include <vector>
                #if !defined(_MSVC_STL_HARDENING) || !defined(_MSVC_STL_DESTRUCTOR_TOMBSTONES)
                #error STL does not recognize both hardening switches
                #endif
                int main() { return 0; }
            ]=] _LORICA_PROBE_MSVC_STL)
            set(CMAKE_TRY_COMPILE_TARGET_TYPE EXECUTABLE)
            check_linker_flag(CXX "/CETCOMPAT" _LORICA_PROBE_MSVC_CET)
            cmake_pop_check_state()
            if(NOT _LORICA_PROBE_MSVC_STL OR NOT _LORICA_PROBE_MSVC_CET)
                set(reason "EXTENDED requires STL hardening, destructor tombstones and /CETCOMPAT")
            endif()
        endif()
    elseif(CMAKE_SYSTEM_NAME STREQUAL "Linux" AND CMAKE_CXX_COMPILER_ID MATCHES "^(GNU|Clang)$")
        if((CMAKE_CXX_COMPILER_ID STREQUAL "GNU" AND CMAKE_CXX_COMPILER_VERSION VERSION_LESS 12) OR
           (CMAKE_CXX_COMPILER_ID STREQUAL "Clang" AND CMAKE_CXX_COMPILER_VERSION VERSION_LESS 18))
            set(reason "EXTENDED needs GCC 12 or Clang 18 or newer")
        elseif(NOT CMAKE_SYSTEM_PROCESSOR MATCHES "^(x86_64|AMD64|amd64|aarch64|arm64|ARM64)$")
            set(reason "EXTENDED supports x86-64 and AArch64 only, not ${CMAKE_SYSTEM_PROCESSOR}")
        elseif(NOT CMAKE_SIZEOF_VOID_P EQUAL 8)
            set(reason "EXTENDED requires a 64-bit Linux target ABI")
        else()
            _lorica_linux_capabilities("" reason)
            if(NOT reason)
                get_property(multi GLOBAL PROPERTY GENERATOR_IS_MULTI_CONFIG)
                if(multi)
                    set(configs ${CMAKE_CONFIGURATION_TYPES})
                else()
                    set(configs "${CMAKE_BUILD_TYPE}")
                endif()
                # An empty single-config build type also needs a header check.
                if(NOT configs)
                    _lorica_check_extended_stdlib("" usable)
                else()
                    foreach(config IN LISTS configs)
                        _lorica_check_extended_stdlib("${config}" usable)
                        if(NOT usable)
                            break()
                        endif()
                    endforeach()
                endif()
                if(NOT usable)
                    set(reason "EXTENDED requires libstdc++ assertions or libc++ EXTENSIVE hardening")
                endif()
            endif()
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
    if(MSVC AND WIN32)
        target_compile_definitions("${target}" PRIVATE
            "$<$<COMPILE_LANGUAGE:CXX>:_MSVC_STL_HARDENING=1>"
            "$<$<COMPILE_LANGUAGE:CXX>:_MSVC_STL_DESTRUCTOR_TOMBSTONES=1>")
        if(kind MATCHES "^(EXECUTABLE|SHARED_LIBRARY|MODULE_LIBRARY)$")
            target_link_options("${target}" PRIVATE /CETCOMPAT)
        endif()
    else()
        target_compile_options("${target}" PRIVATE
            "$<$<COMPILE_LANGUAGE:C,CXX>:-ftrivial-auto-var-init=zero>")
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
    if(NOT CMAKE_CXX_COMPILER_LOADED)
        message(FATAL_ERROR "Lorica: the CXX language is not enabled; Lorica's build functions require it")
    endif()
    _lorica_require_compiled_target("${target}")
    get_target_property(kind "${target}" TYPE)
    get_target_property(applied "${target}" LORICA_HARDENED)
    get_target_property(profile "${target}" LORICA_HARDENING_PROFILE)
    if(arg_EXTENDED AND NOT profile STREQUAL "extended")
        _lorica_extended_unsupported(reason)
        if(reason)
            message(FATAL_ERROR "Lorica: ${reason}; no silent fallback")
        endif()
    endif()
    if(NOT applied)
        _lorica_apply_baseline("${target}" "${kind}")
        set_property(TARGET "${target}" PROPERTY LORICA_HARDENED TRUE)
        set_property(TARGET "${target}" PROPERTY LORICA_HARDENING_PROFILE baseline)
    endif()
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
    _lorica_prepare_checks()
    set(reason "")
    if(NOT CMAKE_CXX_COMPILER_LOADED)
        set(reason "the CXX language is not enabled; Lorica's build functions require it")
    elseif(MSVC AND WIN32)
        if(CMAKE_CXX_COMPILER_ID STREQUAL "Clang")
            set(reason "unsafe API rejection does not support clang-cl, which ignores /we4996")
        endif()
    elseif(WIN32)
        set(reason "unsafe API rejection does not support MinGW, whose C library does not deprecate these functions")
    elseif(CMAKE_SYSTEM_NAME STREQUAL "Linux" AND CMAKE_CXX_COMPILER_ID MATCHES "^(GNU|Clang)$")
        check_source_compiles(CXX [=[
#if defined(__has_include)
#if __has_include(<gnu/libc-version.h>)
#include <features.h>
#if defined(__clang__) && __GLIBC_PREREQ(2, 40)
#error "fortified target builds use separate overloads even when this probe is unfortified"
#elif defined(__fortify_use_clang) && __fortify_use_clang
#error "glibc gives Clang separate fortified overloads"
#endif
#endif
#endif
int main() { return 0; }
]=] _LORICA_PROBE_NO_CLANG_FORTIFY_OVERLOADS)
        if(NOT _LORICA_PROBE_NO_CLANG_FORTIFY_OVERLOADS)
            set(reason "unsafe API rejection does not support Clang with glibc 2.40 or newer, whose fortified overloads it cannot reach; use GCC for this check")
        endif()
    else()
        set(reason "unsafe API rejection does not support ${CMAKE_CXX_COMPILER_ID} on ${CMAKE_SYSTEM_NAME}")
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
# reported, and a C source would stop at the C++ header's #error. Refused here for
# a readable message; inherited precompiled headers are switched off and C sources
# this scan cannot see still stop at that #error.
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
# the target becomes an error, not only these six. Unsupported toolchains and
# targets with C sources or precompiled headers are refused; precompiled headers
# inherited from linked targets are switched off. C++20 module units cannot take a
# force-included header and fail to compile.
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
    # SHELL: keeps CMake from dropping an option the target already has earlier,
    # where a later -Wno-error=... would then win.
    if(MSVC AND WIN32)
        target_compile_options("${target}" PRIVATE "$<$<COMPILE_LANGUAGE:CXX>:SHELL:/we4996>")
    else()
        get_property(header GLOBAL PROPERTY LORICA_UNSAFE_API_HEADER)
        if(NOT EXISTS "${header}")
            message(FATAL_ERROR "Lorica: lorica/unsafe_api.hpp not found; use find_package(Lorica) or set LORICA_INCLUDE_DIR")
        endif()
        # C units get the header too, whose #error stops them however they were added.
        target_compile_options("${target}" PRIVATE
            "$<$<COMPILE_LANGUAGE:C,CXX>:SHELL:-include \"${header}\">"
            "$<$<COMPILE_LANGUAGE:CXX>:SHELL:-Werror=deprecated-declarations>"
            "$<$<AND:$<COMPILE_LANGUAGE:CXX>,$<CXX_COMPILER_ID:Clang>>:SHELL:-Werror=user-defined-warnings>")
    endif()
    # A precompiled header inherited from a linked target is compiled as a system header.
    set_property(TARGET "${target}" PROPERTY DISABLE_PRECOMPILE_HEADERS ON)
    set_property(TARGET "${target}" PROPERTY LORICA_UNSAFE_APIS_DEPRECATED TRUE)
    # A deferred call's arguments are read when it runs, so the name is put in now.
    cmake_language(EVAL CODE
        "cmake_language(DEFER DIRECTORY [[${CMAKE_SOURCE_DIR}]] CALL _lorica_check_unsafe_api_target [[${target}]])")
endfunction()
