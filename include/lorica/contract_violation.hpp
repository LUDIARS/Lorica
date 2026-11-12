#pragma once

#include <cstdint>
#include <exception>

#if defined(_WIN32)
#  if defined(LORICA_BUILDING_CONTRACTS)
#    define LORICA_CONTRACTS_API __declspec(dllexport)
#  else
#    define LORICA_CONTRACTS_API __declspec(dllimport)
#  endif
#else
#  define LORICA_CONTRACTS_API __attribute__((visibility("default")))
#endif

// @implements SPEC-LR-CONTRACTS
// Library emulation of the C++26 contract-violation model (P2900, <contracts>).
// Names and values mirror std::contracts so that call sites can migrate when the
// toolchain ships native pre/post/contract_assert. Nothing here is in namespace std.
namespace lorica::contracts {

enum class assertion_kind : int { pre = 1, post = 2, assert = 3 };

enum class evaluation_semantic : int { ignore = 1, observe = 2, enforce = 3, quick_enforce = 4 };

enum class detection_mode : int { predicate_false = 1, evaluation_exception = 2 };

// C++17-compatible location. Strings are the static literals of the call site.
struct source_location final {
    const char* file;
    const char* function;
    std::uint_least32_t line_number;

    [[nodiscard]] constexpr const char* file_name() const noexcept { return file; }
    [[nodiscard]] constexpr const char* function_name() const noexcept { return function; }
    [[nodiscard]] constexpr std::uint_least32_t line() const noexcept { return line_number; }
};

// Passed by const reference to the handler; never copied (as std::contracts).
class contract_violation final {
public:
    contract_violation(assertion_kind kind, evaluation_semantic semantic, detection_mode mode,
                       const char* comment, source_location location,
                       std::exception_ptr evaluation_exception) noexcept
        : kind_(kind), semantic_(semantic), mode_(mode), comment_(comment),
          location_(location), evaluation_exception_(evaluation_exception) {}
    contract_violation(const contract_violation&) = delete;
    contract_violation& operator=(const contract_violation&) = delete;

    [[nodiscard]] assertion_kind kind() const noexcept { return kind_; }
    [[nodiscard]] evaluation_semantic semantic() const noexcept { return semantic_; }
    [[nodiscard]] detection_mode mode() const noexcept { return mode_; }
    // The predicate as written at the call site.
    [[nodiscard]] const char* comment() const noexcept { return comment_; }
    [[nodiscard]] source_location location() const noexcept { return location_; }
    // Non-null only for detection_mode::evaluation_exception.
    [[nodiscard]] std::exception_ptr evaluation_exception() const noexcept {
        return evaluation_exception_;
    }
    // True for enforce: the program terminates if the handler returns.
    [[nodiscard]] bool is_terminating() const noexcept {
        return semantic_ == evaluation_semantic::enforce ||
               semantic_ == evaluation_semantic::quick_enforce;
    }

private:
    assertion_kind kind_;
    evaluation_semantic semantic_;
    detection_mode mode_;
    const char* comment_;
    source_location location_;
    std::exception_ptr evaluation_exception_;
};

// A handler may return (observe continues, enforce then aborts) or throw (the
// exception propagates out of the checking site, as P2900 permits).
using violation_handler = void (*)(const contract_violation&);

// Process-wide replacement point, the library analogue of the replaceable
// ::handle_contract_violation. nullptr restores the default. Returns the previous
// handler (nullptr when the default was active). Install during startup.
LORICA_CONTRACTS_API violation_handler set_violation_handler(violation_handler handler) noexcept;
[[nodiscard]] LORICA_CONTRACTS_API violation_handler get_violation_handler() noexcept;

// Writes one line to stderr without allocating: location, kind, semantic, predicate.
LORICA_CONTRACTS_API void invoke_default_contract_violation_handler(
    const contract_violation& violation) noexcept;

[[nodiscard]] LORICA_CONTRACTS_API const char* to_string(assertion_kind kind) noexcept;
[[nodiscard]] LORICA_CONTRACTS_API const char* to_string(evaluation_semantic semantic) noexcept;
[[nodiscard]] LORICA_CONTRACTS_API const char* to_string(detection_mode mode) noexcept;

namespace detail {
// Called by the checking templates on a runtime violation of an observe/enforce
// contract. Returns only for observe; enforce aborts after the handler returns.
// A violation raised while a handler runs on the same thread aborts immediately.
LORICA_CONTRACTS_API void handle_violation(
    assertion_kind kind, evaluation_semantic semantic, detection_mode mode,
    const char* comment, source_location location, std::exception_ptr evaluation_exception);
} // namespace detail
} // namespace lorica::contracts

#undef LORICA_CONTRACTS_API
