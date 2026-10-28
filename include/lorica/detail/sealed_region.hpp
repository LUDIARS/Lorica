#pragma once
#include <cstddef>

namespace lorica::detail {
// @implements SPEC-LR-SEALED
// Internal OS mapping owner; callers must provide live, nonempty source bytes.
class sealed_region final {
public:
    sealed_region(const void* source, std::size_t size);
    ~sealed_region() noexcept;
    sealed_region(const sealed_region&) = delete;
    sealed_region& operator=(const sealed_region&) = delete;
    sealed_region(sealed_region&&) = delete;
    sealed_region& operator=(sealed_region&&) = delete;
    const void* data() const noexcept { return data_; }
private:
    void* data_ = nullptr;
    std::size_t size_ = 0;
};
}
