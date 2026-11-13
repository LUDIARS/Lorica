// Built twice: LORICA_CONTRACT_EVALUATION_SEMANTIC=enforce and =quick_enforce, and
// once more with exceptions disabled. Each mode violates a contract in a child.
// LORICA_TEST_OVERLAY builds the same program with the contract laid over the
// unchanged function from outside; the outcomes must not differ.
#ifdef LORICA_TEST_OVERLAY
#include <lorica/contract_overlay.hpp>
#else
#include <lorica/contracts.hpp>
#endif
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
#ifdef LORICA_TEST_OVERLAY
// @implements SPEC-LR-VERIFY
int checked_index(int index) { return index; }
const auto call_checked_index = LORICA_CONTRACT(checked_index)
    .pre([](int index) { return index >= 0; }, "index >= 0");
#else
// @implements SPEC-LR-VERIFY
int checked_index(int index) {
    LORICA_PRE(index >= 0);
    return index;
}
const auto call_checked_index = &checked_index;
#endif
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
#if LORICA_DETAIL_CONTRACT_EXCEPTIONS
// @implements SPEC-LR-VERIFY
bool throwing_predicate() { throw 1; }
#endif
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
    if (std::strcmp(argv[1], "--satisfied") == 0) return call_checked_index(0);
#ifdef LORICA_TEST_OVERLAY
    if (std::strcmp(argv[1], "--delegate-returns") == 0) {
        // An overlay's own delegate does not turn enforce into observe.
        const auto delegated = call_checked_index.on_violation(
            [](const lorica::contracts::contract_violation& violation) {
                std::fprintf(stderr, "own delegate: %s terminating=%d\n", violation.comment(),
                             violation.is_terminating() ? 1 : 0);
                std::fflush(stderr);
            });
        static_cast<void>(delegated(-1));
        return 5;
    }
#endif
#if LORICA_DETAIL_CONTRACT_EXCEPTIONS
    if (std::strcmp(argv[1], "--predicate-throws") == 0) {
        // A predicate that throws is handled as any violation of the semantic.
        lorica::contracts::set_violation_handler(&returning_handler);
        LORICA_CONTRACT_ASSERT(throwing_predicate());
        return 5;
    }
#endif
    if (std::strcmp(argv[1], "--handler-returns") == 0) {
        lorica::contracts::set_violation_handler(&returning_handler);
    } else if (std::strcmp(argv[1], "--handler-violates") == 0) {
        lorica::contracts::set_violation_handler(&violating_handler);
    } else if (std::strcmp(argv[1], "--default") != 0) {
        return 2;
    }
    static_cast<void>(call_checked_index(-1));
    return 5; // Reaching here means the contract did not terminate.
}
