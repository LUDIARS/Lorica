// Linux only, linked with -Wl,--wrap=mmap,--wrap=mprotect,--wrap=munmap: the
// wrappers record what the implementation asks the kernel for and inject single
// failures; every other call reaches the kernel unchanged.
#include <lorica/sealed_value.hpp>
#include <sys/mman.h>
#include <cerrno>
#include <cstdio>
#include <cstdlib>
#include <exception>
#include <fstream>
#include <string>
#include <system_error>
#include <unistd.h>

namespace {
// @implements SPEC-LR-VERIFY
void require(bool condition) { if (!condition) std::abort(); }
struct call { int count = 0; void* address = nullptr; std::size_t length = 0; int prot = 0, flags = 0; };
call mmaps, mprotects, munmaps;
int fail_mmap = 0, fail_mprotect = 0, fail_munmap = 0; // errno for the next call; 0 forwards
bool fail(int& error) {
    if (error == 0) return false;
    errno = error;
    error = 0;
    return true;
}
// Permissions of the mapping holding `address` ("r--p"), empty when unmapped.
std::string permissions_at(const void* address) {
    std::ifstream maps("/proc/self/maps");
    for (std::string line; std::getline(maps, line);) {
        unsigned long begin = 0, end = 0;
        char permissions[5] = "";
        const auto at = reinterpret_cast<unsigned long>(address);
        if (std::sscanf(line.c_str(), "%lx-%lx %4s", &begin, &end, permissions) == 3 && begin <= at && at < end)
            return permissions;
    }
    return {};
}
}
extern "C" void* __real_mmap(void*, std::size_t, int, int, int, off_t);
extern "C" int __real_mprotect(void*, std::size_t, int);
extern "C" int __real_munmap(void*, std::size_t);
extern "C" void* __wrap_mmap(void* address, std::size_t length, int prot, int flags, int fd, off_t offset) {
    void* result = fail(fail_mmap) ? MAP_FAILED : __real_mmap(address, length, prot, flags, fd, offset);
    mmaps = {mmaps.count + 1, result, length, prot, flags};
    return result;
}
extern "C" int __wrap_mprotect(void* address, std::size_t length, int prot) {
    mprotects = {mprotects.count + 1, address, length, prot, 0};
    return fail(fail_mprotect) ? -1 : __real_mprotect(address, length, prot);
}
extern "C" int __wrap_munmap(void* address, std::size_t length) {
    munmaps = {munmaps.count + 1, address, length, 0, 0};
    if (fail(fail_munmap)) return -1;
    const int result = __real_munmap(address, length);
    if (result == 0) errno = 0; // A successful call may change errno; the saved error must win.
    return result;
}
// @implements SPEC-LR-VERIFY
int main() {
    {
        const lorica::sealed_value<int> value(7);
        // Private, never executable, sealed read-only over the whole mapping.
        require(mmaps.count == 1 && mprotects.count == 1 && munmaps.count == 0);
        require((mmaps.prot & PROT_EXEC) == 0 && (mmaps.flags & MAP_PRIVATE) && !(mmaps.flags & MAP_SHARED));
        require(mprotects.prot == PROT_READ && mprotects.address == mmaps.address &&
                mprotects.length == mmaps.length);
        require(permissions_at(mmaps.address) == "r--p" && value.load() == 7);
    }
    require(munmaps.count == 1 && munmaps.address == mmaps.address && munmaps.length == mmaps.length);
    const unsigned char byte = 9;
    // OS failures throw system_error with the OS code; failed sealing releases the page.
    fail_mmap = ENOMEM;
    try { lorica::detail::sealed_region region(&byte, 1); require(false); }
    catch (const std::system_error& error) { require(error.code() == std::errc::not_enough_memory); }
    fail_mprotect = EACCES;
    try { lorica::detail::sealed_region region(&byte, 1); require(false); }
    catch (const std::system_error& error) { require(error.code() == std::errc::permission_denied); }
    require(munmaps.count == 2 && munmaps.address == mmaps.address && munmaps.length == mmaps.length);
    // The kernel refusing a release for lack of mappings leaves the page read-only.
    {
        lorica::detail::sealed_region region(&byte, 1);
        fail_munmap = ENOMEM;
    }
    require(permissions_at(mmaps.address) == "r--p" && *static_cast<const unsigned char*>(mmaps.address) == byte);
    require(__real_munmap(mmaps.address, mmaps.length) == 0);
    // Any other release failure terminates.
    std::set_terminate([] { std::_Exit(EXIT_SUCCESS); });
    {
        lorica::detail::sealed_region region(&byte, 1);
        fail_munmap = EINVAL;
    }
    return EXIT_FAILURE;
}
