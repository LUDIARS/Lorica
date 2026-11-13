#pragma once
#include <lorica/checked_size.hpp>
#include <lorica/detail/sealed_region.hpp>
#include <cstddef>
#include <cstring>
#include <exception>
#include <memory>
#include <optional>
#include <stdexcept>
#include <type_traits>

namespace lorica {
// @implements SPEC-LR-PACK
// What a pack can hold: copyable byte for byte and readable back as a copy.
// Pointers inside a T (for example in a member) are not rejected and stay unprotected.
template<class T>
inline constexpr bool is_packable_v =
    std::is_object_v<T> && !std::is_array_v<T> && !std::is_pointer_v<T> &&
    !std::is_member_pointer_v<T> && std::is_same_v<T, std::remove_cv_t<T>> &&
    std::is_trivially_copyable_v<T> && std::is_trivially_copy_constructible_v<T> &&
    std::is_default_constructible_v<T>;

namespace detail {
struct pack_place {
    std::size_t offset;
    std::size_t end;
};
// @implements SPEC-LR-PACK
// Where count elements of size bytes, aligned to alignment (a power of two), go
// after used bytes; empty when they would not end within capacity. An empty
// request takes no bytes.
[[nodiscard]] constexpr std::optional<pack_place> place_in_pack(std::size_t used, std::size_t capacity,
    std::size_t count, std::size_t size, std::size_t alignment) noexcept {
    const auto bytes = checked_multiply(count, size);
    if (!bytes) return std::nullopt;
    if (*bytes == 0) return pack_place{used, used};
    const auto raised = checked_add(used, alignment - 1);
    if (!raised) return std::nullopt;
    const std::size_t offset = *raised & ~(alignment - 1);
    if (!contains_range(capacity, offset, *bytes)) return std::nullopt;
    return pack_place{offset, offset + *bytes};
}
} // namespace detail

class pack_builder;
class sealed_pack;

// @implements SPEC-LR-PACK
// Names one value by its offset. Only a builder makes one; it does not know its pack.
template<class T>
class pack_slot final {
    friend class pack_builder;
    friend class sealed_pack;
    explicit constexpr pack_slot(std::size_t offset) noexcept : offset_(offset) {}
    std::size_t offset_;
};

// @implements SPEC-LR-PACK
template<class T>
class pack_array_slot final {
public:
    [[nodiscard]] constexpr std::size_t size() const noexcept { return count_; }
private:
    friend class pack_builder;
    friend class sealed_pack;
    constexpr pack_array_slot(std::size_t offset, std::size_t count) noexcept : offset_(offset), count_(count) {}
    std::size_t offset_;
    std::size_t count_;
};

// @implements SPEC-LR-PACK
// Copies values into ordinary heap memory. Nothing here is protected until a
// sealed_pack is constructed from it; refused input is returned as empty.
class pack_builder final {
public:
    explicit pack_builder(std::size_t capacity) : capacity_(capacity) {
        if (capacity == 0) throw std::invalid_argument("empty pack");
        staging_.reset(new unsigned char[capacity]()); // Zeroed: padding is sealed too.
    }
    pack_builder(const pack_builder&) = delete;
    pack_builder& operator=(const pack_builder&) = delete;
    pack_builder(pack_builder&&) = delete;
    pack_builder& operator=(pack_builder&&) = delete;

    template<class T>
    [[nodiscard]] std::optional<pack_slot<T>> add(const T& value) noexcept {
        static_assert(is_packable_v<T>, "lorica::pack_builder: T must satisfy lorica::is_packable_v");
        const auto place = reserve(1, sizeof(T), alignof(T));
        if (!place) return std::nullopt;
        std::memcpy(staging_.get() + place->offset, &value, sizeof(T));
        return pack_slot<T>(place->offset);
    }
    template<class T>
    [[nodiscard]] std::optional<pack_array_slot<T>> add_array(const T* data, std::size_t count) noexcept {
        static_assert(is_packable_v<T>, "lorica::pack_builder: T must satisfy lorica::is_packable_v");
        if (data == nullptr && count != 0) return std::nullopt;
        const auto place = reserve(count, sizeof(T), alignof(T));
        if (!place) return std::nullopt;
        if (count != 0) std::memcpy(staging_.get() + place->offset, data, count * sizeof(T));
        return pack_array_slot<T>(place->offset, count);
    }
    [[nodiscard]] std::size_t used() const noexcept { return used_; }
    [[nodiscard]] std::size_t capacity() const noexcept { return capacity_; }

private:
    friend class sealed_pack;
    std::optional<detail::pack_place> reserve(std::size_t count, std::size_t size, std::size_t alignment) noexcept {
        if (!staging_) return std::nullopt; // Consumed by a sealed_pack.
        const auto place = detail::place_in_pack(used_, capacity_, count, size, alignment);
        if (place) used_ = place->end;
        return place;
    }
    std::unique_ptr<unsigned char[]> staging_;
    std::size_t capacity_;
    std::size_t used_ = 0;
};

// @implements SPEC-LR-PACK
// The builder's used bytes in one OS mapping, sealed read-only before
// construction returns. Reads return copies.
class sealed_pack final {
public:
    // Throws std::invalid_argument when nothing was added (or the builder was
    // consumed) and std::system_error when the OS refuses; the builder is then
    // unchanged. On success the builder is consumed.
    explicit sealed_pack(pack_builder&& builder)
        : region_(builder.staging_.get(), builder.used_), used_(builder.used_) {
        builder.staging_.reset();
        builder.capacity_ = 0;
        builder.used_ = 0;
    }
    sealed_pack(const sealed_pack&) = delete;
    sealed_pack& operator=(const sealed_pack&) = delete;
    sealed_pack(sealed_pack&&) = delete;
    sealed_pack& operator=(sealed_pack&&) = delete;

    template<class T>
    [[nodiscard]] T load(pack_slot<T> slot) const noexcept { return read<T>(slot.offset_); }
    // The index may come from input: out of range is a value, not a fault.
    template<class T>
    [[nodiscard]] std::optional<T> at(pack_array_slot<T> slot, std::size_t index) const noexcept {
        if (index >= slot.count_) return std::nullopt;
        return read<T>(slot.offset_ + index * sizeof(T)); // read() bounds even a wrapped sum.
    }

private:
    template<class T>
    T read(std::size_t offset) const noexcept {
        // Keeps the read inside this pack's bytes. It cannot tell whose slot this is.
        if (!contains_range(used_, offset, sizeof(T))) std::terminate();
        T value{};
        std::memcpy(&value, static_cast<const unsigned char*>(region_.data()) + offset, sizeof(T));
        return value;
    }
    detail::sealed_region region_;
    std::size_t used_;
};
} // namespace lorica
