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
else()
    # Its headers would compile and then fail to link without the library.
    set(lorica_header_excludes PATTERN sealed_value.hpp EXCLUDE PATTERN sealed_pack.hpp EXCLUDE
        PATTERN sealed_region.hpp EXCLUDE)
endif()

# The runtime is hardened, so it needs a supported hardening toolchain/platform;
# OFF leaves the header-only parts usable elsewhere.
option(LORICA_BUILD_CONTRACTS "Build the contracts runtime (Lorica::contracts)" ON)
if(LORICA_BUILD_CONTRACTS)
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
else()
    list(APPEND lorica_header_excludes PATTERN contracts.hpp EXCLUDE PATTERN contract_overlay.hpp EXCLUDE
        PATTERN contract_violation.hpp EXCLUDE)
endif()

option(LORICA_BUILD_TESTS "Build boundary contract tests" OFF)
option(LORICA_BUILD_FUZZER "Build Clang libFuzzer target (test use only)" OFF)
option(LORICA_TEST_REQUIRE_EXTENDED "Fail configuration when the extended-profile tests cannot run" OFF)
if(LORICA_BUILD_TESTS)
    if(NOT LORICA_BUILD_CONTRACTS)
        message(FATAL_ERROR "Lorica: LORICA_BUILD_TESTS requires LORICA_BUILD_CONTRACTS")
    endif()
    enable_testing()
    find_package(Python3 REQUIRED COMPONENTS Interpreter)
    # A check the toolchain cannot run is registered disabled: CTest reports it as
    # not run, never as passed.
    function(lorica_add_disabled_test name)
        add_test(NAME "${name}" COMMAND "${CMAKE_COMMAND}" -E false)
        set_tests_properties("${name}" PROPERTIES DISABLED TRUE)
    endfunction()
    # Small projects that must be refused, or applied, by Lorica's build functions.
    function(lorica_add_build_refusals name group)
        add_test(NAME "${name}" COMMAND "${CMAKE_COMMAND}" "-DLORICA_CMAKE_DIR=${PROJECT_SOURCE_DIR}/cmake"
            "-DWORK_DIR=${PROJECT_BINARY_DIR}/build_refusals" "-DGENERATOR=${CMAKE_GENERATOR}"
            "-DCXX_COMPILER=${CMAKE_CXX_COMPILER}" "-DGROUP=${group}" "-DMSVC_TOOLCHAIN=${MSVC}" ${ARGN}
            -P "${PROJECT_SOURCE_DIR}/tests/build_refusals.cmake")
    endfunction()
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
    if(LORICA_TEST_REQUIRE_EXTENDED AND NOT lorica_extended)
        message(FATAL_ERROR "Lorica: the extended-profile tests are required but cannot run: ${lorica_extended_REASON}")
    endif()
    # Native generators with a compilation database can check the actual C/C++
    # command lines. Fault-injection cases require an otherwise capable host.
    if(CMAKE_SYSTEM_NAME STREQUAL "Linux" AND NOT CMAKE_CROSSCOMPILING AND
       CMAKE_GENERATOR MATCHES "^(Ninja|Ninja Multi-Config|Unix Makefiles)$")
        # harness_control injects nothing, so the harness must report the strict
        # configuration that succeeded.
        foreach(case normal missing_flag older_libc unoptimized unknown_cpu old_compiler abi32
                     no_stdlib no_autoinit harness_control)
            add_test(NAME lorica.profiles.${case} COMMAND "${Python3_EXECUTABLE}"
                "${CMAKE_CURRENT_SOURCE_DIR}/tests/profiles/check.py" "${CMAKE_COMMAND}"
                "${CMAKE_CURRENT_BINARY_DIR}/profiles/$<CONFIG>" "${CMAKE_GENERATOR}"
                "${CMAKE_CXX_COMPILER}" "${CMAKE_CXX_FLAGS}" "${case}")
            set_tests_properties(lorica.profiles.${case} PROPERTIES SKIP_RETURN_CODE 77)
            if(NOT lorica_extended AND NOT case STREQUAL "normal")
                set_tests_properties(lorica.profiles.${case} PROPERTIES DISABLED TRUE)
            endif()
        endforeach()
        set_tests_properties(lorica.profiles.harness_control PROPERTIES
            PASS_REGULAR_EXPRESSION "configuration unexpectedly succeeded")
    endif()
    lorica_unsafe_api_rejection_supported(lorica_unsafe_api)
    lorica_add_build_refusals(lorica.build_refusals build
        "-DEXTENDED=${lorica_extended}" "-DUNSAFE=${lorica_unsafe_api}")
    lorica_add_build_refusals(lorica.build_refusals.harness_control harness_control)
    set_tests_properties(lorica.build_refusals.harness_control PROPERTIES
        PASS_REGULAR_EXPRESSION "accepted was accepted")
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
        if(CMAKE_CXX_FLAGS MATCHES "-fsanitize=[^ ]*address")
            # AddressSanitizer reports the overflowing copy before glibc's check can.
            message(STATUS "Lorica: lorica.hardening_stops does not check the FORTIFY stop under AddressSanitizer")
            set(lorica_fortified 0)
        endif()
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
        lorica_add_disabled_test(lorica.hardening_stops)
    endif()
    if(NOT WIN32)
        # Control: the harness must reject a child that exits with an error instead
        # of being stopped.
        set(child "${CMAKE_CURRENT_BINARY_DIR}/hardening_control/child")
        file(WRITE "${child}" "#!/bin/sh\n[ $# -eq 0 ]\n")
        file(CHMOD "${child}" PERMISSIONS OWNER_READ OWNER_WRITE OWNER_EXECUTE)
        add_test(NAME lorica.hardening_stops.harness_control
            COMMAND ${Python3_EXECUTABLE} ${CMAKE_CURRENT_SOURCE_DIR}/tests/hardening_fault.py "${child}" unfortified)
        set_tests_properties(lorica.hardening_stops.harness_control PROPERTIES
            PASS_REGULAR_EXPRESSION "--element was not stopped by the extended profile \\(exit 1\\)")
    endif()
    # Lorica's own libraries and the tests that rely on a profile carry it; the
    # options each profile gives are checked by lorica.profiles.*.
    set(lorica_profile baseline)
    if(lorica_extended)
        set(lorica_profile extended)
    endif()
    set(lorica_applied lorica_contracts)
    set(lorica_applied_expected "lorica_contracts=baseline,")
    if(LORICA_BUILD_PROTECTION)
        list(APPEND lorica_applied lorica_protection)
        string(APPEND lorica_applied_expected " lorica_protection=baseline,")
    endif()
    foreach(standard 20 23)
        list(APPEND lorica_applied lorica_checked_tests_cxx${standard})
        string(APPEND lorica_applied_expected " lorica_checked_tests_cxx${standard}=${lorica_profile},")
        if(lorica_unsafe_api)
            string(APPEND lorica_applied_expected "TRUE")
        endif()
    endforeach()
    if(lorica_extended)
        list(APPEND lorica_applied lorica_hardening_tests)
        string(APPEND lorica_applied_expected " lorica_hardening_tests=extended,")
    endif()
    list(TRANSFORM lorica_applied REPLACE "^(.+)$"
        "\\1=$<TARGET_PROPERTY:\\1,LORICA_HARDENING_PROFILE>,$<TARGET_PROPERTY:\\1,LORICA_UNSAFE_APIS_DEPRECATED>")
    list(JOIN lorica_applied " " lorica_applied)
    add_test(NAME lorica.hardening_applied COMMAND "${CMAKE_COMMAND}" -E echo "[${lorica_applied}]")
    set_tests_properties(lorica.hardening_applied PROPERTIES PASS_REGULAR_EXPRESSION "\\[${lorica_applied_expected}\\]")
    include(tests/verify_binary.cmake)
    lorica_add_verifier_tests()
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
    # Headers only: an ignored contract must not need the runtime library.
    target_link_libraries(lorica_contracts_ignore PRIVATE Lorica::boundary)
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
        set(harness_exceptions exceptions)
        if(variant MATCHES "_noexceptions$")
            set(harness_exceptions)
        endif()
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
                    $<TARGET_FILE:${target}> ${semantic} ${harness_form} ${harness_exceptions})
        endforeach()
    endforeach()
    # What must not compile: built by its test only.
    foreach(case IN ITEMS "condition_arity:1:ignore:a precondition is not callable"
                          "message_argument:2:enforce:holds"
                          "unknown_semantic:3:strict:strict")
        string(REPLACE ":" ";" case "${case}")
        list(GET case 0 name)
        list(GET case 1 number)
        list(GET case 2 semantic)
        list(GET case 3 diagnostic)
        add_executable(lorica_probe_contract_${name} EXCLUDE_FROM_ALL tests/contracts_rejected.cpp)
        target_link_libraries(lorica_probe_contract_${name} PRIVATE Lorica::contracts)
        target_compile_definitions(lorica_probe_contract_${name} PRIVATE
            LORICA_TEST_REJECT=${number} LORICA_CONTRACT_EVALUATION_SEMANTIC=${semantic})
        add_test(NAME lorica.contracts.rejected.${name} COMMAND "${CMAKE_COMMAND}"
            "-DBUILD_DIR=${CMAKE_BINARY_DIR}" "-DTARGET=lorica_probe_contract_${name}" "-DCONFIG=$<CONFIG>"
            "-DEXPECT=reject" "-DDIAGNOSTIC=${diagnostic}"
            -P "${CMAKE_CURRENT_SOURCE_DIR}/tests/run_build_probe.cmake")
        set_tests_properties(lorica.contracts.rejected.${name} PROPERTIES RESOURCE_LOCK lorica_build_tree)
    endforeach()
    # The semantic chosen from the build, by function and by injection, over
    # sources that never change.
    add_test(NAME lorica.contracts.semantic_switch COMMAND "${CMAKE_COMMAND}"
        "-DLORICA_SOURCE_DIR=${CMAKE_CURRENT_SOURCE_DIR}"
        "-DWORK_DIR=${CMAKE_CURRENT_BINARY_DIR}/contract_semantic_switch/$<CONFIG>"
        "-DGENERATOR=${CMAKE_GENERATOR}" "-DCXX_COMPILER=${CMAKE_CXX_COMPILER}" "-DCONFIG=$<CONFIG>"
        -P "${CMAKE_CURRENT_SOURCE_DIR}/tests/contract_semantic_switch.cmake")
    # LR-BUILD-02: what the injection that carries the semantic applies, and refuses.
    add_test(NAME lorica.inject COMMAND "${CMAKE_COMMAND}"
        "-DLORICA_CMAKE_DIR=${CMAKE_CURRENT_SOURCE_DIR}/cmake"
        "-DWORK_DIR=${CMAKE_CURRENT_BINARY_DIR}/inject/$<CONFIG>"
        "-DGENERATOR=${CMAKE_GENERATOR}" "-DCXX_COMPILER=${CMAKE_CXX_COMPILER}"
        "-DEXTENDED=${lorica_extended}" "-DUNSAFE_API=${lorica_unsafe_api}"
        -P "${CMAKE_CURRENT_SOURCE_DIR}/tests/inject_refusals.cmake")
    if(LORICA_BUILD_PROTECTION)
        find_package(Threads REQUIRED)
        add_executable(lorica_protection_tests tests/protection.cpp)
        target_link_libraries(lorica_protection_tests PRIVATE Lorica::protection Threads::Threads)
        lorica_harden_target(lorica_protection_tests)
        add_test(NAME lorica.protection COMMAND lorica_protection_tests)
        add_test(NAME lorica.protection_write_denied
            COMMAND ${Python3_EXECUTABLE} ${CMAKE_CURRENT_SOURCE_DIR}/tests/protection_fault.py
                $<TARGET_FILE:lorica_protection_tests> --write)
        if(NOT WIN32)
            # Control: the harness must reject a fault the child does not attribute to the sealed byte.
            add_test(NAME lorica.protection_write_misdirected
                COMMAND ${Python3_EXECUTABLE} ${CMAKE_CURRENT_SOURCE_DIR}/tests/protection_fault.py
                    $<TARGET_FILE:lorica_protection_tests> --misdirected)
            set_tests_properties(lorica.protection_write_misdirected PROPERTIES
                PASS_REGULAR_EXPRESSION "Expected write protection fault -11, got 5")
        endif()
        if(CMAKE_SYSTEM_NAME STREQUAL "Linux")
            # The linker routes the library's mmap/mprotect/munmap calls through the test.
            add_executable(lorica_protection_linux_tests tests/protection_linux.cpp)
            target_link_libraries(lorica_protection_linux_tests PRIVATE Lorica::protection)
            target_link_options(lorica_protection_linux_tests PRIVATE
                -Wl,--wrap=mmap,--wrap=mprotect,--wrap=munmap)
            lorica_harden_target(lorica_protection_linux_tests)
            add_test(NAME lorica.protection_linux COMMAND lorica_protection_linux_tests)
        endif()
        # Types sealed_value must refuse, constructed without calling load().
        set(lorica_sealed_pointer "int*")
        set(lorica_sealed_structure "pod")
        set(lorica_sealed_qualified "const int")
        foreach(probe IN ITEMS pointer structure qualified)
            set(type "${lorica_sealed_${probe}}")
            file(CONFIGURE OUTPUT "${CMAKE_CURRENT_BINARY_DIR}/sealed_probes/${probe}.cpp" CONTENT [=[
#include <lorica/sealed_value.hpp>
struct pod { int value; };
int main() { const lorica::sealed_value<@type@> value{{}}; return 0; }
]=] @ONLY)
            add_executable(lorica_probe_sealed_${probe} EXCLUDE_FROM_ALL
                "${CMAKE_CURRENT_BINARY_DIR}/sealed_probes/${probe}.cpp")
            target_link_libraries(lorica_probe_sealed_${probe} PRIVATE Lorica::protection)
            add_test(NAME lorica.protection.rejects_${probe} COMMAND "${CMAKE_COMMAND}"
                "-DBUILD_DIR=${CMAKE_BINARY_DIR}" "-DTARGET=lorica_probe_sealed_${probe}" "-DCONFIG=$<CONFIG>"
                "-DEXPECT=reject" "-DDIAGNOSTIC=sealed_value requires an unqualified arithmetic or enum type"
                -P "${CMAKE_CURRENT_SOURCE_DIR}/tests/run_build_probe.cmake")
            set_tests_properties(lorica.protection.rejects_${probe} PROPERTIES RESOURCE_LOCK lorica_build_tree)
        endforeach()
        # The installed package, found and injected by independent projects.
        add_test(NAME lorica.protection_consumer COMMAND "${CMAKE_COMMAND}"
            "-DBUILD_DIR=${CMAKE_CURRENT_BINARY_DIR}" "-DSOURCE_DIR=${CMAKE_CURRENT_SOURCE_DIR}/examples/consumer"
            "-DCONTRACTS_SOURCE_DIR=${CMAKE_CURRENT_SOURCE_DIR}/examples/contracts"
            "-DWORK_DIR=${CMAKE_CURRENT_BINARY_DIR}/protection_consumer/$<CONFIG>"
            "-DLIBDIR=${CMAKE_INSTALL_LIBDIR}" "-DGENERATOR=${CMAKE_GENERATOR}"
            "-DCXX_COMPILER=${CMAKE_CXX_COMPILER}" "-DCXX_FLAGS=${CMAKE_CXX_FLAGS}" "-DCONFIG=$<CONFIG>"
            -P "${CMAKE_CURRENT_SOURCE_DIR}/tests/protection_consumer.cmake")
        set_tests_properties(lorica.protection_consumer PROPERTIES RESOURCE_LOCK lorica_build_tree)
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
    if(LORICA_BUILD_CONTRACTS)
        add_subdirectory(examples/contracts)
    endif()
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
install(DIRECTORY include/ DESTINATION ${CMAKE_INSTALL_INCLUDEDIR} ${lorica_header_excludes})
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
