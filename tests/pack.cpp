// SPEC-LR-PACK unit checks (spec/feature/sealed-packs.md). The read bound and the
// OS's write refusal are judged from outside by tests/pack_fault.py.
#include <lorica/sealed_pack.hpp>
#include <atomic>
#include <cstdint>
#include <cstdlib>
#include <limits>
#include <memory>
#include <new>
#include <optional>
#include <stdexcept>
#include <string>
#include <string_view>
#include <type_traits>
#include <utility>

namespace {
// @implements SPEC-LR-VERIFY
void require(bool condition) { if (!condition) std::abort(); }

constexpr std::size_t max = (std::numeric_limits<std::size_t>::max)();
using lorica::detail::place_in_pack;

// @implements SPEC-LR-VERIFY
constexpr bool placed(std::optional<lorica::detail::pack_place> place, std::size_t offset, std::size_t end) {
    return place && place->offset == offset && place->end == end;
}
// The offset arithmetic at its edges, checked by the compiler.
static_assert(placed(place_in_pack(0, 8, 1, 8, 8), 0, 8));          // exact fit
static_assert(!place_in_pack(0, 7, 1, 8, 8));                       // one byte too many
static_assert(placed(place_in_pack(1, 16, 1, 8, 8), 8, 16));        // aligned up
static_assert(!place_in_pack(1, 15, 1, 8, 8));                      // aligned up, then too many
static_assert(placed(place_in_pack(3, 4, 0, 8, 8), 3, 3));          // empty: no bytes, no alignment
static_assert(placed(place_in_pack(4, 4, 0, 8, 8), 4, 4));          // empty at the very end
static_assert(placed(place_in_pack(max - 1, max, 1, 1, 1), max - 1, max)); // last byte of the address range
static_assert(!place_in_pack(max, max, 1, 1, 1));                   // nothing after SIZE_MAX
static_assert(!place_in_pack(max - 2, max, 1, 4, 4));               // align-up overflows
static_assert(!place_in_pack(0, max, max / 2 + 1, 2, 2));           // count * size overflows
static_assert(placed(place_in_pack(0, max, max / 4, 4, 4), 0, max / 4 * 4));

struct limits {
    std::uint32_t requests;
    double seconds;
    bool tls;
};
struct alignas(64) line { unsigned char bytes[64]; };
enum class mode : std::uint8_t { off, on = 200 };
struct no_copy { no_copy() = default; no_copy(const no_copy&) = delete; no_copy& operator=(const no_copy&) = default; };
struct counted { counted() = default; counted(const counted&) {} };

// Compile-time refusals. A pointer inside a struct is not one of them (shallow sealing).
static_assert(lorica::is_packable_v<int> && lorica::is_packable_v<limits> && lorica::is_packable_v<mode>);
static_assert(lorica::is_packable_v<line> && lorica::is_packable_v<std::string_view>);
static_assert(!lorica::is_packable_v<int*> && !lorica::is_packable_v<const char*>);
static_assert(!lorica::is_packable_v<int limits::*> && !lorica::is_packable_v<void (limits::*)()>);
static_assert(!lorica::is_packable_v<int[4]> && !lorica::is_packable_v<int&>);
static_assert(!lorica::is_packable_v<const int> && !lorica::is_packable_v<volatile limits>);
static_assert(!lorica::is_packable_v<std::string> && !lorica::is_packable_v<counted>);
static_assert(!lorica::is_packable_v<no_copy> && !lorica::is_packable_v<std::atomic<int>>);
static_assert(!std::is_copy_constructible_v<lorica::pack_builder> && !std::is_copy_assignable_v<lorica::pack_builder>);
static_assert(!std::is_move_constructible_v<lorica::pack_builder> && !std::is_move_assignable_v<lorica::pack_builder>);
static_assert(!std::is_copy_constructible_v<lorica::sealed_pack> && !std::is_copy_assignable_v<lorica::sealed_pack>);
static_assert(!std::is_move_constructible_v<lorica::sealed_pack> && !std::is_move_assignable_v<lorica::sealed_pack>);
static_assert(!std::is_constructible_v<lorica::sealed_pack, lorica::pack_builder&>); // Sealing consumes.
// Slots come only from a builder.
static_assert(!std::is_default_constructible_v<lorica::pack_slot<int>>);
static_assert(!std::is_constructible_v<lorica::pack_slot<int>, std::size_t>);
static_assert(!std::is_constructible_v<lorica::pack_array_slot<int>, std::size_t, std::size_t>);
static_assert(std::is_same_v<decltype(std::declval<const lorica::sealed_pack&>().load(
    std::declval<lorica::pack_slot<limits>>())), limits>);

// @implements SPEC-LR-VERIFY
template<class F>
bool throws_invalid_argument(F f) {
    try { f(); } catch (const std::invalid_argument&) { return true; }
    return false;
}
} // namespace

// @implements SPEC-LR-VERIFY
int main() {
    // Several types read back exactly, aligned after a one-byte value.
    {
        lorica::pack_builder builder(256);
        const auto flag = builder.add(mode::on);
        const auto lowest = builder.add((std::numeric_limits<std::int64_t>::min)());
        require(builder.used() == 16);
        const auto limit = builder.add(limits{4096, 2.5, true});
        line pattern{};
        for (unsigned index = 0; index < 64; ++index) pattern.bytes[index] = static_cast<unsigned char>(index * 3 + 1);
        const auto wide = builder.add(pattern);
        require(builder.used() == 128); // The 64-aligned value started at 64.
        const auto fraction = builder.add(-0.125);
        const auto last = builder.add(std::uint8_t{0xA5}); // The very last used byte.
        require(flag && lowest && limit && wide && fraction && last && builder.used() == 137);
        const lorica::sealed_pack pack(std::move(builder));
        require(pack.load(*flag) == mode::on);
        require(pack.load(*lowest) == (std::numeric_limits<std::int64_t>::min)());
        const limits read = pack.load(*limit);
        require(read.requests == 4096 && read.seconds == 2.5 && read.tls);
        const line copy = pack.load(*wide);
        for (unsigned index = 0; index < 64; ++index) require(copy.bytes[index] == pattern.bytes[index]);
        require(pack.load(*fraction) == -0.125 && pack.load(*last) == 0xA5);
    }
    // Exact fit, then one byte too many: refused, and nothing changes.
    {
        lorica::pack_builder builder(12);
        const auto first = builder.add(std::uint32_t{1});
        const auto second = builder.add(std::uint64_t{2}); // Aligned to 8: does not fit in 12.
        require(first && !second && builder.used() == 4 && builder.capacity() == 12);
        const auto third = builder.add(std::uint32_t{3});
        const auto fourth = builder.add(std::uint32_t{4}); // used() == capacity()
        require(third && fourth && builder.used() == 12);
        require(!builder.add(std::uint8_t{5}) && builder.used() == 12);
        const lorica::sealed_pack pack(std::move(builder));
        require(pack.load(*first) == 1 && pack.load(*third) == 3 && pack.load(*fourth) == 4);
    }
    // Arrays: empty, one, many; null data; count * sizeof(T) overflow; element index.
    {
        const std::uint16_t table[] = {10, 20, 30, 40, 50};
        const std::uint32_t single = 0xFEEDu;
        lorica::pack_builder builder(64);
        require(builder.add(std::uint8_t{9}).has_value());
        const auto empty = builder.add_array(table, 0);
        const auto empty_null = builder.add_array(static_cast<const std::uint16_t*>(nullptr), 0);
        require(empty && empty_null && empty->size() == 0 && builder.used() == 1); // No bytes taken.
        require(!builder.add_array(static_cast<const std::uint16_t*>(nullptr), 1) && builder.used() == 1);
        require(!builder.add_array(table, max / 2 + 1) && builder.used() == 1);
        require(!builder.add_array(table, max) && builder.used() == 1);
        const auto one = builder.add_array(&single, 1);
        const auto many = builder.add_array(table, 5);
        require(one && many && one->size() == 1 && many->size() == 5 && builder.used() == 18);
        const lorica::sealed_pack pack(std::move(builder));
        require(!pack.at(*empty, 0) && !pack.at(*empty_null, 0));
        require(pack.at(*one, 0) == 0xFEEDu && !pack.at(*one, 1));
        for (std::size_t index = 0; index < 5; ++index) require(pack.at(*many, index) == table[index]);
        require(!pack.at(*many, 5) && !pack.at(*many, max)); // Out of range: a value, not a fault.
    }
    // Capacity 0 is refused.
    require(throws_invalid_argument([] { lorica::pack_builder builder(0); }));
    // Sealing nothing is refused and leaves the builder usable.
    {
        lorica::pack_builder builder(8);
        require(throws_invalid_argument([&builder] { lorica::sealed_pack pack(std::move(builder)); }));
        require(builder.capacity() == 8 && builder.add(1).has_value());
    }
    // The builder after sealing accepts nothing, and cannot be sealed again.
    {
        lorica::pack_builder builder(8);
        const auto value = builder.add(7);
        const auto pack = std::make_unique<lorica::sealed_pack>(std::move(builder));
        require(value && pack->load(*value) == 7);
        require(builder.used() == 0 && builder.capacity() == 0);
        const int none = 0;
        require(!builder.add(1) && !builder.add_array(&none, 0) && builder.used() == 0);
        require(throws_invalid_argument([&builder] { lorica::sealed_pack again(std::move(builder)); }));
    }
    // A slot is only an offset: in another pack whose used bytes cover it, it
    // reads that pack's bytes. This is not detected (spec: limits).
    {
        lorica::pack_builder first(4);
        lorica::pack_builder second(4);
        const auto kept = first.add(std::int32_t{111});
        require(kept && second.add(std::int32_t{222}).has_value());
        std::optional<lorica::sealed_pack> other;
        other.emplace(std::move(second));
        const lorica::sealed_pack own(std::move(first));
        require(own.load(*kept) == 111 && other->load(*kept) == 222);
    }
    // An absurd capacity fails to allocate its staging buffer. Not checked under
    // the sanitizers, whose allocators report the request and exit instead of
    // throwing.
#if !defined(__SANITIZE_ADDRESS__) && !defined(__SANITIZE_THREAD__)
    bool refused = false;
    try {
        // Used and sealed, so that the compiler may not elide the allocation.
        lorica::pack_builder builder(max);
        static_cast<void>(builder.add(1));
        const lorica::sealed_pack pack(std::move(builder));
    } catch (const std::bad_alloc&) { refused = true; }
    require(refused);
#endif
}
