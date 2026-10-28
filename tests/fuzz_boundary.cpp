#include <lorica/byte_view.hpp>
#include <lorica/input_budget.hpp>
#include <cstdint>
#include <cstdlib>
#include <cstring>
#include <limits>

// @implements SPEC-LR-VERIFY
// libFuzzer owns this callback; its exact exported name is the framework ABI.
extern "C" int LLVMFuzzerTestOneInput(const std::uint8_t* data, std::size_t size) {
    if (size < 3 * sizeof(std::size_t)) return 0;
    std::size_t a, b, c;
    std::memcpy(&a, data, sizeof(a));
    std::memcpy(&b, data + sizeof(a), sizeof(b));
    std::memcpy(&c, data + 2 * sizeof(a), sizeof(c));
    const auto maximum = std::numeric_limits<std::size_t>::max();
    const auto sum = lorica::checked_add(a, b);
    const auto product = lorica::checked_multiply(a, b);
    if (sum.has_value() != (b <= maximum - a)) std::abort();
    if (product.has_value() != (a == 0 || b <= maximum / a)) std::abort();
    lorica::input_budget budget({a, b, c, 4});
    const bool accepted = budget.consume(c, a, b);
    if (accepted != (c <= a && a <= b && b <= c)) std::abort();
    if (!accepted && (budget.remaining().bytes != a ||
        budget.remaining().elements != b || budget.remaining().allocations != c)) std::abort();
    const auto view = lorica::byte_view::make(reinterpret_cast<const std::byte*>(data), size, size).value();
    const auto sub = view.subview(a, b);
    if (sub.has_value() != lorica::contains_range(size, a, b)) std::abort();
    if (sub && sub->size() != 0) (void)sub->at(sub->size() - 1);
    return 0;
}
