// Built with LORICA_CONTRACT_EVALUATION_SEMANTIC=ignore and linked without the
// contracts runtime: a reference to it from an ignored contract fails the link.
#include <lorica/contract_overlay.hpp>
#include <cstdlib>
#include <memory>
#include <utility>

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
int plain(int value) noexcept { return value; }
struct pinned final {
    explicit pinned(int held) : value(held) {}
    pinned(const pinned&) = delete;
    pinned& operator=(const pinned&) = delete;
    int value;
};
// @implements SPEC-LR-VERIFY
pinned pin(int value) { return pinned(value); }
// A local is moved through LORICA_POST_RETURN only when the call says so.
// @implements SPEC-LR-VERIFY
std::unique_ptr<int> boxed(int value) {
    auto box = std::make_unique<int>(value);
    return LORICA_POST_RETURN(std::move(box), r, r != nullptr);
}
} // namespace

// @implements SPEC-LR-VERIFY
int main() {
    require(checked(5) == 5);
    require(evaluations == 0); // ignore never evaluates a predicate.
    require(*boxed(3) == 3);

    // The same for a contract laid over a function: ignore is the plain call.
    const auto overlaid = LORICA_CONTRACT(plain)
        .pre([](int) { return counted_false(); }, "never holds")
        .post([](int, int) { return counted_false(); }, "never holds");
    static_assert(noexcept(overlaid(5)), "ignore adds nothing that can throw");
    require(overlaid(5) == 5 && evaluations == 0);
    // test() stays the oracle under every semantic; it reports and handles nothing.
    require(overlaid.test(5).status == lorica::contracts::test_status::precondition_failed);
    require(evaluations == 1);
    // ignore keeps no copy of the result: a type that cannot be moved still returns.
    const auto pinning = LORICA_CONTRACT(pin)
        .post([](const pinned&, int) { return counted_false(); }, "never holds");
    require(pinning(7).value == 7 && evaluations == 1);
}
