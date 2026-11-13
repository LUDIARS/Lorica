#pragma once

#if !defined(__cplusplus) || (defined(_MSVC_LANG) ? _MSVC_LANG : __cplusplus) < 202002L
#error "lorica/bounded_text.hpp requires C++20 or newer"
#endif

#include <algorithm>
#include <concepts>
#include <cstddef>
#include <optional>
#include <ranges>
#include <span>
#include <string>
#include <string_view>
#include <type_traits>
#include <utility>
#if __has_include(<version>)
#include <version>
#endif
#if defined(__cpp_lib_format)
#include <format>
#endif

namespace lorica {
// Character types that form C strings.
// @implements SPEC-LR-TEXT
template<class T>
concept text_character = std::same_as<T, char> || std::same_as<T, wchar_t> ||
    std::same_as<T, char8_t> || std::same_as<T, char16_t> || std::same_as<T, char32_t>;

// A contiguous, sized buffer of writable characters that outlives the call: an
// lvalue array or container, or a view such as std::span. A temporary container
// would discard the result, so it is rejected at compile time. The size is the
// capacity and is never changed: a std::string destination keeps its size.
// @implements SPEC-LR-TEXT
template<class R>
concept writable_text = std::ranges::contiguous_range<R> && std::ranges::sized_range<R> &&
    std::ranges::borrowed_range<R> &&
    !std::is_const_v<std::remove_reference_t<std::ranges::range_reference_t<R>>> &&
    text_character<std::ranges::range_value_t<R>>;

template<class R>
using text_character_t = std::ranges::range_value_t<R>;

namespace detail {
// The text a source stands for: a character array is read up to its first
// terminator, which must lie inside the array (a fixed field without one is not a
// C string, and reading on would leave the array); anything else convertible to a
// string view is taken whole, and must not hold a terminator.
template<class C, class S>
[[nodiscard]] constexpr std::optional<std::basic_string_view<C>> source_text(const S& source) noexcept {
    if constexpr (std::is_array_v<S>) {
        const C* end = std::char_traits<C>::find(source, std::extent_v<S>, C{});
        if (end == nullptr) return std::nullopt;
        return std::basic_string_view<C>(source, static_cast<std::size_t>(end - source));
    } else {
        if constexpr (std::is_pointer_v<S>) {
            if (source == nullptr) return std::nullopt;
        }
        const std::basic_string_view<C> text{source};
        if (text.find(C{}) != text.npos) return std::nullopt;
        return text;
    }
}

// Writes text and a terminator at out[at...] (the caller has checked the room).
// char_traits::move copies correctly when text is a view into out.
template<class C>
constexpr std::size_t put_text(std::span<C> out, std::size_t at, std::basic_string_view<C> text) noexcept {
    if (!text.empty()) std::char_traits<C>::move(out.data() + at, text.data(), text.size());
    out[at + text.size()] = C{};
    return at + text.size();
}
} // namespace detail

// What copy_string and append_string read from: an array of the destination's
// character type, or anything else convertible to a string view of it. An array
// of unknown bound has no extent to search, so it does not compile.
// @implements SPEC-LR-TEXT
template<class S, class C>
concept text_source =
    (std::is_bounded_array_v<S> && std::same_as<std::remove_cv_t<std::remove_extent_t<S>>, C>) ||
    (!std::is_array_v<S> && !std::is_null_pointer_v<S> &&
     std::convertible_to<const S&, std::basic_string_view<C>>);

// Replacement for strcpy/wcscpy/strncpy: copies source and a terminator into
// destination and returns the length copied. A source that does not fit, a
// string or view holding a terminator (which would silently shorten the C
// string) and a character array without one leave destination holding an empty
// string and return empty: a cut-off value is never presented as complete. An
// empty destination is left untouched. Source may be a view into destination.
// A null pointer source is rejected. Only the C string is defined: bytes after the
// terminator keep their earlier content (unlike strncpy, nothing is zero-padded),
// so clear a field yourself before writing it out whole.
// @implements SPEC-LR-TEXT
template<writable_text D, class S>
    requires text_source<S, text_character_t<D>>
[[nodiscard]] constexpr std::optional<std::size_t> copy_string(D&& destination, const S& source) noexcept {
    using C = text_character_t<D>;
    std::span<C> out{destination};
    if (out.empty()) return std::nullopt;
    const auto in = detail::source_text<C>(source);
    if (!in || in->size() >= out.size()) {
        out.front() = C{};
        return std::nullopt;
    }
    return detail::put_text(out, 0, *in);
}

// Replacement for strcat/wcscat: appends source to the C string already held in
// destination and returns the new length. Fails like copy_string, and also when
// destination holds no terminator (its current content is then not a C string).
// @implements SPEC-LR-TEXT
template<writable_text D, class S>
    requires text_source<S, text_character_t<D>>
[[nodiscard]] constexpr std::optional<std::size_t> append_string(D&& destination, const S& source) noexcept {
    using C = text_character_t<D>;
    std::span<C> out{destination};
    if (out.empty()) return std::nullopt;
    const auto used = static_cast<std::size_t>(std::ranges::find(out, C{}) - out.begin());
    const auto in = detail::source_text<C>(source);
    if (!in || in->size() >= out.size() - used) {
        out.front() = C{};
        return std::nullopt;
    }
    return detail::put_text(out, used, *in);
}

#if defined(__cpp_lib_format)
// Replacement for sprintf/snprintf, where the library announces <format>
// (__cpp_lib_format: libstdc++ 13, libc++ 19, MSVC STL). The format string is
// checked at compile time, so no runtime value becomes a format string unless the
// caller opts in with std::runtime_format, and output never exceeds destination.
// Output that does not fit or holds a terminator (a shortened C string) leaves an
// empty string and returns empty. Format arguments must not refer to the
// destination (as for snprintf); only copy_string and append_string accept a
// source inside the destination. A formatter may still throw (std::format_error
// for a negative dynamic width, std::bad_alloc where the library formats through a
// heap buffer, or a user formatter's exception); destination then holds an empty
// string, and nothing was written past it.
// @implements SPEC-LR-TEXT
template<writable_text D, class... Args>
    requires std::same_as<text_character_t<D>, char>
[[nodiscard]] std::optional<std::size_t> format_into(
    D&& destination, std::format_string<Args...> format, Args&&... args) {
    std::span<char> out{destination};
    if (out.empty()) return std::nullopt;
    const std::size_t limit = out.size() - 1;
#if defined(__cpp_exceptions) || defined(_CPPUNWIND)
    std::format_to_n_result<std::span<char>::iterator> result;
    try {
        result = std::format_to_n(out.begin(), static_cast<std::ptrdiff_t>(limit), format,
                                  std::forward<Args>(args)...);
    } catch (...) {
        out.front() = '\0';
        throw;
    }
#else
    const auto result = std::format_to_n(out.begin(), static_cast<std::ptrdiff_t>(limit), format,
                                         std::forward<Args>(args)...);
#endif
    if (result.size < 0 || static_cast<std::size_t>(result.size) > limit) {
        out.front() = '\0';
        return std::nullopt;
    }
    const auto written = static_cast<std::size_t>(result.size);
    if (std::char_traits<char>::find(out.data(), written, '\0') != nullptr) {
        out.front() = '\0';
        return std::nullopt;
    }
    out[written] = '\0';
    return written;
}
#endif
} // namespace lorica
