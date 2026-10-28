#pragma once
#include <lorica/detail/sealed_region.hpp>
#include <cstring>
#include <type_traits>

namespace lorica {
// @implements SPEC-LR-SEALED
template<class T>
class sealed_value final {
    static_assert((std::is_arithmetic_v<T> || std::is_enum_v<T>) &&
                  std::is_same_v<T, std::remove_cv_t<T>>,
                  "sealed_value requires an unqualified arithmetic or enum type");
public:
    explicit sealed_value(T value) : storage_(&value, sizeof(value)) {}
    sealed_value(const sealed_value&) = delete;
    sealed_value& operator=(const sealed_value&) = delete;
    sealed_value(sealed_value&&) = delete;
    sealed_value& operator=(sealed_value&&) = delete;
    T load() const noexcept {
        T value{};
        std::memcpy(&value, storage_.data(), sizeof(value));
        return value;
    }
private:
    detail::sealed_region storage_;
};
}
