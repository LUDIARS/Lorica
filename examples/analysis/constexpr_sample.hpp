// Stands for a consumer's header: none of these functions is declared constexpr.
#pragma once
#include <cstdint>
#include <ctime>

// Convertible: a witness constant-evaluates it.
inline int scaled(int value, int factor) { return value * factor; }

// Accepted by GCC, never constant: its witness does not compile.
inline std::uintptr_t address_of(const int* pointer) { return reinterpret_cast<std::uintptr_t>(pointer); }

// Rejected in C++17 (try in a constexpr function), accepted in C++20.
inline int checked_divide(int dividend, int divisor) {
    try {
        return divisor == 0 ? 0 : dividend / divisor;
    } catch (...) {
        return 0;
    }
}

// Rejected: calls a function that is not constexpr.
inline long now_seconds() { return static_cast<long>(std::time(nullptr)); }

// Hidden: every compiler accepts the specifier on a template.
template <class T>
T twice(T value) { return value + value; }
