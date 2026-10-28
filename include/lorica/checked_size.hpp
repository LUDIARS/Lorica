#pragma once

#include <cstddef>
#include <limits>
#include <optional>

namespace lorica {
// These functions validate integer values, not pointer provenance or lifetime.
[[nodiscard]] constexpr std::optional<std::size_t> checked_add(
    std::size_t left, std::size_t right) noexcept {
    if (right > std::numeric_limits<std::size_t>::max() - left) return std::nullopt;
    return left + right;
}

[[nodiscard]] constexpr std::optional<std::size_t> checked_multiply(
    std::size_t left, std::size_t right) noexcept {
    if (left != 0 && right > std::numeric_limits<std::size_t>::max() / left)
        return std::nullopt;
    return left * right;
}

[[nodiscard]] constexpr bool contains_range(
    std::size_t capacity, std::size_t offset, std::size_t length) noexcept {
    return offset <= capacity && length <= capacity - offset;
}
} // namespace lorica
