#include <lorica/contract_violation.hpp>
#include <atomic>
#include <cstdio>
#include <cstdlib>

namespace lorica::contracts {
namespace {
// The one process-wide mutable value in Lorica, the analogue of std::set_terminate.
std::atomic<violation_handler> installed_handler{nullptr};

// Re-entry guard: a violation raised while this thread runs a handler aborts.
thread_local bool handling_violation = false;

class handler_scope final {
public:
    handler_scope() noexcept { handling_violation = true; }
    ~handler_scope() { handling_violation = false; }
    handler_scope(const handler_scope&) = delete;
    handler_scope& operator=(const handler_scope&) = delete;
};

void write_text(const char* text) noexcept {
    std::fputs(text != nullptr ? text : "(null)", stderr);
}
} // namespace

// @implements SPEC-LR-CONTRACTS
violation_handler set_violation_handler(violation_handler handler) noexcept {
    return installed_handler.exchange(handler, std::memory_order_acq_rel);
}

// @implements SPEC-LR-CONTRACTS
violation_handler get_violation_handler() noexcept {
    return installed_handler.load(std::memory_order_acquire);
}

// @implements SPEC-LR-CONTRACTS
const char* to_string(assertion_kind kind) noexcept {
    switch (kind) {
    case assertion_kind::pre: return "pre";
    case assertion_kind::post: return "post";
    case assertion_kind::assert: return "contract_assert";
    }
    return "unknown";
}

// @implements SPEC-LR-CONTRACTS
const char* to_string(evaluation_semantic semantic) noexcept {
    switch (semantic) {
    case evaluation_semantic::ignore: return "ignore";
    case evaluation_semantic::observe: return "observe";
    case evaluation_semantic::enforce: return "enforce";
    case evaluation_semantic::quick_enforce: return "quick_enforce";
    }
    return "unknown";
}

// @implements SPEC-LR-CONTRACTS
const char* to_string(detection_mode mode) noexcept {
    switch (mode) {
    case detection_mode::predicate_false: return "predicate false";
    case detection_mode::evaluation_exception: return "predicate threw";
    }
    return "unknown";
}

// @implements SPEC-LR-CONTRACTS
void invoke_default_contract_violation_handler(const contract_violation& violation) noexcept {
    const source_location location = violation.location();
    const auto text = [](const char* value) { return value != nullptr ? value : "(null)"; };
    // One call holds the stream lock for the whole line: concurrent violations
    // do not interleave.
    std::fprintf(stderr, "%s:%lu: %s: contract violation: %s (%s, %s): %s\n",
                 text(location.file_name()), static_cast<unsigned long>(location.line()),
                 text(location.function_name()), to_string(violation.kind()),
                 to_string(violation.semantic()), to_string(violation.mode()),
                 text(violation.comment()));
    std::fflush(stderr);
}

namespace detail {
// @implements SPEC-LR-CONTRACTS
void handle_violation(violation_sink sink, const void* context, assertion_kind kind,
                      evaluation_semantic semantic, detection_mode mode, const char* comment,
                      source_location location, std::exception_ptr evaluation_exception) {
    const contract_violation violation(kind, semantic, mode, comment, location,
                                       evaluation_exception);
    if (handling_violation) {
        // Typically a contract inside the handler itself; never recurse.
        write_text("lorica: contract violated while handling a contract violation\n");
        invoke_default_contract_violation_handler(violation);
        std::abort();
    }
    {
        const handler_scope scope;
        // Either call may throw; the scope resets the guard while unwinding.
        if (sink != nullptr) {
            sink(context, violation);
        } else if (const violation_handler handler = get_violation_handler()) {
            handler(violation);
        } else {
            invoke_default_contract_violation_handler(violation);
        }
    }
    if (violation.is_terminating()) std::abort(); // Contract-terminated: no unwinding.
}
} // namespace detail
} // namespace lorica::contracts
