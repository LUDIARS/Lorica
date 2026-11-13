#pragma once

#include <lorica/contracts.hpp>
#include <cstdint>
#include <functional>
#include <tuple>
#include <type_traits>
#include <utility>

// @implements SPEC-LR-CONTRACT-OVERLAY
// A contract laid over an existing callable from outside, without editing it:
//
//   int divide(int dividend, int divisor);                    // unchanged
//   const auto checked_divide = LORICA_CONTRACT(divide)
//       .pre([](int, int divisor) { return divisor != 0; }, "divisor is not zero")
//       .post([](int quotient, int dividend, int divisor) {   // result first
//           return quotient * divisor <= dividend; }, "quotient is rounded down");
//   checked_divide(6, 3);                  // same call, same result as divide(6, 3)
//   checked_divide.test(1, 0);             // precondition_failed; divide not called
//
// While its conditions hold, the overlay is the callable: same arguments (perfectly
// forwarded), same result type, same exceptions. A violated condition is handled
// by the evaluation semantic exactly as for LORICA_PRE and LORICA_POST. Removing
// the overlay, or building with the ignore semantic, restores the original call.
// The conditions are also the callable's test oracle: test() evaluates them
// under every semantic, reports instead of handling, and never calls the callable
// with arguments its preconditions refuse.
namespace lorica::contracts {

// What overlay::test found for one set of arguments.
enum class test_status : int { satisfied = 0, precondition_failed = 1, postcondition_failed = 2 };

struct test_result final {
    test_status status;
    // The message of the first condition that did not hold; null when satisfied.
    const char* condition;
    [[nodiscard]] constexpr explicit operator bool() const noexcept {
        return status == test_status::satisfied;
    }
};

namespace detail {
template <class Predicate>
struct condition final {
    Predicate predicate;
    const char* message;
};

struct no_delegate final {};

// std::invoke is constexpr only from C++20. Calling other callables directly keeps
// an overlay over a constexpr function usable in constant evaluation in C++17.
template <class Callable, class... Args>
constexpr decltype(auto) call(Callable&& callable, Args&&... args) {
    if constexpr (std::is_member_pointer_v<std::decay_t<Callable>>) {
        return std::invoke(static_cast<Callable&&>(callable), static_cast<Args&&>(args)...);
    } else {
        return static_cast<Callable&&>(callable)(static_cast<Args&&>(args)...);
    }
}

// Whether every predicate of Conditions takes Values by const reference.
template <class Conditions, class... Values>
struct accepts : std::false_type {};
template <class... Predicates, class... Values>
struct accepts<std::tuple<condition<Predicates>...>, Values...>
    : std::conjunction<std::is_invocable_r<bool, const Predicates&, const Values&...>...> {};

// The same for postconditions, which take the result first unless it is void.
template <class Result, class Conditions, class... Values>
struct accepts_after : accepts<Conditions, std::remove_reference_t<Result>, Values...> {};
template <class Conditions, class... Values>
struct accepts_after<void, Conditions, Values...> : accepts<Conditions, Values...> {};

// The message of the first condition that does not hold, or null.
template <class Conditions, class... Values>
constexpr const char* first_failed(const Conditions& conditions, const Values&... values) {
    const char* failed = nullptr;
    std::apply(
        [&](const auto&... each) {
            static_cast<void>(((static_cast<bool>(each.predicate(values...))
                                    ? false
                                    : (static_cast<void>(failed = each.message), true)) || ...));
        },
        conditions);
    return failed;
}
} // namespace detail

template <evaluation_semantic Semantic, class Callable, class Pre, class Post, class Delegate>
class overlay;

// Starts an overlay; normally spelled LORICA_CONTRACT(callable). The callable is
// held by value (a function decays to a pointer); wrap an object that must stay in
// place, or whose call operator is not const, in std::ref.
template <evaluation_semantic Semantic, class Callable>
[[nodiscard]] constexpr auto contract(Callable&& callable, source_location location) {
    return overlay<Semantic, std::decay_t<Callable>, std::tuple<>, std::tuple<>,
                   detail::no_delegate>(static_cast<Callable&&>(callable), std::tuple<>(),
                                        std::tuple<>(), detail::no_delegate(), location);
}

// Immutable once built: pre, post and on_violation each return a new overlay.
// Concurrent calls are as safe as the callable, the predicates and the delegate are.
template <evaluation_semantic Semantic, class Callable, class Pre, class Post, class Delegate>
class overlay final {
public:
    // Adds a precondition: a predicate over the arguments (taken by const
    // reference). message names it in a violation and in test results; it is not
    // copied, so it must outlive the overlay (normally a string literal).
    template <class Predicate>
    [[nodiscard]] constexpr auto pre(Predicate predicate, const char* message) && {
        return rebuild(std::move(callable_),
                       extend(std::move(pre_), std::move(predicate), message), std::move(post_),
                       std::move(delegate_));
    }
    template <class Predicate>
    [[nodiscard]] constexpr auto pre(Predicate predicate, const char* message) const& {
        return overlay(*this).pre(std::move(predicate), message);
    }

    // Adds a postcondition, checked when the callable returns normally: a predicate
    // over the result (omitted for void) followed by the arguments as the call left
    // them, so an argument the callable moved from or wrote through is seen changed.
    template <class Predicate>
    [[nodiscard]] constexpr auto post(Predicate predicate, const char* message) && {
        return rebuild(std::move(callable_), std::move(pre_),
                       extend(std::move(post_), std::move(predicate), message),
                       std::move(delegate_));
    }
    template <class Predicate>
    [[nodiscard]] constexpr auto post(Predicate predicate, const char* message) const& {
        return overlay(*this).post(std::move(predicate), message);
    }

    // Sends this overlay's violations to delegate(const contract_violation&) in place
    // of the installed handler (observe and enforce only; enforce still terminates
    // when it returns). It replaces an earlier delegate and may throw.
    template <class Handler>
    [[nodiscard]] constexpr auto on_violation(Handler delegate) && {
        static_assert(std::is_invocable_v<const Handler&, const contract_violation&>,
                      "a violation delegate is called as delegate(const contract_violation&)");
        return rebuild(std::move(callable_), std::move(pre_), std::move(post_),
                       std::move(delegate));
    }
    template <class Handler>
    [[nodiscard]] constexpr auto on_violation(Handler delegate) const& {
        return overlay(*this).on_violation(std::move(delegate));
    }

    // Calls the callable. Each condition is one contract assertion of this
    // translation unit's evaluation semantic; ignore evaluates none of them.
    template <class... Args,
              class = std::enable_if_t<std::is_invocable_v<const Callable&, Args...>>>
    constexpr decltype(auto) operator()(Args&&... args) const
        noexcept(Semantic == evaluation_semantic::ignore &&
                 std::is_nothrow_invocable_v<const Callable&, Args...>) {
        using result_type = std::invoke_result_t<const Callable&, Args...>;
        require_callable_conditions<result_type, Args...>();
        if constexpr (Semantic == evaluation_semantic::ignore) {
            return detail::call(callable_, static_cast<Args&&>(args)...);
        } else {
            check(assertion_kind::pre, pre_, args...);
            if constexpr (std::tuple_size_v<Post> == 0) {
                return detail::call(callable_, static_cast<Args&&>(args)...);
            } else if constexpr (std::is_void_v<result_type>) {
                detail::call(callable_, static_cast<Args&&>(args)...);
                check(assertion_kind::post, post_, args...);
            } else {
                result_type result = detail::call(callable_, static_cast<Args&&>(args)...);
                check(assertion_kind::post, post_, result, args...);
                if constexpr (std::is_reference_v<result_type>) {
                    return static_cast<result_type>(result);
                } else {
                    return result;
                }
            }
        }
    }

    // The conditions as a test oracle, under every evaluation semantic: reports the
    // first condition that does not hold instead of handling a violation, and does
    // not call the callable when a precondition fails. The callable's result is
    // discarded; an exception from it or from a predicate propagates.
    template <class... Args,
              class = std::enable_if_t<std::is_invocable_v<const Callable&, Args...>>>
    [[nodiscard]] constexpr test_result test(Args&&... args) const {
        using result_type = std::invoke_result_t<const Callable&, Args...>;
        require_callable_conditions<result_type, Args...>();
        if (const char* failed = detail::first_failed(pre_, args...)) {
            return {test_status::precondition_failed, failed};
        }
        const char* failed = nullptr;
        if constexpr (std::is_void_v<result_type>) {
            detail::call(callable_, static_cast<Args&&>(args)...);
            failed = detail::first_failed(post_, args...);
        } else {
            result_type result = detail::call(callable_, static_cast<Args&&>(args)...);
            failed = detail::first_failed(post_, result, args...);
        }
        if (failed != nullptr) return {test_status::postcondition_failed, failed};
        return {test_status::satisfied, nullptr};
    }

private:
    template <evaluation_semantic OtherSemantic, class OtherCallable>
    friend constexpr auto contract(OtherCallable&& callable, source_location location);
    template <evaluation_semantic, class, class, class, class>
    friend class overlay;

    constexpr overlay(Callable callable, Pre pre, Post post, Delegate delegate,
                      source_location location)
        : callable_(std::move(callable)), pre_(std::move(pre)), post_(std::move(post)),
          delegate_(std::move(delegate)), location_(location) {}

    template <class... Predicates, class Predicate>
    static constexpr auto extend(std::tuple<detail::condition<Predicates>...> conditions,
                                 Predicate predicate, const char* message) {
        return std::tuple_cat(std::move(conditions),
                              std::tuple<detail::condition<Predicate>>(
                                  detail::condition<Predicate>{std::move(predicate), message}));
    }

    template <class NewPre, class NewPost, class NewDelegate>
    constexpr auto rebuild(Callable callable, NewPre pre, NewPost post,
                           NewDelegate delegate) const {
        return overlay<Semantic, Callable, NewPre, NewPost, NewDelegate>(
            std::move(callable), std::move(pre), std::move(post), std::move(delegate), location_);
    }

    // Checked under ignore too, so a stripped build cannot hide a condition whose
    // signature no longer matches the callable (a body is compiled only when called).
    template <class Result, class... Args>
    static constexpr void require_callable_conditions() noexcept {
        static_assert(detail::accepts<Pre, std::remove_reference_t<Args>...>::value,
                      "a precondition is not callable as bool(const Args&...)");
        static_assert(
            detail::accepts_after<Result, Post, std::remove_reference_t<Args>...>::value,
            "a postcondition is not callable as bool(const Result&, const Args&...)");
    }

    template <class Conditions, class... Values>
    constexpr void check(assertion_kind kind, const Conditions& conditions,
                         const Values&... values) const {
        std::apply(
            [&](const auto&... each) {
                (detail::check<Semantic>(
                     kind, [&]() -> bool { return static_cast<bool>(each.predicate(values...)); },
                     each.message, location_, sink(), &delegate_),
                 ...);
            },
            conditions);
    }

    constexpr detail::violation_sink sink() const noexcept {
        if constexpr (std::is_same_v<Delegate, detail::no_delegate>) {
            return nullptr;
        } else {
            return [](const void* context, const contract_violation& violation) {
                (*static_cast<const Delegate*>(context))(violation);
            };
        }
    }

    Callable callable_;
    Pre pre_;
    Post post_;
    Delegate delegate_;
    source_location location_;
};
} // namespace lorica::contracts

// An overlay with this translation unit's evaluation semantic. A violation names
// the callable as written here, and this file and line.
#define LORICA_CONTRACT(...) \
    LORICA_CONTRACT_WITH(LORICA_CONTRACT_EVALUATION_SEMANTIC, __VA_ARGS__)

// An overlay with a semantic of its own (ignore, observe, enforce or
// quick_enforce), for example a test that observes a product built with ignore.
#define LORICA_CONTRACT_WITH(overlay_semantic, ...) \
    ::lorica::contracts::contract<::lorica::contracts::evaluation_semantic::overlay_semantic>( \
        __VA_ARGS__, ::lorica::contracts::source_location{ \
                         __FILE__, #__VA_ARGS__, static_cast<::std::uint_least32_t>(__LINE__)})
