#include <lorica/sealed_value.hpp>
#include <cstdlib>
#include <cstring>
#include <limits>
#include <stdexcept>
#include <type_traits>
#ifdef _WIN32
#define WIN32_LEAN_AND_MEAN
#define NOMINMAX
#include <windows.h>
#else
#include <sys/resource.h>
#endif

namespace {
// @implements SPEC-LR-VERIFY
void require(bool condition) { if (!condition) std::abort(); }
enum class setting : unsigned { enabled = 7 };
}
// @implements SPEC-LR-VERIFY
int main(int argc, char** argv) {
    if (argc == 2 && std::strcmp(argv[1], "--write") == 0) {
#ifdef _WIN32
        SetErrorMode(SEM_FAILCRITICALERRORS | SEM_NOGPFAULTERRORBOX);
#else
        const rlimit limit{0, 0};
        if (setrlimit(RLIMIT_CORE, &limit) != 0) return 4;
#endif
        const unsigned char original = 42;
        lorica::detail::sealed_region storage(&original, sizeof(original));
        // Deliberately violate the OS contract in a disposable child only.
        auto* address = const_cast<volatile unsigned char*>(
            static_cast<const volatile unsigned char*>(storage.data()));
        *address = 43;
        return 3;
    }
    static_assert(!std::is_copy_constructible_v<lorica::sealed_value<int>>);
    static_assert(!std::is_move_constructible_v<lorica::sealed_value<int>>);
    static_assert(!std::is_copy_assignable_v<lorica::sealed_value<int>>);
    static_assert(std::is_same_v<decltype(lorica::sealed_value<int>(1).load()), int>);
    const lorica::sealed_value<int> minimum((std::numeric_limits<int>::min)());
    const lorica::sealed_value<unsigned long long> maximum((std::numeric_limits<unsigned long long>::max)());
    const lorica::sealed_value<double> fractional(0.125);
    const lorica::sealed_value<setting> flag(setting::enabled);
    require(minimum.load() == (std::numeric_limits<int>::min)());
    require(maximum.load() == (std::numeric_limits<unsigned long long>::max)());
    require(fractional.load() == 0.125 && flag.load() == setting::enabled);
    auto copy = minimum.load();
    require(copy == (std::numeric_limits<int>::min)());
    copy = 0;
    require(copy == 0 && minimum.load() == (std::numeric_limits<int>::min)());
    bool rejected = false;
    try { lorica::detail::sealed_region invalid(nullptr, 1); }
    catch (const std::invalid_argument&) { rejected = true; }
    require(rejected);
    rejected = false;
    const unsigned char byte = 0;
    try { lorica::detail::sealed_region invalid(&byte, 0); }
    catch (const std::invalid_argument&) { rejected = true; }
    require(rejected);
#ifdef _WIN32
    const unsigned value = 3;
    lorica::detail::sealed_region region(&value, sizeof(value));
    MEMORY_BASIC_INFORMATION info{};
    require(VirtualQuery(region.data(), &info, sizeof(info)) == sizeof(info));
    require(info.Protect == PAGE_READONLY && info.State == MEM_COMMIT);
#endif
}
