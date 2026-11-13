cmake_minimum_required(VERSION 3.24)
# Standalone against an installed Lorica, or as part of Lorica's own build.
if(CMAKE_SOURCE_DIR STREQUAL CMAKE_CURRENT_SOURCE_DIR)
    project(LoricaContractOverlayExample LANGUAGES CXX)
    find_package(Lorica 0.1 CONFIG REQUIRED)
    enable_testing()
endif()

# The same source with the contract enforced and with it stripped: both runs
# print the same lines and report every outcome as expected.
foreach(semantic IN ITEMS enforce ignore)
    set(target lorica_example_contracts_${semantic})
    add_executable(${target} main.cpp)
    target_link_libraries(${target} PRIVATE Lorica::contracts)
    target_compile_definitions(${target} PRIVATE LORICA_CONTRACT_EVALUATION_SEMANTIC=${semantic})
    lorica_harden_target(${target})
    add_test(NAME lorica.demo.contracts.${semantic} COMMAND ${target})
    set_tests_properties(lorica.demo.contracts.${semantic} PROPERTIES
        PASS_REGULAR_EXPRESSION "every outcome as expected")
    if(WIN32)
        set_tests_properties(lorica.demo.contracts.${semantic} PROPERTIES ENVIRONMENT_MODIFICATION
            "PATH=path_list_prepend:$<TARGET_FILE_DIR:Lorica::contracts>")
    endif()
endforeach()
