// SPEC-LR-CXX23: a target that asks for C++<LORICA_TEST_STANDARD> must compile in
// that ISO standard, not in a newer draft mode. C++23 accepts 202100L (GCC 11-13
// -std=c++2b) up to, but not including, 202400L, which MSVC's /std:c++latest reports
// once C++26 draft features are enabled. MSVC keeps __cplusplus at 199711L without
// /Zc:__cplusplus, so _MSVC_LANG is read there.
#include <cstdio>

#ifndef LORICA_TEST_STANDARD
#error "tests/standard.cpp requires LORICA_TEST_STANDARD (17, 20 or 23)"
#endif

#if defined(_MSVC_LANG)
#define LORICA_TEST_LANGUAGE _MSVC_LANG
#else
#define LORICA_TEST_LANGUAGE __cplusplus
#endif

namespace {
struct version_range {
    long first;
    long end;
};

// @implements SPEC-LR-VERIFY
constexpr version_range accepted(int standard) {
    switch (standard) {
    case 17: return {201703L, 202002L};
    case 20: return {202002L, 202100L};
    case 23: return {202100L, 202400L};
    default: return {0L, 0L};
    }
}
} // namespace

// @implements SPEC-LR-VERIFY
int main() {
    const long language = static_cast<long>(LORICA_TEST_LANGUAGE);
    const version_range range = accepted(LORICA_TEST_STANDARD);
    std::printf("C++%d requested: language version %ld, accepted [%ld, %ld)\n",
                LORICA_TEST_STANDARD, language, range.first, range.end);
    return range.first <= language && language < range.end ? 0 : 1;
}
