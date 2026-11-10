include_guard(GLOBAL)

# Apply explicitly to each locally compiled target. Imported dependencies must
# be rebuilt/audited separately; a usage requirement cannot retrofit their code.
include(CheckCXXCompilerFlag)

# _FORTIFY_SOURCE=3 needs GCC 12+ or Clang 12+; older compilers get level 2.
function(_lorica_fortify_level out)
    if((CMAKE_CXX_COMPILER_ID STREQUAL "GNU" AND CMAKE_CXX_COMPILER_VERSION VERSION_GREATER_EQUAL 12) OR
       (CMAKE_CXX_COMPILER_ID STREQUAL "Clang" AND CMAKE_CXX_COMPILER_VERSION VERSION_GREATER_EQUAL 12))
        set(${out} 3 PARENT_SCOPE)
    else()
        set(${out} 2 PARENT_SCOPE)
    endif()
endfunction()

# Adds a flag the compiler supports on this architecture. An unsupported flag is not added and is
# reported once per configure, so its absence is never silent.
function(_lorica_optional_flag target flag cache_var)
    check_cxx_compiler_flag("${flag}" ${cache_var})
    if(${cache_var})
        target_compile_options("${target}" PRIVATE "$<$<COMPILE_LANGUAGE:C,CXX>:${flag}>")
    else()
        get_property(reported GLOBAL PROPERTY _LORICA_REPORTED_${cache_var})
        if(NOT reported)
            message(WARNING "Lorica: ${flag} is not supported by this compiler/architecture; not applied")
            set_property(GLOBAL PROPERTY _LORICA_REPORTED_${cache_var} TRUE)
        endif()
    endif()
endfunction()

function(lorica_harden_target target)
    if(NOT TARGET "${target}")
        message(FATAL_ERROR "Lorica: missing target ${target}")
    endif()
    get_target_property(imported "${target}" IMPORTED)
    get_target_property(alias "${target}" ALIASED_TARGET)
    get_target_property(kind "${target}" TYPE)
    if(imported OR alias OR NOT kind MATCHES "^(EXECUTABLE|STATIC_LIBRARY|SHARED_LIBRARY|MODULE_LIBRARY|OBJECT_LIBRARY)$")
        message(FATAL_ERROR "Lorica: ${target} must be a concrete locally compiled target")
    endif()
    get_target_property(applied "${target}" LORICA_HARDENED)
    if(applied)
        return()
    endif()
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
        # Standard-library precondition checks (out-of-range operator[], empty optional/front/back ...)
        # abort instead of reading or writing out of bounds. Each macro is read by one library only.
        target_compile_definitions("${target}" PRIVATE
            "$<$<COMPILE_LANGUAGE:CXX>:_GLIBCXX_ASSERTIONS>"
            "$<$<COMPILE_LANGUAGE:CXX>:_LIBCPP_HARDENING_MODE=_LIBCPP_HARDENING_MODE_FAST>")
        # glibc fortified calls need optimization; an unoptimized build only gets a warning from them,
        # so the request is limited to the optimized configurations. Stated here instead of relying on
        # a distribution's compiler default.
        _lorica_fortify_level(_lorica_fortify)
        target_compile_options("${target}" PRIVATE
            "$<$<AND:$<COMPILE_LANGUAGE:C,CXX>,$<CONFIG:Release,RelWithDebInfo,MinSizeRel>>:-U_FORTIFY_SOURCE>"
            "$<$<AND:$<COMPILE_LANGUAGE:C,CXX>,$<CONFIG:Release,RelWithDebInfo,MinSizeRel>>:-D_FORTIFY_SOURCE=${_lorica_fortify}>")
        # Architecture-dependent mitigations: applied where the compiler accepts them, reported where not.
        _lorica_optional_flag("${target}" -fstack-clash-protection LORICA_HAS_STACK_CLASH_PROTECTION)
        _lorica_optional_flag("${target}" -fcf-protection=full LORICA_HAS_CF_PROTECTION)
        if(kind MATCHES "^(EXECUTABLE|SHARED_LIBRARY|MODULE_LIBRARY)$")
            target_link_options("${target}" PRIVATE -Wl,-z,relro,-z,now,-z,noexecstack)
        endif()
        if(kind STREQUAL "EXECUTABLE")
            target_link_options("${target}" PRIVATE -pie)
        endif()
    else()
        message(FATAL_ERROR "Lorica: unsupported hardening toolchain/platform; no silent fallback")
    endif()
    set_property(TARGET "${target}" PROPERTY LORICA_HARDENED TRUE)
endfunction()
