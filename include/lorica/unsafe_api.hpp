#pragma once
// Build-time rejection of the unbounded C copy and format functions (strcpy,
// strcat, sprintf, vsprintf, wcscpy, wcscat). They are declared deprecated, so a
// build with deprecation warnings as errors rejects every use a text search can
// miss: through a macro, a -D alias, std:: qualification, parentheses or a function
// pointer. lorica_deprecate_unsafe_apis() force-includes this header ahead of the
// unit's own first line and makes the warning an error; see SPEC-LR-UNSAFE-API.
// gets() is absent: C11 and C++14 removed it, so it is not declared at all.
//
// The declarations come before the C library's and use compiler-builtin types only,
// so the library's later declarations, and the inline definitions a fortified build
// (_FORTIFY_SOURCE) adds, are compatible redeclarations that inherit the attribute.
// Included after the C library instead, the attribute would come after those inline
// definitions, where compilers ignore it, so that stops compilation here. So does
// Clang with a fortified glibc 2.40 or newer, whose fortified functions are separate
// overloads (pass_object_size) that would not inherit it. Not covered: compiler
// builtins (__builtin_strcpy, __builtin___sprintf_chk), glibc's __*_chk entry
// points, headers on system include paths and the macros they define, and code
// that switches the warning off (#pragma GCC diagnostic, -Wno-deprecated-declarations).
//
// Windows is left to the UCRT, which already deprecates these functions (C4996). It
// declares some of them dllimport and defines sprintf/vsprintf inline, and an
// attribute added after a definition is ignored. A unit that defines
// _CRT_SECURE_NO_WARNINGS turns the UCRT deprecations off.
// @implements SPEC-LR-UNSAFE-API

#if !defined(__cplusplus)
#error "lorica/unsafe_api.hpp is a C++ header"
#endif

#if !defined(_WIN32)
#if defined(_STRING_H) || defined(_STDIO_H) || defined(_WCHAR_H)
#error "lorica/unsafe_api.hpp must come before any C library header: force-include it first"
#endif
// glibc declares these functions noexcept(true) in C++ (its __THROW), and every
// declaration must carry the same exception specification: a mismatch is an error
// in either order. glibc is recognized by a header only it ships; its features.h
// declares no function, and g++ and clang++ predefine _GNU_SOURCE, so reading it
// first selects nothing the unit would not. musl and the BSD libcs declare none;
// another C library that does makes every unit fail to compile instead of losing
// the check.
#define LORICA_NOTHROW
#if defined(__has_include)
#if __has_include(<gnu/libc-version.h>)
#include <features.h>
#undef LORICA_NOTHROW
#define LORICA_NOTHROW noexcept(true)
// glibc 2.40 and newer set __fortify_use_clang when Clang takes its fortified
// overloads, which a fortified build (__USE_FORTIFY_LEVEL) then declares.
#if defined(__fortify_use_clang) && __fortify_use_clang && defined(__USE_FORTIFY_LEVEL) && __USE_FORTIFY_LEVEL > 0
#error "lorica/unsafe_api.hpp cannot cover glibc 2.40+ fortified Clang overloads; check unsafe APIs in an unfortified build or with GCC"
#endif
#endif
#endif
// An object-like macro (for example -Dsprintf=...) must not rename the API away.
#undef strcpy
#undef strcat
#undef sprintf
#undef vsprintf
#undef wcscpy
#undef wcscat
// Spelled through a macro so that no declaration reads like a call to the API.
#define LORICA_DECLARE_UNSAFE(type, name, parameters, reason) \
    [[deprecated("Lorica: " reason)]] type name parameters LORICA_NOTHROW;
extern "C" {
LORICA_DECLARE_UNSAFE(char*, strcpy, (char* __restrict, const char* __restrict),
                      "unbounded copy; use lorica::copy_string (<lorica/bounded_text.hpp>)")
LORICA_DECLARE_UNSAFE(char*, strcat, (char* __restrict, const char* __restrict),
                      "unbounded concatenation; use lorica::append_string (<lorica/bounded_text.hpp>)")
LORICA_DECLARE_UNSAFE(int, sprintf, (char* __restrict, const char* __restrict, ...),
                      "unbounded format; use std::snprintf or lorica::format_into (<lorica/bounded_text.hpp>)")
LORICA_DECLARE_UNSAFE(int, vsprintf, (char* __restrict, const char* __restrict, __builtin_va_list),
                      "unbounded format; use std::vsnprintf")
LORICA_DECLARE_UNSAFE(wchar_t*, wcscpy, (wchar_t* __restrict, const wchar_t* __restrict),
                      "unbounded copy; use lorica::copy_string (<lorica/bounded_text.hpp>)")
LORICA_DECLARE_UNSAFE(wchar_t*, wcscat, (wchar_t* __restrict, const wchar_t* __restrict),
                      "unbounded concatenation; use lorica::append_string (<lorica/bounded_text.hpp>)")
}
// Clang attaches the attribute to the std:: names only through these re-exports;
// <cstring>, <cstdio> and <cwchar> later repeat them, which is valid.
namespace std {
using ::strcpy;
using ::strcat;
using ::sprintf;
using ::vsprintf;
using ::wcscpy;
using ::wcscat;
}
#undef LORICA_DECLARE_UNSAFE
#undef LORICA_NOTHROW
#endif
