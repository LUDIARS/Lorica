#include <lorica/contract_violation.hpp>
#include <cstdio>
#include <cstdlib>
#include <string_view>

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
    require(expected == "probe" || expected == (shared ? "shared" : "split"),
            "observed handler state differs from expected");
}
