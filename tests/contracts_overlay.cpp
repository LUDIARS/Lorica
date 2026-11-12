// Built with LORICA_CONTRACT_EVALUATION_SEMANTIC=observe, at C++17, C++20 and C++23.
#include <lorica/contract_overlay.hpp>
#include <cstdlib>
#include <memory>
#include <stdexcept>
#include <string>
#include <type_traits>
#include <utility>

namespace {
// @implements SPEC-LR-VERIFY
void require(bool condition) { if (!condition) std::abort(); }

struct recorded {
    int count = 0;
    lorica::contracts::assertion_kind kind{};
    lorica::contracts::evaluation_semantic semantic{};
    lorica::contracts::detection_mode mode{};
    std::string comment;
    std::string function;
    std::string file;
    unsigned long line = 0;
};
recorded installed;

// @implements SPEC-LR-VERIFY
void record(recorded& into, const lorica::contracts::contract_violation& violation) {
    ++into.count;
    into.kind = violation.kind();
    into.semantic = violation.semantic();
    into.mode = violation.mode();
    into.comment = violation.comment();
    into.function = violation.location().function_name();
    into.file = violation.location().file_name();
    into.line = violation.location().line();
}
// @implements SPEC-LR-VERIFY
void installed_handler(const lorica::contracts::contract_violation& violation) {
    record(installed, violation);
}

// The code under contract. Nothing below edits these bodies.
int calls = 0;
// @implements SPEC-LR-VERIFY
int divide(int dividend, int divisor) {
    ++calls;
    return divisor == 0 ? 0 : dividend / divisor;
}
// @implements SPEC-LR-VERIFY
constexpr int square(int value) { return value * value; }
int stored = 0;
// @implements SPEC-LR-VERIFY
void store(int value) { stored = value; }
// @implements SPEC-LR-VERIFY
int& slot(int& value) noexcept { return value; }
// @implements SPEC-LR-VERIFY
int take(std::unique_ptr<int> owned) { return *owned; }
// @implements SPEC-LR-VERIFY
int failing(int value) {
    if (value < 0) throw std::out_of_range("negative");
    return value;
}
struct account {
    int balance;
    // @implements SPEC-LR-VERIFY
    int withdraw(int amount) { return balance -= amount; }
};
// @implements SPEC-LR-VERIFY
bool throwing_predicate(int) { throw std::runtime_error("predicate"); }

struct delegate_failure final : std::runtime_error {
    delegate_failure() : std::runtime_error("delegate") {}
};

// Usable in constant evaluation: a call, and the conditions as a compile-time test.
constexpr auto checked_square = LORICA_CONTRACT(square)
    .pre([](int value) { return value > 0; }, "value is positive")
    .post([](int result, int value) { return result >= value; }, "square is not smaller");
static_assert(checked_square(3) == 9, "an overlay keeps a constexpr callable constexpr");
static_assert(checked_square.test(3), "satisfied conditions");
static_assert(checked_square.test(0).status ==
              lorica::contracts::test_status::precondition_failed, "refused argument");
static_assert(std::is_same_v<decltype(checked_square(3)), int>, "same result type");
} // namespace

// @implements SPEC-LR-VERIFY
int main() {
    using namespace lorica::contracts;
    require(set_violation_handler(&installed_handler) == nullptr);

    unsigned long attached_line = 0;
    attached_line = __LINE__; const auto checked_divide = LORICA_CONTRACT(divide)
        .pre([](int, int divisor) { return divisor != 0; }, "divisor is not zero")
        .pre([](int dividend, int) { return dividend >= 0; }, "dividend is not negative")
        .post([](int quotient, int dividend, int divisor) {
            return divisor == 0 || quotient * divisor <= dividend; }, "quotient is rounded down");

    // Conditions hold: the same result as the callable, which ran exactly once.
    require(checked_divide(7, 2) == divide(7, 2) && calls == 2 && installed.count == 0);

    // A violated precondition under observe: reported once, then the call proceeds.
    require(checked_divide(7, 0) == 0 && calls == 3);
    require(installed.count == 1 && installed.kind == assertion_kind::pre);
    require(installed.semantic == evaluation_semantic::observe);
    require(installed.mode == detection_mode::predicate_false);
    require(installed.comment == "divisor is not zero" && installed.function == "divide");
    require(installed.line == attached_line && installed.file == __FILE__);

    // Every precondition is its own assertion, evaluated in order.
    require(checked_divide(-7, 0) == 0);
    require(installed.count == 3 && installed.comment == "dividend is not negative");

    // A violated postcondition sees the result first and still returns it.
    const auto wrong = LORICA_CONTRACT(divide)
        .post([](int quotient, int, int) { return quotient < 0; }, "quotient is negative");
    require(wrong(6, 3) == 2);
    require(installed.count == 4 && installed.kind == assertion_kind::post);
    require(installed.comment == "quotient is negative");

    // The result type and value category of the callable are kept.
    const auto checked_slot = LORICA_CONTRACT(slot)
        .post([](const int& result, const int& value) { return &result == &value; }, "same object");
    int object = 5;
    static_assert(std::is_same_v<decltype(checked_slot(object)), int&>, "reference result");
    require(&checked_slot(object) == &object && installed.count == 4);

    // void results: the postcondition takes the arguments only.
    const auto checked_store = LORICA_CONTRACT(store)
        .post([](int value) { return stored == value; }, "value was stored");
    static_assert(std::is_void_v<decltype(checked_store(1))>, "void result");
    checked_store(11);
    require(stored == 11 && installed.count == 4);
    const auto wrong_store = LORICA_CONTRACT(store)
        .post([](int value) { return stored != value; }, "value was not stored");
    wrong_store(12);
    require(stored == 12 && installed.count == 5 && installed.kind == assertion_kind::post);
    require(installed.comment == "value was not stored");

    // Arguments are forwarded: a move-only argument reaches the callable.
    const auto checked_take = LORICA_CONTRACT(take)
        .pre([](const std::unique_ptr<int>& owned) { return owned != nullptr; }, "owned is set");
    require(checked_take(std::make_unique<int>(9)) == 9 && installed.count == 5);

    // Member functions take the object first, as std::invoke does.
    const auto checked_withdraw = LORICA_CONTRACT(&account::withdraw)
        .pre([](const account& from, int amount) { return amount <= from.balance; }, "covered")
        .post([](int balance, const account&, int) { return balance >= 0; }, "not overdrawn");
    account savings{10};
    require(checked_withdraw(savings, 4) == 6 && savings.balance == 6 && installed.count == 5);
    require(checked_withdraw(savings, 7) == -1 && installed.count == 7);

    // An exception from the callable leaves unchanged; no postcondition is checked.
    const auto checked_failing = LORICA_CONTRACT(failing)
        .post([](int, int) { return false; }, "never holds");
    bool propagated = false;
    try { static_cast<void>(checked_failing(-1)); }
    catch (const std::out_of_range&) { propagated = true; }
    require(propagated && installed.count == 7);

    // A predicate that throws is a violation, not an escape.
    const auto checked_throwing = LORICA_CONTRACT(square).pre(&throwing_predicate, "throws");
    require(checked_throwing(2) == 4 && installed.count == 8);
    require(installed.mode == detection_mode::evaluation_exception);

    // An overlay's own delegate replaces the installed handler for that overlay.
    recorded own;
    const auto delegated = checked_divide.on_violation(
        [&own](const contract_violation& violation) { record(own, violation); });
    require(delegated(1, 0) == 0);
    require(own.count == 1 && own.comment == "divisor is not zero" && installed.count == 8);
    require(checked_divide(1, 0) == 0 && installed.count == 9 && own.count == 1);

    // A delegate may throw: a refused call then never reaches the callable.
    const auto strict = checked_divide.on_violation(
        [](const contract_violation&) { throw delegate_failure(); });
    const int calls_before = calls;
    bool refused = false;
    try { static_cast<void>(strict(1, 0)); }
    catch (const delegate_failure&) { refused = true; }
    require(refused && calls == calls_before);
    // ...and the re-entry guard was reset during unwinding.
    require(strict(4, 2) == 2 && checked_divide(1, 0) == 0 && installed.count == 10);

    // The conditions as a test oracle: reported, not handled; a refused call is not made.
    const int handled = installed.count;
    const int called = calls;
    require(static_cast<bool>(checked_divide.test(6, 3)) && calls == called + 1);
    const test_result refused_divisor = checked_divide.test(6, 0);
    require(!refused_divisor && refused_divisor.status == test_status::precondition_failed);
    require(std::string(refused_divisor.condition) == "divisor is not zero" && calls == called + 1);
    // Of several conditions that do not hold, the first is the one reported.
    require(std::string(checked_divide.test(-6, 0).condition) == "divisor is not zero");
    require(std::string(checked_divide.test(-6, 2).condition) == "dividend is not negative");
    const test_result broken = wrong.test(6, 3);
    require(broken.status == test_status::postcondition_failed);
    require(std::string(broken.condition) == "quotient is negative");
    require(checked_divide.test(6, 3).condition == nullptr);
    require(installed.count == handled && own.count == 1);

    // An overlay with a semantic of its own, whatever this unit is built with.
    const auto silent = LORICA_CONTRACT_WITH(ignore, divide)
        .pre([](int, int) { return false; }, "never holds");
    const auto silent_slot = LORICA_CONTRACT_WITH(ignore, slot);
    static_assert(noexcept(silent_slot(object)), "ignore adds nothing that can throw");
    static_assert(!noexcept(checked_slot(object)), "a handler may throw when checking");
    require(silent(8, 2) == 4 && installed.count == handled);
    require(silent.test(8, 2).status == test_status::precondition_failed);

    require(set_violation_handler(nullptr) == &installed_handler);
}
