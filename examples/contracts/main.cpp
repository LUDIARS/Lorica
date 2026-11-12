// A contract laid over existing code from outside, and the same contract used as
// the code's test. Build with LORICA_CONTRACT_EVALUATION_SEMANTIC=ignore and the
// output is identical: the overlay then is the plain call.
#include <lorica/contract_overlay.hpp>
#include <cstddef>
#include <cstdio>
#include <utility>

namespace shop {
// Existing code. Nothing below edits it.
// @implements SPEC-LR-CONTRACT-OVERLAY
int reserve(int in_stock, int requested) { return in_stock - requested; }
// A defect the contract is expected to catch.
// @implements SPEC-LR-CONTRACT-OVERLAY
int reserve_miscounting(int in_stock, int requested) { return in_stock - requested - 1; }
} // namespace shop

namespace {
// The contract of reserve(), written once and laid over whatever implements it.
// @implements SPEC-LR-CONTRACT-OVERLAY
template <class Overlay>
constexpr auto with_reserve_contract(Overlay overlay) {
    return std::move(overlay)
        .pre([](int in_stock, int) { return in_stock >= 0; }, "stock is not negative")
        .pre([](int in_stock, int requested) { return requested >= 0 && requested <= in_stock; },
             "request is covered by the stock")
        .post([](int left, int in_stock, int requested) { return left == in_stock - requested; },
              "what is left is the stock less the request");
}

constexpr auto reserve = with_reserve_contract(LORICA_CONTRACT(shop::reserve));
constexpr auto miscounting = with_reserve_contract(LORICA_CONTRACT(shop::reserve_miscounting));

struct expectation {
    int in_stock;
    int requested;
    lorica::contracts::test_status status;
};

// @implements SPEC-LR-CONTRACT-OVERLAY
const char* name(lorica::contracts::test_status status) {
    switch (status) {
    case lorica::contracts::test_status::satisfied: return "satisfied";
    case lorica::contracts::test_status::precondition_failed: return "precondition failed";
    case lorica::contracts::test_status::postcondition_failed: return "postcondition failed";
    }
    return "unknown";
}

// Runs one overlay against a table and says whether every outcome was the expected one.
// @implements SPEC-LR-CONTRACT-OVERLAY
template <class Overlay, std::size_t Count>
bool run(const char* title, const Overlay& overlay, const expectation (&table)[Count]) {
    bool as_expected = true;
    for (const expectation& each : table) {
        const lorica::contracts::test_result result = overlay.test(each.in_stock, each.requested);
        std::printf("%s(%d, %d): %s%s%s\n", title, each.in_stock, each.requested,
                    name(result.status), result.condition != nullptr ? ": " : "",
                    result.condition != nullptr ? result.condition : "");
        as_expected = as_expected && result.status == each.status;
    }
    return as_expected;
}
} // namespace

// @implements SPEC-LR-CONTRACT-OVERLAY
int main() {
    using lorica::contracts::test_status;
    // In the product the overlay is called like the function it covers.
    std::printf("reserve(10, 3) = %d\n", reserve(10, 3));

    // In a test its conditions are the oracle. A refused call is never made.
    const expectation correct[] = {
        {10, 3, test_status::satisfied},
        {10, 10, test_status::satisfied},
        {10, 11, test_status::precondition_failed},
        {-1, 0, test_status::precondition_failed},
    };
    const expectation defective[] = {
        {10, 3, test_status::postcondition_failed},
        {10, 11, test_status::precondition_failed},
    };
    const bool passed = run("reserve", reserve, correct) &&
                        run("reserve_miscounting", miscounting, defective);
    std::printf("%s\n", passed ? "every outcome as expected" : "UNEXPECTED OUTCOME");
    return passed ? 0 : 1;
}
