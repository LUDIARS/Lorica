#include <lorica/byte_view.hpp>
#include <lorica/input_budget.hpp>
#include <array>
#include <cstdlib>
#include <limits>
#include <type_traits>

namespace {
// @implements SPEC-LR-VERIFY
void require(bool condition) { if (!condition) std::abort(); }

// A charge smaller than the budget: every dimension is subtracted, and adds up.
constexpr bool partial_charges() {
    lorica::input_budget budget({10, 3, 2, 4});
    if (!budget.consume(4, 1, 1)) return false;
    const auto left = budget.remaining();
    if (left.bytes != 6 || left.elements != 2 || left.allocations != 1 || left.depth != 4) return false;
    if (budget.consume(0, 3, 0) || budget.consume(0, 0, 2)) return false;
    return budget.consume(6, 2, 1) && !budget.consume(0, 1, 0) && !budget.consume(0, 0, 1);
}
static_assert(partial_charges());
// A copy would be a second budget that the request's charges never reach.
static_assert(!std::is_copy_constructible<lorica::input_budget>::value &&
              !std::is_copy_assignable<lorica::input_budget>::value);

// Exactly three bytes: in a constant expression a read past them does not compile,
// which is the "without reading backing memory" half of LR-VIEW-02.
constexpr std::byte exact[3]{std::byte{1}, std::byte{2}, std::byte{3}};
constexpr auto shorter = lorica::byte_view::make(exact, 2, 3);   // size < maximum
static_assert(shorter.value().size() == 2 && !shorter.value().at(2));
constexpr auto whole = lorica::byte_view::make(exact, 3, 3);
static_assert(!whole.value().at(3));
static_assert(!whole.value().subview(1, 3) && !whole.value().subview(2, 2));
constexpr auto head = whole.value().subview(0, 1);
static_assert(head.value().size() == 1 && !head.value().at(1));
static_assert(lorica::byte_view::make(nullptr, 0, 16).has_value());
static_assert(noexcept(lorica::byte_view::make(nullptr, 0, 0)));
}
// @implements SPEC-LR-VERIFY
int main() {
    constexpr auto max = std::numeric_limits<std::size_t>::max();
    static_assert(!lorica::checked_add(max, 1));
    static_assert(lorica::checked_add(max, 0).value() == max);
    static_assert(lorica::checked_add(2, 3).value() == 5 && lorica::checked_add(max - 1, 1).value() == max);
    static_assert(!lorica::checked_multiply(max, 2));
    static_assert(lorica::checked_multiply(max, 0).value() == 0);
    static_assert(lorica::checked_multiply(0, max).value() == 0 && lorica::checked_multiply(6, 7).value() == 42);
    static_assert(lorica::checked_multiply(max, 1).value() == max && !lorica::checked_multiply(max / 2 + 1, 2));
    static_assert(lorica::contains_range(max, max, 0));
    static_assert(!lorica::contains_range(max, max, 1));
    static_assert(!lorica::contains_range(0, max, 1));
    static_assert(lorica::contains_range(10, 4, 6) && !lorica::contains_range(10, 4, 7));

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
    require(view.subview(3, 0).value().size() == 0);
    require(view.subview(1, 2).value().at(1).value() == std::byte{3});
    const auto empty = lorica::byte_view::make(nullptr, 0, 0).value();
    require(empty.subview(0, 0).has_value() && !empty.at(0));
}
