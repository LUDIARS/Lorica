include_guard(GLOBAL)
include("${CMAKE_CURRENT_LIST_DIR}/LoricaHardening.cmake")

# lorica_set_contract_semantic(<target> <ignore|observe|enforce|quick_enforce>)
# (LR-CONTRACT-11) Selects the evaluation semantic of every contract in the target's
# own sources, in-body macros and overlays alike, from the build instead of the
# code: ignore strips them, and the same sources are checked again with another
# value. It replaces a LORICA_CONTRACT_EVALUATION_SEMANTIC definition the target
# already has. A target has one semantic; targets that share inline or template
# code with contracts need the same one (P2900 mixed mode otherwise).
function(lorica_set_contract_semantic target semantic)
    _lorica_require_compiled_target("${target}")
    if(NOT semantic MATCHES "^(ignore|observe|enforce|quick_enforce)$")
        message(FATAL_ERROR "Lorica: the contract semantic must be ignore, observe, enforce or quick_enforce, not '${semantic}'")
    endif()
    # Compared as quoted strings: if() reads the value "ignore" as false, and an
    # unset property leaves the variable undefined.
    get_property(current TARGET "${target}" PROPERTY LORICA_CONTRACT_SEMANTIC)
    if("${current}" STREQUAL "${semantic}")
        return()
    elseif(NOT "${current}" STREQUAL "")
        message(FATAL_ERROR "Lorica: ${target} already has the contract semantic ${current}; ${semantic} would give it two")
    endif()
    if(MSVC)
        # The later of two /D definitions wins (command-line warning D9025).
        target_compile_definitions("${target}" PRIVATE
            "$<$<COMPILE_LANGUAGE:CXX>:LORICA_CONTRACT_EVALUATION_SEMANTIC=${semantic}>")
    else()
        # Options follow the target's definitions, so this pair replaces one of them.
        target_compile_options("${target}" PRIVATE
            "$<$<COMPILE_LANGUAGE:CXX>:SHELL:-ULORICA_CONTRACT_EVALUATION_SEMANTIC -DLORICA_CONTRACT_EVALUATION_SEMANTIC=${semantic}>")
    endif()
    set_property(TARGET "${target}" PROPERTY LORICA_CONTRACT_SEMANTIC "${semantic}")
endfunction()
