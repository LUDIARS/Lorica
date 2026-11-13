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
include(cmake/LoricaContracts.cmake)

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
    find_package(Python3 REQUIRED COMPONENTS Interpreter)
    add_executable(lorica_boundary_tests tests/boundary.cpp)
    target_link_libraries(lorica_boundary_tests PRIVATE Lorica::boundary)
    set_target_properties(lorica_boundary_tests PROPERTIES
        CXX_STANDARD 17 CXX_STANDARD_REQUIRED ON CXX_EXTENSIONS OFF)
    lorica_harden_target(lorica_boundary_tests)
    add_test(NAME lorica.boundary COMMAND lorica_boundary_tests)
    # The C++20 headers, as C++20 and as C++23, under the extended profile and with
    # the unbounded C APIs rejected, where the toolchain offers each. Checks the
    # toolchain cannot run are reported as not run, never as passed.
    lorica_extended_hardening_supported(lorica_extended)
    # Native generators with a compilation database can check the actual C/C++
    # command lines. Fault-injection cases require an otherwise capable host.
    if(CMAKE_SYSTEM_NAME STREQUAL "Linux" AND NOT CMAKE_CROSSCOMPILING AND
       CMAKE_GENERATOR MATCHES "^(Ninja|Ninja Multi-Config|Unix Makefiles)$")
        foreach(case normal missing_flag older_libc unoptimized unknown_cpu)
            add_test(NAME lorica.profiles.${case} COMMAND "${Python3_EXECUTABLE}"
                "${CMAKE_CURRENT_SOURCE_DIR}/tests/profiles/check.py" "${CMAKE_COMMAND}"
                "${CMAKE_CURRENT_BINARY_DIR}/profiles/$<CONFIG>" "${CMAKE_GENERATOR}"
                "${CMAKE_CXX_COMPILER}" "${CMAKE_CXX_FLAGS}" "${case}")
            set_tests_properties(lorica.profiles.${case} PROPERTIES SKIP_RETURN_CODE 77)
            if(NOT lorica_extended AND NOT case STREQUAL "normal")
                set_tests_properties(lorica.profiles.${case} PROPERTIES DISABLED TRUE)
            endif()
        endforeach()
    endif()
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
        # The format checks by name: skipped (77) where the library lacks <format>.
        add_test(NAME lorica.checked.format.cxx${standard} COMMAND lorica_checked_tests_cxx${standard} format)
        set_tests_properties(lorica.checked.format.cxx${standard} PROPERTIES SKIP_RETURN_CODE 77)
    endforeach()
    # LR-TEXT-02: a run-time format string must not compile (CWE-134). Without
    # <format> the probe stops with its own message and the test is skipped.
    file(CONFIGURE OUTPUT "${CMAKE_CURRENT_BINARY_DIR}/format_probes/runtime_format.cpp" CONTENT [=[
#include <lorica/bounded_text.hpp>
#include <string>
#if !defined(__cpp_lib_format)
#error "Lorica format probe skipped: no __cpp_lib_format"
#endif
int main(int, char** argv) {
    char out[16];
    const std::string format = argv[0];
    return lorica::format_into(out, format, 1).has_value();
}
]=] @ONLY)
    add_executable(lorica_probe_runtime_format EXCLUDE_FROM_ALL
        "${CMAKE_CURRENT_BINARY_DIR}/format_probes/runtime_format.cpp")
    target_link_libraries(lorica_probe_runtime_format PRIVATE Lorica::boundary)
    target_compile_features(lorica_probe_runtime_format PRIVATE cxx_std_20)
    add_test(NAME lorica.checked.runtime_format COMMAND "${CMAKE_COMMAND}" "-DBUILD_DIR=${CMAKE_BINARY_DIR}"
        "-DTARGET=lorica_probe_runtime_format" "-DCONFIG=$<CONFIG>" "-DEXPECT=reject"
        "-DDIAGNOSTIC=constant expression" -P "${CMAKE_CURRENT_SOURCE_DIR}/tests/run_build_probe.cmake")
    set_tests_properties(lorica.checked.runtime_format PROPERTIES RESOURCE_LOCK lorica_build_tree
        SKIP_REGULAR_EXPRESSION "Lorica format probe skipped")
    if(lorica_extended)
        set(lorica_fortified "$<AND:$<CONFIG:Release,RelWithDebInfo,MinSizeRel>,$<NOT:$<BOOL:${WIN32}>>>")
        add_executable(lorica_hardening_tests tests/hardening.cpp)
        target_compile_features(lorica_hardening_tests PRIVATE cxx_std_17)
        target_compile_definitions(lorica_hardening_tests PRIVATE
            "$<${lorica_fortified}:LORICA_TEST_EXPECT_FORTIFY=3>")
        lorica_harden_target(lorica_hardening_tests)
        lorica_harden_target(lorica_hardening_tests EXTENDED)
        lorica_harden_target(lorica_hardening_tests)
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

    add_subdirectory(tests/contract_modules)
    add_subdirectory(tests/analysis)

    # Contracts: the in-body macros (observe) and the overlay, both under observe at
    # each supported standard; ignore; then termination in children.
    foreach(standard IN ITEMS 17 20 23)
        if(standard IN_LIST CMAKE_CXX_COMPILE_FEATURES OR "cxx_std_${standard}" IN_LIST CMAKE_CXX_COMPILE_FEATURES)
            foreach(suite IN ITEMS observe overlay)
                set(target lorica_contracts_${suite}_cxx${standard})
                add_executable(${target} tests/contracts_${suite}.cpp)
                target_link_libraries(${target} PRIVATE Lorica::contracts)
                target_compile_definitions(${target} PRIVATE
                    LORICA_CONTRACT_EVALUATION_SEMANTIC=observe)
                set_target_properties(${target} PROPERTIES
                    CXX_STANDARD ${standard} CXX_STANDARD_REQUIRED ON CXX_EXTENSIONS OFF)
                lorica_harden_target(${target})
                add_test(NAME lorica.contracts.${suite}.cxx${standard} COMMAND ${target})
            endforeach()
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
    # Each variant as in-body macros and as an overlay: the outcomes must not differ.
    foreach(variant IN LISTS lorica_contract_variants)
        string(REPLACE "_noexceptions" "" semantic "${variant}")
        foreach(form IN ITEMS "" overlay_)
            set(target lorica_contracts_${form}${variant})
            add_executable(${target} tests/contracts_termination.cpp)
            target_link_libraries(${target} PRIVATE Lorica::contracts)
            target_compile_definitions(${target} PRIVATE
                LORICA_CONTRACT_EVALUATION_SEMANTIC=${semantic}
                $<$<BOOL:${form}>:LORICA_TEST_OVERLAY>)
            if(variant MATCHES "_noexceptions$")
                target_compile_options(${target} PRIVATE -fno-exceptions)
            endif()
            lorica_harden_target(${target})
            string(REPLACE "_" "" harness_form "${form}")
            add_test(NAME lorica.contracts.${form}${variant}
                COMMAND ${Python3_EXECUTABLE} ${CMAKE_CURRENT_SOURCE_DIR}/tests/contract_termination.py
                    $<TARGET_FILE:${target}> ${semantic} ${harness_form})
        endforeach()
    endforeach()
    # The semantic chosen from the build, by function and by injection, over
    # sources that never change.
    add_test(NAME lorica.contracts.semantic_switch COMMAND "${CMAKE_COMMAND}"
        "-DLORICA_SOURCE_DIR=${CMAKE_CURRENT_SOURCE_DIR}"
        "-DWORK_DIR=${CMAKE_CURRENT_BINARY_DIR}/contract_semantic_switch/$<CONFIG>"
        "-DGENERATOR=${CMAKE_GENERATOR}" "-DCXX_COMPILER=${CMAKE_CXX_COMPILER}" "-DCONFIG=$<CONFIG>"
        -P "${CMAKE_CURRENT_SOURCE_DIR}/tests/contract_semantic_switch.cmake")
    if(LORICA_BUILD_PROTECTION)
        add_executable(lorica_protection_tests tests/protection.cpp)
        target_link_libraries(lorica_protection_tests PRIVATE Lorica::protection)
        lorica_harden_target(lorica_protection_tests)
        add_test(NAME lorica.protection COMMAND lorica_protection_tests)
        add_test(NAME lorica.protection_write_denied
            COMMAND ${Python3_EXECUTABLE} ${CMAKE_CURRENT_SOURCE_DIR}/tests/protection_fault.py
                $<TARGET_FILE:lorica_protection_tests>)
        # Sealed packs: the API, then each violation in a child judged from outside.
        foreach(name pack pack_fault)
            add_executable(lorica_${name}_tests tests/${name}.cpp)
            target_link_libraries(lorica_${name}_tests PRIVATE Lorica::protection)
            lorica_harden_target(lorica_${name}_tests)
        endforeach()
        add_test(NAME lorica.pack.unit COMMAND lorica_pack_tests)
        foreach(case IN ITEMS control:exit-0 write_first:access-violation write_last:access-violation
                              load_outside:abort at_outside:abort)
            string(REPLACE ":" ";" case "${case}")
            list(GET case 0 mode)
            list(GET case 1 ending)
            add_test(NAME lorica.pack.stops.${mode}
                COMMAND ${Python3_EXECUTABLE} ${CMAKE_CURRENT_SOURCE_DIR}/tests/pack_fault.py
                    $<TARGET_FILE:lorica_pack_fault_tests> ${mode} ${ending})
        endforeach()
        # Readers without synchronisation can only fail where a race is reported.
        if(CMAKE_CXX_FLAGS MATCHES "-fsanitize=thread")
            find_package(Threads REQUIRED)
            add_executable(lorica_pack_readers_tests tests/pack_readers.cpp)
            target_link_libraries(lorica_pack_readers_tests PRIVATE Lorica::protection Threads::Threads)
            add_test(NAME lorica.pack.readers_tsan COMMAND lorica_pack_readers_tests)
        endif()
    endif()
endif()
# Examples double as demos that cannot rot: with tests enabled they run as
# lorica.demo.* tests.
option(LORICA_BUILD_EXAMPLES "Build the examples (run as lorica.demo.* tests with LORICA_BUILD_TESTS)" OFF)
if(LORICA_BUILD_EXAMPLES)
    add_subdirectory(examples/contracts)
    if(LORICA_BUILD_PROTECTION)
        add_subdirectory(examples/packing)
    endif()
endif()
if(LORICA_BUILD_FUZZER)
    if(NOT CMAKE_CXX_COMPILER_ID STREQUAL "Clang" OR NOT CMAKE_SYSTEM_NAME STREQUAL "Linux")
        message(FATAL_ERROR "Lorica fuzzing currently requires Linux Clang")
    endif()
    add_executable(lorica_boundary_fuzz tests/fuzz_boundary.cpp)
    target_link_libraries(lorica_boundary_fuzz PRIVATE Lorica::boundary)
    target_compile_options(lorica_boundary_fuzz PRIVATE -fsanitize=fuzzer,address,undefined
        -fno-sanitize-recover=all)
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
    cmake/LoricaHardening.cmake cmake/LoricaContracts.cmake cmake/LoricaInject.cmake
    DESTINATION ${CMAKE_INSTALL_LIBDIR}/cmake/Lorica)
