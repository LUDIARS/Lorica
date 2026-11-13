#pragma once

#if !defined(__cplusplus) || (defined(_MSVC_LANG) ? _MSVC_LANG : __cplusplus) < 202002L
#error "lorica/checked_integer.hpp requires C++20 or newer"
#endif

#include <concepts>
#include <limits>
#include <optional>
#include <type_traits>
#include <utility>

namespace lorica {
// Integer types whose arithmetic is meaningful: bool and the character types are
// excluded because arithmetic on them is almost always a defect (std::in_range and
// the std::cmp_* functions reject them for the same reason).
// @implements SPEC-LR-INTEGER
template<class T>
concept checked_integral = std::integral<T> &&
    !std::same_as<std::remove_cv_t<T>, bool> &&
    !std::same_as<std::remove_cv_t<T>, char> &&
    !std::same_as<std::remove_cv_t<T>, wchar_t> &&
    !std::same_as<std::remove_cv_t<T>, char8_t> &&
    !std::same_as<std::remove_cv_t<T>, char16_t> &&
    !std::same_as<std::remove_cv_t<T>, char32_t>;

// Value-preserving conversion: empty when value is not representable in To. The
// source type is deduced only (int&...), so narrow<unsigned, unsigned>(-1) does
// not compile.
// @implements SPEC-LR-INTEGER
template<checked_integral To, int&..., checked_integral From>
[[nodiscard]] constexpr std::optional<To> narrow(From value) noexcept {
    if (!std::in_range<To>(value)) return std::nullopt;
    return static_cast<To>(value);
}

// Two operands of one checked_integral type, given only by deduction. Explicit
// template arguments are refused by the leading int&... pack (an explicit
// checked_add<std::size_t, std::size_t>(size, -1) would otherwise convert -1
// silently), and
// every other pair of types reaches a deleted overload, which an exact match
// makes better than any converting overload in scope, such as the size_t ones of
// <lorica/checked_size.hpp>. Convert with narrow first.
template<class L, class R>
concept same_checked_integral = checked_integral<L> && std::same_as<L, R>;

#define LORICA_REJECT_MIXED(name) \
    template<int&..., class L, class R> \
        requires(!same_checked_integral<L, R>) \
    void name(L, R) = delete;
LORICA_REJECT_MIXED(checked_add)
LORICA_REJECT_MIXED(checked_subtract)
LORICA_REJECT_MIXED(checked_multiply)
LORICA_REJECT_MIXED(checked_divide)
LORICA_REJECT_MIXED(saturating_add)
LORICA_REJECT_MIXED(saturating_subtract)
LORICA_REJECT_MIXED(saturating_multiply)
#undef LORICA_REJECT_MIXED

// Each check runs before the operation, so no intermediate result overflows,
// including promoted small unsigned operands (65535 * 65535 as int).
// @implements SPEC-LR-INTEGER
template<int&..., class T, same_checked_integral<T> U>
[[nodiscard]] constexpr std::optional<T> checked_add(T left, U right) noexcept {
    using limits = std::numeric_limits<T>;
    if constexpr (std::is_signed_v<T>) {
        if ((right > 0 && left > (limits::max)() - right) ||
            (right < 0 && left < (limits::min)() - right)) return std::nullopt;
    } else if (left > (limits::max)() - right) {
        return std::nullopt;
    }
    return static_cast<T>(left + right);
}

// @implements SPEC-LR-INTEGER
template<int&..., class T, same_checked_integral<T> U>
[[nodiscard]] constexpr std::optional<T> checked_subtract(T left, U right) noexcept {
    using limits = std::numeric_limits<T>;
    if constexpr (std::is_signed_v<T>) {
        if ((right < 0 && left > (limits::max)() + right) ||
            (right > 0 && left < (limits::min)() + right)) return std::nullopt;
    } else if (left < right) {
        return std::nullopt;
    }
    return static_cast<T>(left - right);
}

// @implements SPEC-LR-INTEGER
template<int&..., class T, same_checked_integral<T> U>
[[nodiscard]] constexpr std::optional<T> checked_multiply(T left, U right) noexcept {
    using limits = std::numeric_limits<T>;
    if constexpr (std::is_signed_v<T>) {
        if (left > 0) {
            if (right > 0 ? left > (limits::max)() / right : right < (limits::min)() / left)
                return std::nullopt;
        } else if (right > 0) {
            if (left < (limits::min)() / right) return std::nullopt;
        } else if (left != 0 && right < (limits::max)() / left) {
            return std::nullopt;
        }
    } else if (left != 0 && right > (limits::max)() / left) {
        return std::nullopt;
    }
    return static_cast<T>(left * right);
}

// Division without its two undefined cases: a zero divisor and MIN / -1.
// @implements SPEC-LR-INTEGER
template<int&..., class T, same_checked_integral<T> U>
[[nodiscard]] constexpr std::optional<T> checked_divide(T left, U right) noexcept {
    if (right == 0) return std::nullopt;
    if constexpr (std::is_signed_v<T>) {
        if (left == (std::numeric_limits<T>::min)() && right == -1) return std::nullopt;
    }
    return static_cast<T>(left / right);
}

// Saturating forms clamp to the type's range. The fallbacks name the checked
// templates with <>, so a non-template overload in scope (checked_size.hpp's) is
// never chosen and the meaning does not depend on include order.
// @implements SPEC-LR-INTEGER
template<int&..., class T, same_checked_integral<T> U>
[[nodiscard]] constexpr T saturating_add(T left, U right) noexcept {
    using limits = std::numeric_limits<T>;
    return checked_add<>(left, right).value_or(
        std::is_signed_v<T> && right < 0 ? (limits::min)() : (limits::max)());
}

// @implements SPEC-LR-INTEGER
template<int&..., class T, same_checked_integral<T> U>
[[nodiscard]] constexpr T saturating_subtract(T left, U right) noexcept {
    using limits = std::numeric_limits<T>;
    return checked_subtract(left, right).value_or(
        std::is_signed_v<T> && right < 0 ? (limits::max)() : (limits::min)());
}

// @implements SPEC-LR-INTEGER
template<int&..., class T, same_checked_integral<T> U>
[[nodiscard]] constexpr T saturating_multiply(T left, U right) noexcept {
    using limits = std::numeric_limits<T>;
    return checked_multiply<>(left, right).value_or(
        (left < 0) != (right < 0) ? (limits::min)() : (limits::max)());
}

// @implements SPEC-LR-INTEGER
template<checked_integral To, int&..., checked_integral From>
[[nodiscard]] constexpr To saturate_cast(From value) noexcept {
    using limits = std::numeric_limits<To>;
    if (std::cmp_less(value, (limits::min)())) return (limits::min)();
    if (std::cmp_greater(value, (limits::max)())) return (limits::max)();
    return static_cast<To>(value);
}
} // namespace lorica
