#include <lorica/byte_view.hpp>
#include <lorica/input_budget.hpp>
#include <array>
#include <cstdlib>
#include <limits>

namespace {
// @implements SPEC-LR-VERIFY
void require(bool condition) { if (!condition) std::abort(); }
}
// @implements SPEC-LR-VERIFY
int main() {
    constexpr auto max = std::numeric_limits<std::size_t>::max();
    static_assert(!lorica::checked_add(max, 1));
    static_assert(lorica::checked_add(max, 0).value() == max);
    static_assert(!lorica::checked_multiply(max, 2));
    static_assert(lorica::checked_multiply(max, 0).value() == 0);
    static_assert(lorica::contains_range(max, max, 0));
    static_assert(!lorica::contains_range(max, max, 1));
    static_assert(!lorica::contains_range(0, max, 1));

    lorica::input_budget budget({10, 3, 2, 4});
    require(!budget.consume(11, 1, 1));
    require(budget.remaining().bytes == 10 && budget.remaining().allocations == 2);
    require(!budget.consume(1, 4, 1));
    require(!budget.consume(1, 1, 3));
    require(budget.consume(10, 3, 2));
    require(!budget.consume(1, 0, 0));
    require(budget.consume(0, 0, 0));
    require(budget.permits_depth(4) && !budget.permits_depth(5));

    const std::array<std::byte, 3> data{std::byte{1}, std::byte{2}, std::byte{3}};
    require(!lorica::byte_view::make(nullptr, 1, 1));
    require(!lorica::byte_view::make(data.data(), 3, 2));
    const auto view = lorica::byte_view::make(data.data(), data.size(), 3).value();
    require(view.at(2).value() == std::byte{3});
    require(!view.at(3) && !view.at(max));
    require(!view.subview(1, max) && !view.subview(max, 0));
    require(view.subview(3, 0)->size() == 0);
    require(view.subview(1, 2)->at(1).value() == std::byte{3});
    const auto empty = lorica::byte_view::make(nullptr, 0, 0).value();
    require(empty.subview(0, 0).has_value() && !empty.at(0));
}
