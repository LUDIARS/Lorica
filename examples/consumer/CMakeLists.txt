cmake_minimum_required(VERSION 3.24)
project(LoricaConsumer LANGUAGES CXX)
find_package(Lorica 0.1 CONFIG REQUIRED)
add_executable(lorica_consumer main.cpp)
target_link_libraries(lorica_consumer PRIVATE Lorica::boundary)
# Build protection is supplied externally by LoricaInject.cmake in this example.
