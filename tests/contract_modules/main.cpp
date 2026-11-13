#include <lorica/contract_violation.hpp>
#include <cstdio>
#include <cstdlib>
#include <string_view>
#include <thread>

using lorica::contracts::contract_violation;
using lorica::contracts::violation_handler;

namespace module_a {
violation_handler set(violation_handler) noexcept;
violation_handler get() noexcept;
void violate();
}
namespace module_b {
violation_handler set(violation_handler) noexcept;
violation_handler get() noexcept;
void violate();
}

namespace {
int first_calls = 0;
int second_calls = 0;
void first(const contract_violation&) { ++first_calls; }
void second(const contract_violation&) { ++second_calls; }

// Runs on the violating thread, then once more on a thread it starts and joins.
int nested_calls = 0;
void nesting(const contract_violation&) {
    if (++nested_calls != 1) return;
    std::thread other([] { module_b::violate(); });
    other.join();
}

void require(bool condition, const char* message) {
    if (!condition) {
        std::fprintf(stderr, "%s\n", message);
        std::exit(EXIT_FAILURE);
    }
}
}

int main(int argc, char** argv) {
    require(argc == 2, "expected shared, split or probe");
    const std::string_view expected(argv[1]);
    require(expected == "shared" || expected == "split" || expected == "probe",
            "unknown expectation");

    require(!module_a::get() && !module_b::get(), "initial handlers must be null");
    require(!module_a::set(first) && module_a::get() == first, "install in A");
    const auto seen_by_b = module_b::get();
    require(!seen_by_b || seen_by_b == first, "unexpected handler in B");
    const bool shared = seen_by_b == first;
    std::printf("B.get() after A.set(first): %s\n", shared ? "first (shared)" : "null (split)");

    require(module_b::set(second) == seen_by_b, "previous handler returned by B");
    require(module_b::get() == second, "replacement in B");
    require(module_a::get() == (shared ? second : first), "B replacement as seen by A");
    module_a::violate();
    module_b::violate();
    require(first_calls == (shared ? 0 : 1) && second_calls == (shared ? 2 : 1),
            "observe dispatch disagrees with get()");
    require(module_a::set(nullptr) == (shared ? second : first), "A reset return value");
    require(!module_a::get(), "reset in A");
    require(module_b::get() == (shared ? nullptr : second), "A reset as seen by B");
    require(module_b::set(nullptr) == (shared ? nullptr : second), "B reset return value");
    require(!module_b::get(), "reset in B");
    if (shared) {
        // Exchanges on two threads must agree on one of the two possible orders.
        violation_handler previous_a = nullptr;
        std::thread writer([&] { previous_a = module_a::set(first); });
        const auto previous_b = module_b::set(second);
        writer.join();
        const bool a_first = !previous_a && previous_b == first;
        const bool b_first = !previous_b && previous_a == second;
        require(a_first || b_first, "exchanges did not form a single order");
        require(module_a::get() == module_b::get(), "final handlers differ");
        require(module_a::set(nullptr) == (a_first ? second : first), "last writer lost");
        // The re-entry guard is per thread: a violation on another thread while a
        // handler runs here is handled, not treated as recursion.
        module_a::set(nesting);
        module_a::violate();
        require(nested_calls == 2, "a violation on a second thread was not handled");
        module_a::set(nullptr);
    }
    require(expected == "probe" || expected == (shared ? "shared" : "split"),
            "observed handler state differs from expected");
}
