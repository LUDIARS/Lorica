// Each LORICA_TEST_REJECT value is one program that must not compile; built only
// by its test, through tests/run_build_probe.cmake.
#include <lorica/contract_overlay.hpp>

namespace {
// @implements SPEC-LR-VERIFY
int plain(int value) { return value; }
} // namespace

// @implements SPEC-LR-VERIFY
int main() {
#if LORICA_TEST_REJECT == 1
    // LR-OVERLAY-03: a condition that cannot take the arguments, also when stripped.
    const auto overlaid = LORICA_CONTRACT(plain).pre([](int, int) { return true; }, "arity");
    return overlaid(1);
#elif LORICA_TEST_REJECT == 2
    // A contract is one condition; a message is not a second argument.
    LORICA_PRE(plain(1) == 1, "plain returns its argument");
    return 0;
#elif LORICA_TEST_REJECT == 3
    // Built with an evaluation semantic that does not exist.
    LORICA_PRE(plain(1) == 1);
    return 0;
#endif
}
