#include <lorica/byte_view.hpp>
#include <lorica/input_budget.hpp>
#include <cstdint>
#include <cstdlib>
#include <cstring>
#include <limits>

// Every oracle is independent of the function it judges (compiler overflow
// builtins, 128-bit arithmetic, the raw input bytes), and results are compared by
// value, not only by has_value().
// @implements SPEC-LR-VERIFY
// libFuzzer owns this callback; its exact exported name is the framework ABI.
extern "C" int LLVMFuzzerTestOneInput(const std::uint8_t* data, std::size_t size) {
    if (size < 3 * sizeof(std::size_t)) return 0;
    std::size_t a, b, c;
    std::memcpy(&a, data, sizeof(a));
    std::memcpy(&b, data + sizeof(a), sizeof(b));
    std::memcpy(&c, data + 2 * sizeof(a), sizeof(c));

    std::size_t expected = 0;
    const bool add_overflows = __builtin_add_overflow(a, b, &expected);
    const auto sum = lorica::checked_add(a, b);
    if (sum.has_value() == add_overflows || (sum && *sum != expected)) std::abort();
    const bool multiply_overflows = __builtin_mul_overflow(a, b, &expected);
    const auto product = lorica::checked_multiply(a, b);
    if (product.has_value() == multiply_overflows || (product && *product != expected)) std::abort();

    using wide = unsigned __int128;
    if (lorica::contains_range(a, b, c) != (static_cast<wide>(b) + c <= a)) std::abort();

    // Budget: a rejected charge changes nothing; an accepted one is subtracted in
    // every dimension; what is left can be taken exactly once.
    lorica::input_budget budget({a, b, c, 4});
    const bool accepted = budget.consume(c, a, b);
    if (accepted != (c <= a && a <= b && b <= c)) std::abort();
    if (!accepted) {
        const std::size_t part[3]{a >> (c & 63), b >> ((c >> 6) & 63), c >> ((c >> 12) & 63)};
        if (!budget.consume(part[0], part[1], part[2])) std::abort();
        auto left = budget.remaining();
        if (left.bytes != a - part[0] || left.elements != b - part[1] ||
            left.allocations != c - part[2] || left.depth != 4) std::abort();
        if (left.bytes != std::numeric_limits<std::size_t>::max() && budget.consume(left.bytes + 1, 0, 0)) std::abort();
        if (left.elements != std::numeric_limits<std::size_t>::max() && budget.consume(0, left.elements + 1, 0)) std::abort();
        if (left.allocations != std::numeric_limits<std::size_t>::max() && budget.consume(0, 0, left.allocations + 1)) std::abort();
        if (!budget.consume(left.bytes, left.elements, left.allocations)) std::abort();
        left = budget.remaining();
        if (left.bytes != 0 || left.elements != 0 || left.allocations != 0) std::abort();
    }
    if (budget.permits_depth(a) != (a <= 4)) std::abort();

    // View: the declared size, not the maximum and not the backing buffer, bounds it.
    const auto* bytes = reinterpret_cast<const std::byte*>(data);
    if (lorica::byte_view::make(bytes, size, size - 1)) std::abort();
    if (lorica::byte_view::make(nullptr, size, size) || !lorica::byte_view::make(nullptr, 0, size)) std::abort();
    const std::size_t shown = size - (c % 8);                       // size >= 24, so shown >= 17
    const auto made = lorica::byte_view::make(bytes, shown, size + (b & 1));
    if (!made || made->size() != shown || made->at(shown) || made->at(a | shown)) std::abort();
    const lorica::byte_view view = *made;
    for (const std::size_t offset : {a, a % (shown + 2)}) {
        for (const std::size_t length : {b, b % (shown + 2)}) {
            const auto sub = view.subview(offset, length);
            if (sub.has_value() != (static_cast<wide>(offset) + length <= shown)) std::abort();
            if (!sub) continue;
            if (sub->size() != length || sub->at(length)) std::abort();
            for (std::size_t index = 0; index < length; ++index) {
                const auto value = sub->at(index);
                if (!value || *value != bytes[offset + index]) std::abort();
            }
        }
    }
    return 0;
}
