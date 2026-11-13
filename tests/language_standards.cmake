# SPEC-LR-CXX23, SPEC-LR-VERIFY: lorica.standard.cxx17/20/23 build tests/standard.cpp
# with cxx_std_17/20/23 and check the language version each request selects. The
# C++23 check is registered disabled with the reason where cxx_std_23 selects a
# draft mode (MSVC before 19.52) or no C++23 mode exists.
function(lorica_add_language_standard_tests)
    lorica_iso_cxx23_supported(iso_cxx23)
    foreach(standard IN ITEMS 17 20 23)
        set(test lorica.standard.cxx${standard})
        if(standard EQUAL 23 AND NOT iso_cxx23)
            message(STATUS "Lorica: ${test} not run: ${iso_cxx23_REASON}")
            lorica_add_disabled_test(${test})
            continue()
        endif()
        set(target lorica_standard_tests_cxx${standard})
        add_executable(${target} tests/standard.cpp)
        target_compile_features(${target} PRIVATE cxx_std_${standard})
        target_compile_definitions(${target} PRIVATE LORICA_TEST_STANDARD=${standard})
        lorica_harden_target(${target})
        add_test(NAME ${test} COMMAND ${target})
    endforeach()
endfunction()
