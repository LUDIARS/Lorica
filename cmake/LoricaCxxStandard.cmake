# SPEC-LR-CXX23: C++23 means ISO C++23, not the compiler's newest draft mode.
# CMake maps cxx_std_23 to /std:c++latest for every MSVC from 19.29 on, which also
# enables C++26 draft features. MSVC 19.52 (Visual Studio 2026 18.12) is the first
# with the ISO /std:c++23 switch, so lorica_use_iso_cxx23 uses it there. Older MSVC
# has no ISO C++23 mode and keeps CMake's mapping; lorica_iso_cxx23_supported says
# so, so a check that needs ISO C++23 is reported as not run.
include_guard(GLOBAL)

# lorica_use_iso_cxx23(): call at directory scope after project() (or after
# enable_language(CXX)). It is a macro because CMake reads the standard switch
# from directory-scope variables: it affects targets in the calling directory and
# its subdirectories, never a parent project. It changes only the C++23 switch and
# only where it would otherwise be a latest-draft switch on MSVC 19.52 or newer.
macro(lorica_use_iso_cxx23)
    if(CMAKE_CXX_COMPILER_ID STREQUAL "MSVC" AND
       CMAKE_CXX_COMPILER_VERSION VERSION_GREATER_EQUAL 19.52 AND
       CMAKE_CXX23_STANDARD_COMPILE_OPTION MATCHES "^[-/]std:c\\+\\+latest$")
        set(CMAKE_CXX23_STANDARD_COMPILE_OPTION -std:c++23)
        set(CMAKE_CXX23_EXTENSION_COMPILE_OPTION -std:c++23)
    endif()
endmacro()

# lorica_iso_cxx23_supported(<variable>): TRUE when cxx_std_23 selects ISO C++23
# in the calling directory, else FALSE with the reason in <variable>_REASON.
function(lorica_iso_cxx23_supported variable)
    set(reason "")
    if(NOT "cxx_std_23" IN_LIST CMAKE_CXX_COMPILE_FEATURES)
        set(reason "the C++ compiler offers no C++23 mode")
    elseif(CMAKE_CXX23_STANDARD_COMPILE_OPTION MATCHES "latest|26")
        string(CONCAT reason "cxx_std_23 selects ${CMAKE_CXX23_STANDARD_COMPILE_OPTION} here, a draft "
                   "mode; ISO C++23 on MSVC needs 19.52 or newer with lorica_use_iso_cxx23()")
    endif()
    if(reason)
        set(${variable} FALSE PARENT_SCOPE)
    else()
        set(${variable} TRUE PARENT_SCOPE)
    endif()
    set(${variable}_REASON "${reason}" PARENT_SCOPE)
endfunction()
