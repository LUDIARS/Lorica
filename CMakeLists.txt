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

# All modules in a process must import the same contracts runtime.
add_library(lorica_contracts SHARED src/contract_violation.cpp)
add_library(Lorica::contracts ALIAS lorica_contracts)
set_target_properties(lorica_contracts PROPERTIES
    EXPORT_NAME contracts
    DEFINE_SYMBOL LORICA_BUILDING_CONTRACTS
    CXX_VISIBILITY_PRESET hidden
    VISIBILITY_INLINES_HIDDEN YES
    SOVERSION ${PROJECT_VERSION_MAJOR})
target_link_libraries(lorica_contracts PUBLIC Lorica::boundary)
lorica_harden_target(lorica_contracts)
install(TARGETS lorica_contracts EXPORT LoricaTargets
    RUNTIME DESTINATION ${CMAKE_INSTALL_BINDIR}
    LIBRARY DESTINATION ${CMAKE_INSTALL_LIBDIR}
    ARCHIVE DESTINATION ${CMAKE_INSTALL_LIBDIR})

option(LORICA_BUILD_TESTS "Build boundary contract tests" OFF)
option(LORICA_BUILD_FUZZER "Build Clang libFuzzer target (test use only)" OFF)
if(LORICA_BUILD_TESTS)
    enable_testing()
    add_executable(lorica_boundary_tests tests/boundary.cpp)
    target_link_libraries(lorica_boundary_tests PRIVATE Lorica::boundary)
    lorica_harden_target(lorica_boundary_tests)
    add_test(NAME lorica.boundary COMMAND lorica_boundary_tests)
    find_package(Python3 REQUIRED COMPONENTS Interpreter)

    add_subdirectory(tests/contract_modules)

    # Contracts: observe at each supported standard, ignore, then termination in children.
    foreach(standard IN ITEMS 17 20 23)
        if(standard IN_LIST CMAKE_CXX_COMPILE_FEATURES OR "cxx_std_${standard}" IN_LIST CMAKE_CXX_COMPILE_FEATURES)
            add_executable(lorica_contracts_observe_cxx${standard} tests/contracts_observe.cpp)
            target_link_libraries(lorica_contracts_observe_cxx${standard} PRIVATE Lorica::contracts)
            target_compile_definitions(lorica_contracts_observe_cxx${standard} PRIVATE
                LORICA_CONTRACT_EVALUATION_SEMANTIC=observe)
            set_target_properties(lorica_contracts_observe_cxx${standard} PROPERTIES
                CXX_STANDARD ${standard} CXX_STANDARD_REQUIRED ON CXX_EXTENSIONS OFF)
            lorica_harden_target(lorica_contracts_observe_cxx${standard})
            add_test(NAME lorica.contracts.observe.cxx${standard}
                COMMAND lorica_contracts_observe_cxx${standard})
        endif()
    endforeach()
    add_executable(lorica_contracts_ignore tests/contracts_ignore.cpp)
    target_link_libraries(lorica_contracts_ignore PRIVATE Lorica::contracts)
    target_compile_definitions(lorica_contracts_ignore PRIVATE LORICA_CONTRACT_EVALUATION_SEMANTIC=ignore)
    lorica_harden_target(lorica_contracts_ignore)
    add_test(NAME lorica.contracts.ignore COMMAND lorica_contracts_ignore)
    set(lorica_contract_variants enforce quick_enforce)
    if(NOT MSVC)
        list(APPEND lorica_contract_variants enforce_noexceptions)
    endif()
    foreach(variant IN LISTS lorica_contract_variants)
        string(REPLACE "_noexceptions" "" semantic "${variant}")
        add_executable(lorica_contracts_${variant} tests/contracts_termination.cpp)
        target_link_libraries(lorica_contracts_${variant} PRIVATE Lorica::contracts)
        target_compile_definitions(lorica_contracts_${variant} PRIVATE
            LORICA_CONTRACT_EVALUATION_SEMANTIC=${semantic})
        if(variant MATCHES "_noexceptions$")
            target_compile_options(lorica_contracts_${variant} PRIVATE -fno-exceptions)
        endif()
        lorica_harden_target(lorica_contracts_${variant})
        add_test(NAME lorica.contracts.${variant}
            COMMAND ${Python3_EXECUTABLE} ${CMAKE_CURRENT_SOURCE_DIR}/tests/contract_termination.py
                $<TARGET_FILE:lorica_contracts_${variant}> ${semantic})
    endforeach()
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
    INSTALL_DESTINATION ${CMAKE_INSTALL_LIBDIR}/cmake/Lorica)
write_basic_package_version_file(${CMAKE_CURRENT_BINARY_DIR}/LoricaConfigVersion.cmake
    VERSION ${PROJECT_VERSION} COMPATIBILITY SameMajorVersion)
install(FILES ${CMAKE_CURRENT_BINARY_DIR}/LoricaConfig.cmake
    ${CMAKE_CURRENT_BINARY_DIR}/LoricaConfigVersion.cmake
    cmake/LoricaHardening.cmake cmake/LoricaInject.cmake
    DESTINATION ${CMAKE_INSTALL_LIBDIR}/cmake/Lorica)
