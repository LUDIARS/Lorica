#ifdef __linux__
#include <lorica/detail/sealed_region.hpp>
#include <sys/mman.h>
#include <cerrno>
#include <cstring>
#include <exception>
#include <stdexcept>
#include <system_error>

namespace lorica::detail {
// @implements SPEC-LR-SEALED
sealed_region::sealed_region(const void* source, std::size_t size) : size_(size) {
    if (source == nullptr || size == 0) throw std::invalid_argument("empty sealed region");
    data_ = mmap(nullptr, size_, PROT_READ | PROT_WRITE, MAP_PRIVATE | MAP_ANONYMOUS, -1, 0);
    if (data_ == MAP_FAILED) {
        data_ = nullptr;
        throw std::system_error(errno, std::generic_category(), "mmap");
    }
    std::memcpy(data_, source, size_);
    if (mprotect(data_, size_, PROT_READ) != 0) {
        const auto error = errno;
        if (munmap(data_, size_) != 0) std::terminate();
        data_ = nullptr;
        throw std::system_error(error, std::generic_category(), "mprotect");
    }
}
// @implements SPEC-LR-SEALED
sealed_region::~sealed_region() noexcept {
    if (!data_ || munmap(data_, size_) == 0) return;
    // Unmapping from the middle of merged adjacent mappings needs one more kernel
    // mapping; at vm.max_map_count that is refused and the page stays read-only.
    if (errno == ENOMEM) return;
    std::terminate(); // Any other failure means the ownership invariant is broken.
}
}
#endif
