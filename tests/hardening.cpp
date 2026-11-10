#include <cstdlib>
#include <cstring>
#include <optional>
#include <string_view>
#include <vector>
#ifdef _WIN32
#define WIN32_LEAN_AND_MEAN
#define NOMINMAX
#include <windows.h>
#include <crtdbg.h>
#else
#include <sys/resource.h>
#endif

// The build says which FORTIFY level its configuration must have (CMake passes 3
// for optimized Linux configurations); a weaker one fails here, at compile time.
#if defined(LORICA_TEST_EXPECT_FORTIFY) && (!defined(_FORTIFY_SOURCE) || _FORTIFY_SOURCE < LORICA_TEST_EXPECT_FORTIFY)
#error "the extended profile did not set _FORTIFY_SOURCE=3"
#endif

namespace {
// @implements SPEC-LR-VERIFY
void require(bool condition) { if (!condition) std::abort(); }

// @implements SPEC-LR-VERIFY
bool quiet_crash() {
#ifdef _WIN32
    SetErrorMode(SEM_FAILCRITICALERRORS | SEM_NOGPFAULTERRORBOX);
    // A debug CRT reports a failed check in a dialog before failing fast.
    _CrtSetReportMode(_CRT_ASSERT, _CRTDBG_MODE_FILE);
    _CrtSetReportFile(_CRT_ASSERT, _CRTDBG_FILE_STDERR);
    _set_abort_behavior(0, _WRITE_ABORT_MSG | _CALL_REPORTFAULT);
    return true;
#else
    const rlimit limit{0, 0};
    return setrlimit(RLIMIT_CORE, &limit) == 0;
#endif
}
}

// The extended profile's checks, observed from outside (tests/hardening_fault.py).
// Each violation runs only in a disposable child; the argument's length supplies
// the out-of-range amount, so no compiler can see the defect at build time.
// @implements SPEC-LR-VERIFY
int main(int argc, char** argv) {
    if (argc == 3) {
        if (!quiet_crash()) return 4;
        const std::string_view mode(argv[1]);
        const std::size_t amount = std::strlen(argv[2]);
        if (mode == "--element") {
            // Hardened standard library: an index past the end stops the program.
            std::vector<int> values(1);
            return values[amount];
        }
        if (mode == "--empty-optional") {
            std::optional<int> value;
            if (amount != 0) value.reset();
            return *value;
        }
        if (mode == "--copy") {
            // _FORTIFY_SOURCE=3: a copy past a heap buffer whose size is known only
            // at run time stops the program. Level 2 and the stack protector cannot
            // see this buffer's size, so only level 3 passes the test.
            char* target = static_cast<char*>(std::malloc(amount / 2 + 1));
            if (target == nullptr) return 6;
            std::memcpy(target, argv[2], amount);
            const char first = target[0];
            std::free(target);
            return first;
        }
        return 5;
    }
    // In range, the same operations behave normally.
    std::vector<int> values{1, 2, 3};
    require(values[2] == 3 && values.front() == 1 && values.back() == 3);
    const std::optional<int> value(7);
    require(*value == 7);
    char target[4] = {};
    std::memcpy(target, "abc", 3);
    require(target[2] == 'c');
    return 0;
}
