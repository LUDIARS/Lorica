# SPEC-LR-VERIFY: builds one probe target and judges the result by the exit code
# and the compiler output, not by generator-specific text. Run with cmake -P:
#   -DBUILD_DIR=<build tree> -DTARGET=<target> -DCONFIG=<config>
#   -DEXPECT=accept|reject [-DDIAGNOSTIC=<regular expression, required for reject>]
# A rejected probe passes only when the build fails and prints DIAGNOSTIC.
foreach(variable BUILD_DIR TARGET EXPECT)
    if(NOT ${variable})
        message(FATAL_ERROR "run_build_probe: ${variable} is required")
    endif()
endforeach()
set(config_arguments)
if(CONFIG)
    set(config_arguments --config "${CONFIG}")
endif()
execute_process(COMMAND "${CMAKE_COMMAND}" --build "${BUILD_DIR}" --target "${TARGET}" ${config_arguments}
    RESULT_VARIABLE result OUTPUT_VARIABLE output ERROR_VARIABLE output)
if(EXPECT STREQUAL "accept")
    if(NOT result EQUAL 0)
        message(FATAL_ERROR "${TARGET} was rejected:\n${output}")
    endif()
elseif(EXPECT STREQUAL "reject")
    if(NOT DIAGNOSTIC)
        message(FATAL_ERROR "run_build_probe: DIAGNOSTIC is required to reject")
    endif()
    if(result EQUAL 0)
        message(FATAL_ERROR "${TARGET} was built, but must be rejected:\n${output}")
    endif()
    if(NOT output MATCHES "${DIAGNOSTIC}")
        message(FATAL_ERROR "${TARGET} failed without the expected diagnostic (${DIAGNOSTIC}):\n${output}")
    endif()
else()
    message(FATAL_ERROR "run_build_probe: EXPECT must be accept or reject")
endif()
