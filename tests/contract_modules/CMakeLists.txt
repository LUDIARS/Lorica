cmake_minimum_required(VERSION 3.24)
if(CMAKE_SOURCE_DIR STREQUAL CMAKE_CURRENT_SOURCE_DIR)
    project(LoricaContractModules LANGUAGES CXX)
    find_package(Lorica CONFIG REQUIRED)
    enable_testing()
    # Probe an installed PR #1 archive with either ELF binding mode.
    option(LORICA_TEST_BIND_LOCAL "Bind ELF calls to definitions in the same test DSO" ON)
    set(LORICA_TEST_HANDLER_STATE shared CACHE STRING "Expected handler state: shared, split or probe")
else()
    set(LORICA_TEST_BIND_LOCAL ON)
    set(LORICA_TEST_HANDLER_STATE shared)
endif()

foreach(side IN ITEMS a b)
    set(target lorica_contract_module_${side})
    add_library(${target} SHARED module.cpp)
    target_link_libraries(${target} PRIVATE Lorica::contracts)
    target_compile_definitions(${target} PRIVATE LORICA_TEST_MODULE=module_${side}
        LORICA_CONTRACT_EVALUATION_SEMANTIC=observe)
    if(CMAKE_SYSTEM_NAME STREQUAL "Linux" AND LORICA_TEST_BIND_LOCAL)
        target_link_options(${target} PRIVATE "LINKER:-Bsymbolic-functions")
    endif()
    lorica_harden_target(${target})
endforeach()

find_package(Threads REQUIRED)
add_executable(lorica_contract_modules main.cpp)
# Only the plugins link Lorica::contracts. A third copy in the driver would
# make it harder to identify which binary owns the handler.
target_link_libraries(lorica_contract_modules PRIVATE
    Threads::Threads Lorica::boundary lorica_contract_module_a lorica_contract_module_b)
lorica_harden_target(lorica_contract_modules)
add_test(NAME lorica.contracts.modules
    COMMAND lorica_contract_modules "${LORICA_TEST_HANDLER_STATE}")
if(WIN32)
    set_tests_properties(lorica.contracts.modules PROPERTIES ENVIRONMENT_MODIFICATION
        "PATH=path_list_prepend:$<TARGET_FILE_DIR:Lorica::contracts>")
endif()
