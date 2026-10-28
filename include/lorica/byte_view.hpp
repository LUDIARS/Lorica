#pragma once

#include <cstddef>
#include <optional>
#include "checked_size.hpp"

namespace lorica {
// Non-owning, read-only view. The caller must supply a live contiguous object
// of at least size bytes and retain it unchanged for the lifetime of the view.
class byte_view final {
public:
    [[nodiscard]] static constexpr std::optional<byte_view> make(
        const std::byte* data, std::size_t size, std::size_t maximum) noexcept {
        if (size > maximum || (data == nullptr && size != 0)) return std::nullopt;
        return byte_view(data, size);
    }

    [[nodiscard]] constexpr std::size_t size() const noexcept { return size_; }
    [[nodiscard]] constexpr std::optional<std::byte> at(std::size_t index) const noexcept {
        if (index >= size_) return std::nullopt;
        return data_[index];
    }
    [[nodiscard]] constexpr std::optional<byte_view> subview(
        std::size_t offset, std::size_t length) const noexcept {
        if (!contains_range(size_, offset, length)) return std::nullopt;
        // Even adding zero to a null pointer is avoided.
        return byte_view(offset == 0 ? data_ : data_ + offset, length);
    }

private:
    constexpr byte_view(const std::byte* data, std::size_t size) noexcept
        : data_(data), size_(size) {}
    const std::byte* data_;
    std::size_t size_;
};
} // namespace lorica
