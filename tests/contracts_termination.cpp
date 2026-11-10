// Built twice: LORICA_CONTRACT_EVALUATION_SEMANTIC=enforce and =quick_enforce, and
// once more with exceptions disabled. Each mode violates a contract in a child.
#include <lorica/contracts.hpp>
#include <cstdio>
#include <cstdlib>
#include <cstring>
#ifdef _WIN32
#define WIN32_LEAN_AND_MEAN
#define NOMINMAX
#include <windows.h>
#else
#include <sys/resource.h>
#endif

namespace {
// @implements SPEC-LR-VERIFY
int checked_index(int index) {
    LORICA_PRE(index >= 0);
    return index;
}
// @implements SPEC-LR-VERIFY
void returning_handler(const lorica::contracts::contract_violation& violation) {
    std::fprintf(stderr, "custom handler: %s terminating=%d\n", violation.comment(),
                 violation.is_terminating() ? 1 : 0);
    std::fflush(stderr);
}
// @implements SPEC-LR-VERIFY
void violating_handler(const lorica::contracts::contract_violation&) {
    LORICA_CONTRACT_ASSERT(false);
}
} // namespace

// @implements SPEC-LR-VERIFY
int main(int argc, char** argv) {
#ifdef _WIN32
    // Exercise the CRT abort path with exit code 3, independently of WER.
    _set_abort_behavior(0, _WRITE_ABORT_MSG | _CALL_REPORTFAULT);
    SetErrorMode(SEM_FAILCRITICALERRORS | SEM_NOGPFAULTERRORBOX);
#else
    const rlimit limit{0, 0};
    if (setrlimit(RLIMIT_CORE, &limit) != 0) return 4;
#endif
    if (argc != 2) return 2;
    if (std::strcmp(argv[1], "--satisfied") == 0) return checked_index(0);
    if (std::strcmp(argv[1], "--handler-returns") == 0) {
        lorica::contracts::set_violation_handler(&returning_handler);
    } else if (std::strcmp(argv[1], "--handler-violates") == 0) {
        lorica::contracts::set_violation_handler(&violating_handler);
    } else if (std::strcmp(argv[1], "--default") != 0) {
        return 2;
    }
    static_cast<void>(checked_index(-1));
    return 5; // Reaching here means the contract did not terminate.
}
