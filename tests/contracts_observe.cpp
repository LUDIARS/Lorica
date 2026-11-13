// Built with LORICA_CONTRACT_EVALUATION_SEMANTIC=observe, at C++17, C++20 and C++23.
#include <lorica/contracts.hpp>
#include <cstdlib>
#include <cstring>
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
    unsigned long line = 0;
    bool terminating = true;
    bool has_exception = false;
    bool in_handler = false;
};
recorded last;
bool throw_from_handler = false;

struct handler_failure final : std::runtime_error {
    handler_failure() : std::runtime_error("handler") {}
};

// @implements SPEC-LR-VERIFY
void recording_handler(const lorica::contracts::contract_violation& violation) {
    ++last.count;
    last.kind = violation.kind();
    last.semantic = violation.semantic();
    last.mode = violation.mode();
    last.comment = violation.comment();
    last.function = violation.location().function_name();
    last.line = violation.location().line();
    last.terminating = violation.is_terminating();
    last.has_exception = static_cast<bool>(violation.evaluation_exception());
    last.in_handler = static_cast<bool>(std::current_exception());
    if (throw_from_handler) throw handler_failure();
}

// @implements SPEC-LR-VERIFY
unsigned long halve_line = 0;
// @implements SPEC-LR-VERIFY
int halve(int value) {
    halve_line = __LINE__; LORICA_PRE(value % 2 == 0);
    return value / 2;
}

// @implements SPEC-LR-VERIFY
constexpr int positive_square(int value) {
    LORICA_PRE(value > 0);
    return LORICA_POST_RETURN(value * value, r, r >= value);
}
// Satisfied contracts are usable in constant evaluation. A violated one
// (positive_square(0) in a constant expression) does not compile.
static_assert(positive_square(3) == 9, "constexpr contracts");
// LR-CONTRACT-08, asked without failing the build: a call whose contract is
// violated is not a constant expression, so it cannot be a template argument.
template <int Value, int = (static_cast<void>(positive_square(Value)), 0)>
constexpr bool constant_evaluable(int) { return true; }
template <int Value> constexpr bool constant_evaluable(long) { return false; }
static_assert(constant_evaluable<3>(0) && !constant_evaluable<0>(0), "violated in constant evaluation");

// A result postcondition never turns a temporary into a reference to it.
// @implements SPEC-LR-VERIFY
decltype(auto) made() { return LORICA_POST_RETURN(std::string(3, 'x'), r, !r.empty()); }
static_assert(std::is_same_v<decltype(made()), std::string>, "an rvalue is returned by value");
// @implements SPEC-LR-VERIFY
decltype(auto) same(int& value) { return LORICA_POST_RETURN(value, r, r >= 0); }
static_assert(std::is_same_v<decltype(same(std::declval<int&>())), int&>, "an lvalue stays one");

// @implements SPEC-LR-VERIFY
int doubled(int value) { return LORICA_POST_RETURN(value * 2, r, r > 0); }

int post_side_effect = 0;
// @implements SPEC-LR-VERIFY
void ensure_positive(int& target, bool fail, bool raise) {
    LORICA_POST(target > 0);
    ++post_side_effect;
    if (raise) throw std::runtime_error("exceptional exit");
    target = fail ? -1 : 1;
}

// @implements SPEC-LR-VERIFY
bool throwing_predicate() { throw std::runtime_error("predicate"); }

// @implements SPEC-LR-VERIFY
void assert_throwing() { LORICA_CONTRACT_ASSERT(throwing_predicate()); }

// @implements SPEC-LR-VERIFY
void nested_handler(const lorica::contracts::contract_violation&) {
    ++last.count;
}
} // namespace

// @implements SPEC-LR-VERIFY
int main() {
    using namespace lorica::contracts;
    require(get_violation_handler() == nullptr);
    require(set_violation_handler(&recording_handler) == nullptr);
    require(get_violation_handler() == &recording_handler);

    // Satisfied precondition: no handler call.
    require(halve(4) == 2 && last.count == 0);

    // Violated precondition under observe: handler runs, execution continues.
    require(halve(3) == 1);
    require(last.count == 1);
    require(last.kind == assertion_kind::pre);
    require(last.semantic == evaluation_semantic::observe);
    require(last.mode == detection_mode::predicate_false);
    require(last.comment == "value % 2 == 0");
    require(last.function == "halve");
    require(last.line == halve_line);
    require(!last.terminating && !last.has_exception);

    // Result postcondition at runtime.
    int target_for_same = 1;
    require(positive_square(2) == 4 && last.count == 1);
    require(positive_square(-2) == 4);
    require(last.count == 2 && last.kind == assertion_kind::pre);
    // A violated result postcondition is reported as post and the value still returns.
    require(doubled(2) == 4 && last.count == 2);
    require(made() == "xxx" && &same(target_for_same) == &target_for_same && last.count == 2);
    require(doubled(-2) == -4 && last.count == 3);
    require(last.kind == assertion_kind::post && last.comment == "r > 0");
    last.count = 2;

    // Scope postcondition: checked on normal return, skipped on exceptional exit.
    int target = 0;
    ensure_positive(target, false, false);
    require(target == 1 && last.count == 2);
    ensure_positive(target, true, false);
    require(last.count == 3 && last.kind == assertion_kind::post);
    require(last.comment == "target > 0");
    target = -5;
    bool propagated = false;
    try { ensure_positive(target, false, true); }
    catch (const std::runtime_error&) { propagated = true; }
    require(propagated && last.count == 3 && post_side_effect == 3);

    // A throwing predicate is an evaluation_exception violation, not an escape.
    assert_throwing();
    require(last.count == 4 && last.kind == assertion_kind::assert);
    require(last.mode == detection_mode::evaluation_exception && last.has_exception);
    // ...handled inside the handler of that exception, so `throw;` reaches it there.
    require(last.in_handler);

    // An observe handler may throw; the exception leaves the checking site.
    throw_from_handler = true;
    bool handler_threw = false;
    try { static_cast<void>(halve(5)); }
    catch (const handler_failure&) { handler_threw = true; }
    require(handler_threw && last.count == 5);
    // ...and the re-entry guard was reset during unwinding.
    throw_from_handler = false;
    require(halve(7) == 3 && last.count == 6);

    // Replacing and restoring the handler.
    require(set_violation_handler(&nested_handler) == &recording_handler);
    static_cast<void>(halve(9));
    require(last.count == 7);
    require(set_violation_handler(nullptr) == &nested_handler);
    require(get_violation_handler() == nullptr);

    require(std::strcmp(to_string(assertion_kind::pre), "pre") == 0);
    require(std::strcmp(to_string(assertion_kind::post), "post") == 0);
    require(std::strcmp(to_string(assertion_kind::assert), "contract_assert") == 0);
    require(std::strcmp(to_string(evaluation_semantic::ignore), "ignore") == 0);
    require(std::strcmp(to_string(evaluation_semantic::observe), "observe") == 0);
    require(std::strcmp(to_string(evaluation_semantic::enforce), "enforce") == 0);
    require(std::strcmp(to_string(evaluation_semantic::quick_enforce), "quick_enforce") == 0);
    require(std::strcmp(to_string(detection_mode::predicate_false), "predicate false") == 0);
    require(std::strcmp(to_string(detection_mode::evaluation_exception), "predicate threw") == 0);
}
