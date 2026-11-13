cmake_minimum_required(VERSION 3.24)
# Standalone against an installed Lorica, or as part of Lorica's own build.
if(CMAKE_SOURCE_DIR STREQUAL CMAKE_CURRENT_SOURCE_DIR)
    project(LoricaPackingExample LANGUAGES CXX)
    find_package(Lorica 0.1 CONFIG REQUIRED)
    enable_testing()
endif()

add_executable(lorica_example_packing main.cpp)
target_link_libraries(lorica_example_packing PRIVATE Lorica::protection)
lorica_harden_target(lorica_example_packing)
# A smoke run: only the checksums are judged, never a time.
add_test(NAME lorica.demo.packing COMMAND lorica_example_packing)
set_tests_properties(lorica.demo.packing PROPERTIES PASS_REGULAR_EXPRESSION "checksums match")
