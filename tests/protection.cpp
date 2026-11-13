#include <lorica/sealed_value.hpp>
#include <cstdlib>
#include <cstring>
#include <limits>
#include <stdexcept>
#include <thread>
#include <type_traits>
#include <vector>
#ifdef _WIN32
#define WIN32_LEAN_AND_MEAN
#define NOMINMAX
#include <windows.h>
#else
#include <signal.h>
#include <sys/resource.h>
#include <unistd.h>
#endif

namespace {
// @implements SPEC-LR-VERIFY
void require(bool condition) { if (!condition) std::abort(); }
#ifndef _WIN32
// The fault counts only as a write denied on the sealed byte itself: any other
// SIGSEGV, or one while reading, exits with a status the harness rejects.
const void* volatile expected_address = nullptr;
volatile sig_atomic_t writing = 0;
extern "C" void on_fault(int, siginfo_t* info, void*) {
    if (!writing) _exit(6);
    if (info->si_code != SEGV_ACCERR || info->si_addr != expected_address) _exit(5);
    signal(SIGSEGV, SIG_DFL); // The write repeats on return and ends the child by SIGSEGV.
}
#endif
enum class setting : unsigned { enabled = 7 };
}
// @implements SPEC-LR-VERIFY
int main(int argc, char** argv) {
    const bool write = argc == 2 && std::strcmp(argv[1], "--write") == 0;
    // Harness control: the same write, judged against an address it does not touch.
    const bool misdirected = argc == 2 && std::strcmp(argv[1], "--misdirected") == 0;
    if (write || misdirected) {
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
#ifndef _WIN32
        // Own the SIGSEGV disposition: sanitizer runtimes install their own handler.
        expected_address = write ? storage.data() : nullptr;
        struct sigaction action {};
        action.sa_sigaction = on_fault;
        action.sa_flags = SA_SIGINFO;
        if (sigaction(SIGSEGV, &action, nullptr) != 0) return 4;
        if (*address != 42) return 6;
        writing = 1;
#endif
        *address = 43;
        return 3;
    }
    static_assert(!std::is_copy_constructible_v<lorica::sealed_value<int>>);
    static_assert(!std::is_move_constructible_v<lorica::sealed_value<int>>);
    static_assert(!std::is_copy_assignable_v<lorica::sealed_value<int>>);
    static_assert(!std::is_move_assignable_v<lorica::sealed_value<int>>);
    static_assert(!std::is_convertible_v<int, lorica::sealed_value<int>>);
    static_assert(!std::is_copy_constructible_v<lorica::detail::sealed_region> &&
                  !std::is_move_constructible_v<lorica::detail::sealed_region> &&
                  !std::is_copy_assignable_v<lorica::detail::sealed_region> &&
                  !std::is_move_assignable_v<lorica::detail::sealed_region>);
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
    // Concurrent readers of published values (meaningful under ThreadSanitizer).
    std::vector<std::thread> readers;
    for (int thread = 0; thread < 4; ++thread) readers.emplace_back([&] {
        for (int i = 0; i < 10000; ++i)
            require(minimum.load() == (std::numeric_limits<int>::min)() && flag.load() == setting::enabled);
    });
    for (auto& reader : readers) reader.join();
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
