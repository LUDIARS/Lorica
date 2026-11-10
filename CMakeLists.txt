cmake_minimum_required(VERSION 3.24)
project(Lorica VERSION 0.1.0 LANGUAGES CXX)

include(GNUInstallDirs)
include(CMakePackageConfigHelpers)
add_library(lorica_boundary INTERFACE)
add_library(Lorica::boundary ALIAS lorica_boundary)
set_target_properties(lorica_boundary PROPERTIES EXPORT_NAME boundary)
target_compile_features(lorica_boundary INTERFACE cxx_std_17)
target_include_directories(lorica_boundary INTERFACE
    $<BUILD_INTERFACE:${CMAKE_CURRENT_SOURCE_DIR}/include>
    $<INSTALL_INTERFACE:${CMAKE_INSTALL_INCLUDEDIR}>)
include(cmake/LoricaHardening.cmake)

option(LORICA_BUILD_PROTECTION "Build OS read-only scalar protection" ON)
if(LORICA_BUILD_PROTECTION)
    if(WIN32)
        set(lorica_protection_source src/sealed_region_windows.cpp)
    elseif(CMAKE_SYSTEM_NAME STREQUAL "Linux")
        set(lorica_protection_source src/sealed_region_linux.cpp)
    else()
        message(FATAL_ERROR "Lorica protection requires Windows or Linux")
    endif()
    add_library(lorica_protection STATIC ${lorica_protection_source})
    add_library(Lorica::protection ALIAS lorica_protection)
    set_target_properties(lorica_protection PROPERTIES EXPORT_NAME protection)
    target_link_libraries(lorica_protection PUBLIC Lorica::boundary)
    lorica_harden_target(lorica_protection)
    install(TARGETS lorica_protection EXPORT LoricaTargets
        ARCHIVE DESTINATION ${CMAKE_INSTALL_LIBDIR})
endif()

option(LORICA_BUILD_TESTS "Build boundary contract tests" OFF)
option(LORICA_BUILD_FUZZER "Build Clang libFuzzer target (test use only)" OFF)
if(LORICA_BUILD_TESTS)
    enable_testing()
    find_package(Python3 REQUIRED COMPONENTS Interpreter)
    add_executable(lorica_boundary_tests tests/boundary.cpp)
    target_link_libraries(lorica_boundary_tests PRIVATE Lorica::boundary)
    lorica_harden_target(lorica_boundary_tests)
    add_test(NAME lorica.boundary COMMAND lorica_boundary_tests)
    # The C++20 headers, as C++20 and as C++23, under the extended profile and with
    # the unbounded C APIs rejected, where the toolchain offers each. Checks the
    # toolchain cannot run are reported as not run, never as passed.
    lorica_extended_hardening_supported(lorica_extended)
    lorica_unsafe_api_rejection_supported(lorica_unsafe_api)
    foreach(standard 20 23)
        add_executable(lorica_checked_tests_cxx${standard} tests/checked.cpp)
        target_link_libraries(lorica_checked_tests_cxx${standard} PRIVATE Lorica::boundary)
        target_compile_features(lorica_checked_tests_cxx${standard} PRIVATE cxx_std_${standard})
        if(lorica_extended)
            lorica_harden_target(lorica_checked_tests_cxx${standard} EXTENDED)
        else()
            lorica_harden_target(lorica_checked_tests_cxx${standard})
        endif()
        if(lorica_unsafe_api)
            lorica_deprecate_unsafe_apis(lorica_checked_tests_cxx${standard})
        endif()
        add_test(NAME lorica.checked.cxx${standard} COMMAND lorica_checked_tests_cxx${standard})
    endforeach()
    if(lorica_extended)
        set(lorica_fortified "$<AND:$<CONFIG:Release,RelWithDebInfo,MinSizeRel>,$<NOT:$<BOOL:${WIN32}>>>")
        add_executable(lorica_hardening_tests tests/hardening.cpp)
        target_compile_features(lorica_hardening_tests PRIVATE cxx_std_17)
        target_compile_definitions(lorica_hardening_tests PRIVATE
            "$<${lorica_fortified}:LORICA_TEST_EXPECT_FORTIFY=3>")
        lorica_harden_target(lorica_hardening_tests EXTENDED)
        add_test(NAME lorica.hardening_stops
            COMMAND ${Python3_EXECUTABLE} ${CMAKE_CURRENT_SOURCE_DIR}/tests/hardening_fault.py
                $<TARGET_FILE:lorica_hardening_tests>
                $<IF:${lorica_fortified},fortified,unfortified>)
    else()
        message(STATUS "Lorica: lorica.hardening_stops not run: ${lorica_extended_REASON}")
        add_test(NAME lorica.hardening_stops COMMAND ${CMAKE_COMMAND} -E false)
        set_tests_properties(lorica.hardening_stops PROPERTIES DISABLED TRUE)
    endif()
    include(tests/unsafe_api_probes.cmake)
    lorica_add_unsafe_api_probes()
    if(LORICA_BUILD_PROTECTION)
        add_executable(lorica_protection_tests tests/protection.cpp)
        target_link_libraries(lorica_protection_tests PRIVATE Lorica::protection)
        lorica_harden_target(lorica_protection_tests)
        add_test(NAME lorica.protection COMMAND lorica_protection_tests)
        add_test(NAME lorica.protection_write_denied
            COMMAND ${Python3_EXECUTABLE} ${CMAKE_CURRENT_SOURCE_DIR}/tests/protection_fault.py
                $<TARGET_FILE:lorica_protection_tests>)
    endif()
endif()
if(LORICA_BUILD_FUZZER)
    if(NOT CMAKE_CXX_COMPILER_ID STREQUAL "Clang" OR NOT CMAKE_SYSTEM_NAME STREQUAL "Linux")
        message(FATAL_ERROR "Lorica fuzzing currently requires Linux Clang")
    endif()
    add_executable(lorica_boundary_fuzz tests/fuzz_boundary.cpp)
    target_link_libraries(lorica_boundary_fuzz PRIVATE Lorica::boundary)
    target_compile_options(lorica_boundary_fuzz PRIVATE -fsanitize=fuzzer,address,undefined)
    target_link_options(lorica_boundary_fuzz PRIVATE -fsanitize=fuzzer,address,undefined)
endif()

install(TARGETS lorica_boundary EXPORT LoricaTargets)
install(DIRECTORY include/ DESTINATION ${CMAKE_INSTALL_INCLUDEDIR})
install(EXPORT LoricaTargets NAMESPACE Lorica:: DESTINATION ${CMAKE_INSTALL_LIBDIR}/cmake/Lorica)
configure_package_config_file(cmake/LoricaConfig.cmake.in
    ${CMAKE_CURRENT_BINARY_DIR}/LoricaConfig.cmake
    INSTALL_DESTINATION ${CMAKE_INSTALL_LIBDIR}/cmake/Lorica
    PATH_VARS CMAKE_INSTALL_INCLUDEDIR)
write_basic_package_version_file(${CMAKE_CURRENT_BINARY_DIR}/LoricaConfigVersion.cmake
    VERSION ${PROJECT_VERSION} COMPATIBILITY SameMajorVersion)
install(FILES ${CMAKE_CURRENT_BINARY_DIR}/LoricaConfig.cmake
    ${CMAKE_CURRENT_BINARY_DIR}/LoricaConfigVersion.cmake
    cmake/LoricaHardening.cmake cmake/LoricaInject.cmake
    DESTINATION ${CMAKE_INSTALL_LIBDIR}/cmake/Lorica)
