# SPEC-LR-CXX23: LoricaInject.cmake runs before the consuming project enables its
# languages, when the C++23 switch is not yet known. CMake includes this file as
# CMAKE_USER_MAKE_RULES_OVERRIDE_CXX right after the compiler's own settings, in
# the top-level directory, so every directory of the build inherits ISO C++23.
# An override the consuming project had set is included first and kept.
if(LORICA_CONSUMER_MAKE_RULES_OVERRIDE_CXX)
    include("${LORICA_CONSUMER_MAKE_RULES_OVERRIDE_CXX}")
endif()
include("${CMAKE_CURRENT_LIST_DIR}/LoricaCxxStandard.cmake")
lorica_use_iso_cxx23()
