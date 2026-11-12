// Built with LORICA_CONTRACT_EVALUATION_SEMANTIC=ignore.
#include <lorica/contracts.hpp>
#include <cstdlib>

namespace {
// @implements SPEC-LR-VERIFY
void require(bool condition) { if (!condition) std::abort(); }
int evaluations = 0;
// @implements SPEC-LR-VERIFY
bool counted_false() { ++evaluations; return false; }
// @implements SPEC-LR-VERIFY
int checked(int value) {
    LORICA_PRE(counted_false());
    LORICA_POST(counted_false());
    LORICA_CONTRACT_ASSERT(counted_false());
    return LORICA_POST_RETURN(value, r, counted_false() && r == 0);
}
// @implements SPEC-LR-VERIFY
void failing_handler(const lorica::contracts::contract_violation&) { std::abort(); }
} // namespace

// @implements SPEC-LR-VERIFY
int main() {
    lorica::contracts::set_violation_handler(&failing_handler);
    require(checked(5) == 5);
    require(evaluations == 0); // ignore never evaluates a predicate.
}
