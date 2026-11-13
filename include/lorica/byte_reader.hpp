#pragma once

#if !defined(__cplusplus) || (defined(_MSVC_LANG) ? _MSVC_LANG : __cplusplus) < 202002L
#error "lorica/byte_reader.hpp requires C++20 or newer"
#endif

#include <lorica/checked_integer.hpp>
#include <bit>
#include <climits>
#include <concepts>
#include <cstddef>
#include <optional>
#include <ranges>
#include <span>
#include <type_traits>

namespace lorica {
// Bounds-checked cursor over untrusted bytes (packets, file records). It replaces
// pointer arithmetic plus memcpy/reinterpret_cast: every read checks the remaining
// length first, and a failed read consumes nothing. Integers are assembled byte by
// byte in the requested order, independent of the host's byte order and alignment.
// Like byte_view it is non-owning: the caller keeps the bytes alive and unchanged
// for the reader's lifetime; it does not validate pointer provenance or lifetime.
// @implements SPEC-LR-READER
class byte_reader final {
public:
    constexpr byte_reader() noexcept = default;
    constexpr explicit byte_reader(std::span<const std::byte> bytes) noexcept : bytes_(bytes) {}
    // A temporary container would be destroyed before the first read.
    template<class R>
        requires(!std::ranges::borrowed_range<R> && std::convertible_to<R, std::span<const std::byte>>)
    explicit byte_reader(R&&) = delete;

    [[nodiscard]] constexpr std::size_t size() const noexcept { return bytes_.size(); }
    [[nodiscard]] constexpr std::size_t offset() const noexcept { return offset_; }
    [[nodiscard]] constexpr std::size_t remaining() const noexcept { return bytes_.size() - offset_; }

    // The next count bytes, as a view into the underlying buffer.
    [[nodiscard]] constexpr std::optional<std::span<const std::byte>> take(std::size_t count) noexcept {
        if (count > remaining()) return std::nullopt;
        const auto part = bytes_.subspan(offset_, count);
        offset_ += count;
        return part;
    }

    [[nodiscard]] constexpr bool skip(std::size_t count) noexcept { return take(count).has_value(); }

    // An integer stored in order (std::endian::big or std::endian::little).
    template<checked_integral T, std::endian Order>
        requires(Order == std::endian::big || Order == std::endian::little)
    [[nodiscard]] constexpr std::optional<T> read() noexcept {
        using U = std::make_unsigned_t<std::remove_cv_t<T>>;
        const auto part = take(sizeof(T));
        if (!part) return std::nullopt;
        U value = 0;
        for (std::size_t index = 0; index < sizeof(T); ++index) {
            const std::size_t source = Order == std::endian::big ? index : sizeof(T) - 1 - index;
            value = static_cast<U>((sizeof(T) > 1 ? static_cast<U>(value << CHAR_BIT) : U{0}) |
                                   static_cast<U>((*part)[source]));
        }
        // C++20 defines the conversion to a signed type as modular (two's complement).
        return static_cast<T>(value);
    }

    template<checked_integral T>
    [[nodiscard]] constexpr std::optional<T> read_big_endian() noexcept {
        return read<T, std::endian::big>();
    }
    template<checked_integral T>
    [[nodiscard]] constexpr std::optional<T> read_little_endian() noexcept {
        return read<T, std::endian::little>();
    }

    // A length-prefixed field: a Length in Order, then that many bytes. Nothing is
    // consumed when the length is negative, does not fit size_t, or exceeds what
    // remains. A zero length gives an empty view.
    template<checked_integral Length, std::endian Order>
    [[nodiscard]] constexpr std::optional<std::span<const std::byte>> read_prefixed() noexcept {
        const auto start = offset_;
        const auto length = read<Length, Order>();
        const auto count = length ? narrow<std::size_t>(*length) : std::nullopt;
        const auto part = count ? take(*count) : std::nullopt;
        if (!part) offset_ = start;
        return part;
    }

private:
    std::span<const std::byte> bytes_{};
    std::size_t offset_ = 0;
};
} // namespace lorica
