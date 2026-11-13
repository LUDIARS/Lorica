#pragma once

#include <lorica/contract_violation.hpp>
#include <cstdint>
#include <exception>
#include <type_traits>
#if defined(_WIN32) && defined(_MSC_VER)
#include <intrin.h>
#endif

// @implements SPEC-LR-CONTRACTS
// Statement-level emulation of C++26 contracts (P2900): LORICA_PRE, LORICA_POST,
// LORICA_POST_RETURN and LORICA_CONTRACT_ASSERT. Contracts state invariants of
// correct programs; they are not input validation. Reject hostile input with
// ordinary error paths (Lorica::boundary) and reserve contracts for bugs.
//
// The evaluation semantic is chosen per translation unit, before this header:
//   -DLORICA_CONTRACT_EVALUATION_SEMANTIC=ignore|observe|enforce|quick_enforce
// The default is enforce. Use one semantic per program for inline and template
// code: mixing is the P2900 "mixed mode" and the kept definition is unspecified.
#ifndef LORICA_CONTRACT_EVALUATION_SEMANTIC
#define LORICA_CONTRACT_EVALUATION_SEMANTIC enforce
#endif

#if defined(__cpp_exceptions) || defined(__EXCEPTIONS) || (defined(_MSC_VER) && defined(_CPPUNWIND))
#define LORICA_DETAIL_CONTRACT_EXCEPTIONS 1
#else
#define LORICA_DETAIL_CONTRACT_EXCEPTIONS 0
#endif

#if defined(__cpp_lib_is_constant_evaluated)
#define LORICA_DETAIL_IS_CONSTANT_EVALUATED() (::std::is_constant_evaluated())
#elif defined(__has_builtin)
#if __has_builtin(__builtin_is_constant_evaluated)
#define LORICA_DETAIL_IS_CONSTANT_EVALUATED() (__builtin_is_constant_evaluated())
#endif
#endif
#if !defined(LORICA_DETAIL_IS_CONSTANT_EVALUATED) && defined(_MSC_VER) && _MSC_VER >= 1925
#define LORICA_DETAIL_IS_CONSTANT_EVALUATED() (__builtin_is_constant_evaluated())
#endif
#ifndef LORICA_DETAIL_IS_CONSTANT_EVALUATED
// Without detection, contracts run on the runtime path only and a constexpr
// function containing one cannot be constant-evaluated.
#define LORICA_DETAIL_IS_CONSTANT_EVALUATED() false
#endif

namespace lorica::contracts::detail {

// quick_enforce: terminate at the violation site with no handler, no I/O.
[[noreturn]] inline void trap() noexcept {
#if defined(_WIN32) && defined(_MSC_VER)
    __fastfail(7); // FAST_FAIL_FATAL_APP_EXIT
#else
    __builtin_trap();
#endif
}

// Deliberately not constexpr: reaching it during constant evaluation makes the
// enclosing constant expression ill-formed, which is the C++26 behaviour.
inline void contract_violated_during_constant_evaluation() noexcept { trap(); }

// One condition per contract: a second macro argument (a message, say) would
// otherwise be a comma expression whose value is the last operand.
template <class Condition>
constexpr bool holds(const Condition& condition) { return static_cast<bool>(condition); }

template <evaluation_semantic Semantic, class Predicate>
void evaluate_at_runtime(assertion_kind kind, Predicate& predicate, const char* comment,
                         source_location location, violation_sink sink, const void* context) {
#if LORICA_DETAIL_CONTRACT_EXCEPTIONS
    bool satisfied = false;
    try {
        satisfied = predicate();
    } catch (...) {
        // As P2900: the handler runs inside the handler of the predicate's exception.
        if constexpr (Semantic == evaluation_semantic::quick_enforce) {
            trap();
        } else {
            handle_violation(sink, context, kind, Semantic, detection_mode::evaluation_exception,
                             comment, location, std::current_exception());
            return;
        }
    }
#else
    const bool satisfied = predicate();
#endif
    if (satisfied) return;
    if constexpr (Semantic == evaluation_semantic::quick_enforce) {
        trap();
    } else {
        handle_violation(sink, context, kind, Semantic, detection_mode::predicate_false, comment,
                         location, std::exception_ptr());
    }
}

// sink and context name an overlay's own delegate; null means the installed handler.
template <evaluation_semantic Semantic, class Predicate>
constexpr void check(assertion_kind kind, Predicate&& predicate, const char* comment,
                     source_location location, violation_sink sink = nullptr,
                     const void* context = nullptr) {
    if constexpr (Semantic == evaluation_semantic::ignore) {
        // The predicate stays well-formed (it was compiled) but is never evaluated.
        static_cast<void>(kind);
        static_cast<void>(predicate);
        static_cast<void>(comment);
        static_cast<void>(location);
        static_cast<void>(sink);
        static_cast<void>(context);
    } else {
        if (LORICA_DETAIL_IS_CONSTANT_EVALUATED()) {
            if (!predicate()) contract_violated_during_constant_evaluation();
            return;
        }
        evaluate_at_runtime<Semantic>(kind, predicate, comment, location, sink, context);
    }
}

// Postcondition on a returned value: check, then pass it on as an lvalue stays an
// lvalue and an rvalue becomes a value (one move), so no reference to a temporary
// leaves the return statement, whatever the function's return type deduces to.
template <evaluation_semantic Semantic, class Value, class Predicate>
constexpr Value check_result(Value&& value, Predicate&& predicate, const char* comment,
                               source_location location) {
    using viewed = const std::remove_reference_t<Value>&;
    check<Semantic>(
        assertion_kind::post,
        [&]() -> bool { return predicate(static_cast<viewed>(value)); }, comment, location);
    return static_cast<Value&&>(value);
}

// Postcondition without a result: evaluated when the scope exits normally.
// Exceptional exit skips the check, as P2900 checks postconditions on return only.
template <evaluation_semantic Semantic, class Predicate>
class post_guard final {
public:
    post_guard(Predicate predicate, const char* comment, source_location location) noexcept(
        std::is_nothrow_move_constructible_v<Predicate>)
        : predicate_(static_cast<Predicate&&>(predicate)), comment_(comment), location_(location)
#if LORICA_DETAIL_CONTRACT_EXCEPTIONS
          , exceptions_on_entry_(Semantic == evaluation_semantic::ignore
                                     ? 0 : std::uncaught_exceptions())
#endif
    {
    }
    post_guard(const post_guard&) = delete;
    post_guard& operator=(const post_guard&) = delete;
    post_guard(post_guard&&) = delete;
    post_guard& operator=(post_guard&&) = delete;

    // An observe handler may throw; that exception leaves the function normally.
    ~post_guard() noexcept(false) {
        // ignore asks nothing of the library, whose uncaught_exceptions may not be pure.
        if constexpr (Semantic != evaluation_semantic::ignore) {
#if LORICA_DETAIL_CONTRACT_EXCEPTIONS
            if (std::uncaught_exceptions() != exceptions_on_entry_) return;
#endif
            check<Semantic>(assertion_kind::post, predicate_, comment_, location_);
        }
    }

private:
    Predicate predicate_;
    const char* comment_;
    source_location location_;
#if LORICA_DETAIL_CONTRACT_EXCEPTIONS
    int exceptions_on_entry_;
#endif
};

template <evaluation_semantic Semantic, class Predicate>
post_guard<Semantic, std::decay_t<Predicate>> make_post_guard(Predicate&& predicate,
                                                              const char* comment,
                                                              source_location location) {
    return post_guard<Semantic, std::decay_t<Predicate>>(static_cast<Predicate&&>(predicate),
                                                         comment, location);
}
} // namespace lorica::contracts::detail

#define LORICA_DETAIL_CONTRACT_SEMANTIC \
    ::lorica::contracts::evaluation_semantic::LORICA_CONTRACT_EVALUATION_SEMANTIC
#define LORICA_DETAIL_CONTRACT_LOCATION \
    ::lorica::contracts::source_location{__FILE__, __func__, \
                                         static_cast<::std::uint_least32_t>(__LINE__)}
#define LORICA_DETAIL_CONTRACT_CONCAT_(left, right) left##right
#define LORICA_DETAIL_CONTRACT_CONCAT(left, right) LORICA_DETAIL_CONTRACT_CONCAT_(left, right)
#define LORICA_DETAIL_CONTRACT_CHECK(kind, ...) \
    ::lorica::contracts::detail::check<LORICA_DETAIL_CONTRACT_SEMANTIC>( \
        ::lorica::contracts::assertion_kind::kind, \
        [&]() -> bool { return ::lorica::contracts::detail::holds(__VA_ARGS__); }, #__VA_ARGS__, \
        LORICA_DETAIL_CONTRACT_LOCATION)

// Precondition. Place first in the function body.
#define LORICA_PRE(...) LORICA_DETAIL_CONTRACT_CHECK(pre, __VA_ARGS__)

// Assertion inside a body (C++26 contract_assert).
#define LORICA_CONTRACT_ASSERT(...) LORICA_DETAIL_CONTRACT_CHECK(assert, __VA_ARGS__)

// Postcondition checked when the enclosing scope exits by return or fall-off.
// Declare it before the locals the predicate must not see; it sees parameters and
// earlier locals by reference. Not usable in constant evaluation. It runs after the
// return value has been constructed: a parameter or local that the return statement
// moves from is seen moved-from; state a condition on the result with
// LORICA_POST_RETURN.
#define LORICA_POST(...) \
    const auto LORICA_DETAIL_CONTRACT_CONCAT(lorica_post_guard_, __COUNTER__) = \
        ::lorica::contracts::detail::make_post_guard<LORICA_DETAIL_CONTRACT_SEMANTIC>( \
            [&]() -> bool { return ::lorica::contracts::detail::holds(__VA_ARGS__); }, #__VA_ARGS__, \
            LORICA_DETAIL_CONTRACT_LOCATION)

// Postcondition on a result: `return LORICA_POST_RETURN(expr, r, r >= 0);`
// Parenthesize `expr` if it contains a top-level comma. Usable in constexpr. In every
// semantic it copies an lvalue (write std::move(local) to move it) and moves an
// rvalue once, so a type that cannot be moved cannot pass through it.
#define LORICA_POST_RETURN(expression, name, ...) \
    ::lorica::contracts::detail::check_result<LORICA_DETAIL_CONTRACT_SEMANTIC>( \
        expression, [&](const auto& name) -> bool { return ::lorica::contracts::detail::holds(__VA_ARGS__); }, \
        #__VA_ARGS__, LORICA_DETAIL_CONTRACT_LOCATION)
