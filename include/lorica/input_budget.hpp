#pragma once

#include <cstddef>

namespace lorica {
struct budget_limits {
    std::size_t bytes;
    std::size_t elements;
    std::size_t allocations;
    std::size_t depth;
};

// One request owns one budget. External synchronization is required if shared.
// Cumulative charges are intentionally not refunded when memory is freed.
class input_budget final {
public:
    explicit constexpr input_budget(budget_limits limits) noexcept : remaining_(limits) {}

    [[nodiscard]] constexpr bool consume(std::size_t bytes, std::size_t elements,
                                         std::size_t allocations) noexcept {
        if (bytes > remaining_.bytes || elements > remaining_.elements ||
            allocations > remaining_.allocations) return false;
        remaining_.bytes -= bytes;
        remaining_.elements -= elements;
        remaining_.allocations -= allocations;
        return true;
    }

    // Caller supplies the actual nesting depth before descending. This avoids
    // exporting a lifetime-sensitive RAII token; it does not observe recursion.
    [[nodiscard]] constexpr bool permits_depth(std::size_t depth) const noexcept {
        return depth <= remaining_.depth;
    }
    [[nodiscard]] constexpr budget_limits remaining() const noexcept { return remaining_; }

private:
    budget_limits remaining_;
};
} // namespace lorica
