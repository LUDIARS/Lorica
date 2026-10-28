#ifdef _WIN32
#include <lorica/detail/sealed_region.hpp>
#define WIN32_LEAN_AND_MEAN
#define NOMINMAX
#include <windows.h>
#include <cstring>
#include <exception>
#include <stdexcept>
#include <system_error>

namespace lorica::detail {
// @implements SPEC-LR-SEALED
sealed_region::sealed_region(const void* source, std::size_t size) : size_(size) {
    if (source == nullptr || size == 0) throw std::invalid_argument("empty sealed region");
    data_ = VirtualAlloc(nullptr, size_, MEM_RESERVE | MEM_COMMIT, PAGE_READWRITE);
    if (!data_) throw std::system_error(static_cast<int>(GetLastError()),
                                       std::system_category(), "VirtualAlloc");
    std::memcpy(data_, source, size_);
    DWORD previous = 0;
    if (!VirtualProtect(data_, size_, PAGE_READONLY, &previous)) {
        const auto error = GetLastError();
        if (!VirtualFree(data_, 0, MEM_RELEASE)) std::terminate();
        data_ = nullptr;
        throw std::system_error(static_cast<int>(error), std::system_category(), "VirtualProtect");
    }
}
// @implements SPEC-LR-SEALED
sealed_region::~sealed_region() noexcept {
    // Failure violates ownership invariants; a destructor cannot safely throw.
    if (data_ && !VirtualFree(data_, 0, MEM_RELEASE)) std::terminate();
}
}
#endif
