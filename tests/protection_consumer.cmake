# SPEC-LR-VERIFY: an independent project links the installed Lorica::protection
# (SPEC-LR-SEALED acceptance). Installs the build tree to a scratch prefix, then
# configures examples/consumer against it through CMAKE_PREFIX_PATH and the
# installed LoricaInject.cmake, builds and runs it; judged by exit status and by
# which package was found. Then builds examples/contracts against the same prefix
# (Lorica::contracts) and runs its tests. Run with cmake -P:
#   -DBUILD_DIR=<Lorica build tree> -DSOURCE_DIR=<examples/consumer>
#   -DCONTRACTS_SOURCE_DIR=<examples/contracts> -DWORK_DIR=<scratch>
#   -DLIBDIR=<CMAKE_INSTALL_LIBDIR> -DGENERATOR=<generator> -DCXX_COMPILER=<compiler>
#   [-DCXX_FLAGS=<flags the library was built with>] [-DCONFIG=<configuration>]
foreach(variable BUILD_DIR SOURCE_DIR CONTRACTS_SOURCE_DIR WORK_DIR LIBDIR GENERATOR CXX_COMPILER)
    if(NOT ${variable})
        message(FATAL_ERROR "protection_consumer: ${variable} is required")
    endif()
endforeach()
# An empty configuration installs its own files; the consumers then build Release.
set(install_config)
if(CONFIG)
    set(install_config --config "${CONFIG}")
else()
    set(CONFIG Release)
endif()
# An empty $<CONFIG> leaves a trailing slash; the cache holds the normalized path.
get_filename_component(WORK_DIR "${WORK_DIR}" ABSOLUTE)
string(TOUPPER "${CONFIG}" config_upper)
set(prefix "${WORK_DIR}/prefix")
set(bin "${WORK_DIR}/bin")
file(REMOVE_RECURSE "${WORK_DIR}")
function(lorica_step name)
    execute_process(COMMAND ${ARGN} RESULT_VARIABLE result OUTPUT_VARIABLE output ERROR_VARIABLE output)
    if(NOT result EQUAL 0)
        message(FATAL_ERROR "${name} failed (${result}):\n${output}")
    endif()
endfunction()
lorica_step(install "${CMAKE_COMMAND}" --install "${BUILD_DIR}" ${install_config} --prefix "${prefix}")
# A per-configuration output directory gets no configuration subdirectory, so the
# program is in the same place under single- and multi-config generators.
lorica_step(configure "${CMAKE_COMMAND}" -S "${SOURCE_DIR}" -B "${WORK_DIR}/build" -G "${GENERATOR}"
    "-DCMAKE_CXX_COMPILER=${CXX_COMPILER}" "-DCMAKE_CXX_FLAGS=${CXX_FLAGS}" "-DCMAKE_BUILD_TYPE=${CONFIG}"
    "-DCMAKE_PREFIX_PATH=${prefix}" -DLORICA_TARGETS=lorica_consumer
    "-DCMAKE_PROJECT_TOP_LEVEL_INCLUDES=${prefix}/${LIBDIR}/cmake/Lorica/LoricaInject.cmake"
    "-DCMAKE_RUNTIME_OUTPUT_DIRECTORY_${config_upper}=${bin}")
file(STRINGS "${WORK_DIR}/build/CMakeCache.txt" found REGEX "^Lorica_DIR:")
if(NOT found STREQUAL "Lorica_DIR:PATH=${prefix}/${LIBDIR}/cmake/Lorica")
    message(FATAL_ERROR "the consumer did not find the installed package: ${found}")
endif()
lorica_step(build "${CMAKE_COMMAND}" --build "${WORK_DIR}/build" --config "${CONFIG}")
set(suffix)
if(CMAKE_HOST_WIN32)
    set(suffix .exe)
endif()
lorica_step(run "${bin}/lorica_consumer${suffix}")
lorica_step(configure_contracts "${CMAKE_COMMAND}" -S "${CONTRACTS_SOURCE_DIR}" -B "${WORK_DIR}/contracts"
    -G "${GENERATOR}" "-DCMAKE_CXX_COMPILER=${CXX_COMPILER}" "-DCMAKE_CXX_FLAGS=${CXX_FLAGS}"
    "-DCMAKE_BUILD_TYPE=${CONFIG}" "-DCMAKE_PREFIX_PATH=${prefix}")
lorica_step(build_contracts "${CMAKE_COMMAND}" --build "${WORK_DIR}/contracts" --config "${CONFIG}")
lorica_step(test_contracts "${CMAKE_CTEST_COMMAND}" --test-dir "${WORK_DIR}/contracts" -C "${CONFIG}"
    --output-on-failure --no-tests=error)
