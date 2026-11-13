#include <lorica/bounded_text.hpp>
#include <lorica/byte_reader.hpp>
// byte_view.hpp brings checked_size.hpp's size_t overloads into the same overload
// sets, which must not let a mixed call convert its way through.
#include <lorica/byte_view.hpp>
#include <lorica/checked_integer.hpp>
#include <array>
#include <bit>
#include <concepts>
#include <cstddef>
#include <cstdint>
#include <cstdlib>
#include <limits>
#include <span>
#include <string>
#include <string_view>
#include <vector>

namespace {
// @implements SPEC-LR-VERIFY
void require(bool condition) { if (!condition) std::abort(); }

template<class T>
using limits = std::numeric_limits<T>;

// Overload sets probed without instantiating an ill-formed call.
template<class D>
concept copies_into = requires(D&& destination) {
    lorica::copy_string(std::forward<D>(destination), "x");
};
template<class S>
concept copies_from = requires(std::array<char, 8>& out, const S& source) { lorica::copy_string(out, source); };

static_assert(!lorica::checked_integral<bool> && !lorica::checked_integral<char> &&
              !lorica::checked_integral<char8_t> && !lorica::checked_integral<wchar_t> &&
              !lorica::checked_integral<char16_t> && !lorica::checked_integral<char32_t> &&
              !lorica::checked_integral<const bool>);
static_assert(lorica::checked_integral<signed char> && lorica::checked_integral<unsigned char> &&
              lorica::checked_integral<std::int64_t> && lorica::checked_integral<std::size_t>);
// Mixed operand types and explicit template arguments are refused for every binary
// function, so -1 never becomes SIZE_MAX silently, even next to checked_size.hpp's
// size_t overloads (checked_add and checked_multiply have one).
#define LORICA_PROBE(name) \
    template<class A, class B> concept calls_##name = requires(A a, B b) { lorica::name(a, b); }; \
    template<class A, class B> \
    concept calls1_##name = requires(A a, B b) { lorica::name<std::size_t>(a, b); }; \
    template<class A, class B> \
    concept calls2_##name = requires(A a, B b) { lorica::name<std::size_t, std::size_t>(a, b); }; \
    static_assert(calls_##name<std::size_t, std::size_t> && calls_##name<int, int>); \
    static_assert(!calls_##name<std::size_t, int> && !calls_##name<int, std::size_t> && \
                  !calls_##name<int, long> && !calls_##name<std::uint32_t, int> && \
                  !calls_##name<bool, bool> && !calls_##name<char, char>); \
    static_assert(!calls1_##name<std::size_t, int> && !calls1_##name<std::size_t, std::size_t> && \
                  !calls2_##name<std::size_t, int> && !calls2_##name<std::size_t, std::size_t>);
LORICA_PROBE(checked_add) LORICA_PROBE(checked_subtract) LORICA_PROBE(checked_multiply)
LORICA_PROBE(checked_divide) LORICA_PROBE(saturating_add) LORICA_PROBE(saturating_subtract)
LORICA_PROBE(saturating_multiply)
#undef LORICA_PROBE
// The conversions take their source type by deduction only.
template<class V>
concept narrows_explicitly = requires(V v) { lorica::narrow<unsigned, unsigned>(v); };
template<class V>
concept saturates_explicitly = requires(V v) { lorica::saturate_cast<unsigned, unsigned>(v); };
static_assert(!narrows_explicitly<int> && !saturates_explicitly<int>);
// An array of unknown bound has no extent to search, and nullptr is no string.
static_assert(copies_from<char[4]> && copies_from<std::string> && copies_from<const char*> &&
              !copies_from<wchar_t[4]> && !copies_from<int> && !copies_from<char[]> &&
              !copies_from<std::nullptr_t>);
// A temporary container would be destroyed before the reader's first read.
static_assert(!std::constructible_from<lorica::byte_reader, std::vector<std::byte>> &&
              std::constructible_from<lorica::byte_reader, std::vector<std::byte>&> &&
              std::constructible_from<lorica::byte_reader, std::span<const std::byte>>);
// A temporary or read-only destination would lose the result.
static_assert(copies_into<std::array<char, 4>&> && copies_into<std::span<char>>);
static_assert(!copies_into<std::array<char, 4>> && !copies_into<const std::array<char, 4>&> &&
              !copies_into<std::string> && !copies_into<std::array<int, 4>&>);

// @implements SPEC-LR-VERIFY
constexpr bool integers() {
    using i8 = std::int8_t;
    using u16 = std::uint16_t;
    using i64 = std::int64_t;
    using u64 = std::uint64_t;
    bool ok = true;
    ok = ok && lorica::narrow<i8>(127).value() == 127 && !lorica::narrow<i8>(128);
    ok = ok && !lorica::narrow<i8>(-129) && lorica::narrow<i8>(-128).value() == -128;
    ok = ok && !lorica::narrow<unsigned>(-1) && !lorica::narrow<i64>(limits<u64>::max());
    ok = ok && lorica::narrow<u64>(limits<i64>::max()).value() == 9223372036854775807ULL;
    ok = ok && !lorica::checked_add(limits<int>::max(), 1) && !lorica::checked_add(limits<int>::min(), -1);
    ok = ok && lorica::checked_add(limits<int>::max(), -1).value() == limits<int>::max() - 1;
    ok = ok && !lorica::checked_add(limits<u64>::max(), u64{1}) && lorica::checked_add(u64{1}, u64{2}) == u64{3};
    ok = ok && !lorica::checked_subtract(limits<int>::min(), 1) && !lorica::checked_subtract(0, limits<int>::min());
    ok = ok && !lorica::checked_subtract(u16{0}, u16{1}) && lorica::checked_subtract(u16{5}, u16{5}) == u16{0};
    // Promoted operands must not overflow int: 65535 * 65535 is checked first.
    ok = ok && !lorica::checked_multiply(u16{65535}, u16{65535});
    ok = ok && lorica::checked_multiply(u16{255}, u16{257}).value() == 65535;
    ok = ok && !lorica::checked_multiply(limits<int>::min(), -1) && !lorica::checked_multiply(-1, limits<int>::min());
    ok = ok && !lorica::checked_multiply(limits<int>::max(), 2) && !lorica::checked_multiply(limits<int>::min(), 2);
    ok = ok && !lorica::checked_multiply(-2, limits<int>::max()) && lorica::checked_multiply(-1, limits<int>::max()).value() == -limits<int>::max();
    ok = ok && lorica::checked_multiply(0, limits<int>::min()).value() == 0 && lorica::checked_multiply(-3, -4).value() == 12;
    ok = ok && !lorica::checked_divide(1, 0) && !lorica::checked_divide(limits<int>::min(), -1);
    ok = ok && lorica::checked_divide(-7, 2).value() == -3 && !lorica::checked_divide(u64{1}, u64{0});
    ok = ok && lorica::saturating_add(limits<int>::max(), 5) == limits<int>::max();
    ok = ok && lorica::saturating_add(limits<int>::min(), -5) == limits<int>::min();
    ok = ok && lorica::saturating_subtract(u16{1}, u16{2}) == 0 && lorica::saturating_subtract(limits<int>::min(), 1) == limits<int>::min();
    ok = ok && lorica::saturating_subtract(limits<int>::max(), -1) == limits<int>::max();
    ok = ok && lorica::saturating_multiply(limits<int>::max(), -2) == limits<int>::min();
    ok = ok && lorica::saturating_multiply(limits<int>::min(), -1) == limits<int>::max();
    ok = ok && lorica::saturating_multiply(u16{300}, u16{300}) == 65535;
    ok = ok && lorica::saturate_cast<i8>(1000) == 127 && lorica::saturate_cast<i8>(-1000) == -128;
    ok = ok && lorica::saturate_cast<unsigned>(-1) == 0u && lorica::saturate_cast<i64>(limits<u64>::max()) == limits<i64>::max();
    return ok;
}
static_assert(integers());
// Unsigned types of int rank and wider and 64-bit signed types through the
// templates, where integer promotion no longer hides a wrap.
static_assert(!lorica::checked_add(limits<unsigned>::max(), 1u) &&
              !lorica::checked_add(limits<unsigned long long>::max(), 1ull) &&
              !lorica::checked_add(limits<unsigned long>::max(), 1ul) &&
              lorica::checked_add(limits<unsigned>::max() - 1u, 1u) == limits<unsigned>::max());
static_assert(!lorica::checked_subtract(0u, 1u) && !lorica::checked_subtract(std::size_t{4}, std::size_t{5}) &&
              !lorica::checked_subtract(0ull, 1ull) && lorica::saturating_subtract(std::size_t{4}, std::size_t{5}) == 0);
static_assert(!lorica::checked_multiply(1ull << 32, 1ull << 32) &&
              lorica::checked_multiply(0xFFFFFFFFull, 0x100000001ull) == limits<unsigned long long>::max() &&
              lorica::saturating_multiply(1ull << 63, 2ull) == limits<unsigned long long>::max());
static_assert(!lorica::checked_add(limits<long long>::max(), 1ll) && !lorica::checked_add(limits<long long>::min(), -1ll) &&
              !lorica::checked_add(limits<long>::max(), 1l) &&
              lorica::checked_add(limits<long long>::min(), limits<long long>::max()) == -1ll);

// @implements SPEC-LR-VERIFY
constexpr bool text() {
    bool ok = true;
    std::array<char, 6> buffer{'x', 'x', 'x', 'x', 'x', 'x'};
    ok = ok && lorica::copy_string(buffer, "hello").value() == 5 && buffer[5] == '\0';
    ok = ok && std::string_view(buffer.data()) == "hello";
    // One character too long: no truncated value is left behind.
    ok = ok && !lorica::copy_string(buffer, "hello!") && buffer[0] == '\0';
    // An embedded terminator would shorten the string silently.
    ok = ok && !lorica::copy_string(buffer, std::string_view("a\0b", 3)) && buffer[0] == '\0';
    ok = ok && lorica::copy_string(buffer, "").value() == 0 && buffer[0] == '\0';
    ok = ok && lorica::copy_string(buffer, "ab").value() == 2;
    ok = ok && lorica::append_string(buffer, "cd").value() == 4 && std::string_view(buffer.data()) == "abcd";
    ok = ok && lorica::append_string(buffer, "e").value() == 5;
    ok = ok && !lorica::append_string(buffer, "f") && buffer[0] == '\0';
    ok = ok && lorica::copy_string(buffer, "ab").value() == 2;
    ok = ok && !lorica::append_string(buffer, std::string_view("x\0y", 3)) && buffer[0] == '\0';
    // A character array is read up to its first terminator, which must lie inside it:
    // a fixed field without one is not read past its end.
    const char unterminated[2] = {'a', 'b'};
    ok = ok && !lorica::copy_string(buffer, unterminated) && buffer[0] == '\0';
    ok = ok && lorica::copy_string(buffer, "ab").value() == 2;
    ok = ok && !lorica::append_string(buffer, unterminated) && buffer[0] == '\0';
    const char padded[6] = "ab";
    ok = ok && lorica::copy_string(buffer, padded).value() == 2 && lorica::append_string(buffer, padded).value() == 4;
    ok = ok && lorica::copy_string(buffer, "a\0b").value() == 1;
    // A source that is a view into the destination is copied correctly.
    std::array<char, 10> shift{'a', 'b', 'c', 'd', 'e', 'f', '\0'};
    ok = ok && lorica::copy_string(std::span<char>(shift).subspan(2), std::string_view(shift.data(), 6)).value() == 6;
    ok = ok && std::string_view(shift.data() + 2) == "abcdef";
    std::array<char, 10> back{'x', 'x', 'a', 'b', 'c', '\0'};
    ok = ok && lorica::copy_string(back, std::string_view(back.data() + 2, 3)).value() == 3;
    ok = ok && std::string_view(back.data()) == "abc";
    // No terminator: the content is not a C string, so nothing is appended.
    std::array<char, 2> full{'a', 'b'};
    ok = ok && !lorica::append_string(full, "") && full[0] == '\0';
    std::array<char, 0> none{};
    ok = ok && !lorica::copy_string(none, "") && !lorica::append_string(none, "");
    std::array<char32_t, 3> wide{};
    ok = ok && lorica::copy_string(wide, U"ab").value() == 2 && wide[2] == U'\0';
    std::array<char, 4> span_backing{};
    ok = ok && lorica::copy_string(std::span<char>(span_backing).first(2), "a").value() == 1;
    ok = ok && !lorica::copy_string(std::span<char>(span_backing).first(2), "ab");
    const char* null_text = nullptr;
    ok = ok && lorica::copy_string(buffer, "ab").value() == 2;
    ok = ok && !lorica::copy_string(buffer, null_text) && buffer[0] == '\0';
    return ok;
}
static_assert(text());

constexpr std::array<std::byte, 11> packet{
    std::byte{0x12}, std::byte{0x34}, std::byte{0x34}, std::byte{0x12}, std::byte{0xFF},
    std::byte{0x00}, std::byte{0x02}, std::byte{'h'}, std::byte{'i'}, std::byte{0x80}, std::byte{0x00}};

// @implements SPEC-LR-VERIFY
constexpr bool reader() {
    bool ok = true;
    lorica::byte_reader in{std::span<const std::byte>(packet)};
    ok = ok && in.read_big_endian<std::uint16_t>().value() == 0x1234;
    ok = ok && in.read_little_endian<std::uint16_t>().value() == 0x1234;
    ok = ok && in.read_big_endian<std::int8_t>().value() == -1;
    const auto field = in.read_prefixed<std::uint16_t, std::endian::big>();
    ok = ok && field && field->size() == 2 && (*field)[1] == std::byte{'i'};
    ok = ok && in.read_big_endian<std::int16_t>().value() == -32768 && in.remaining() == 0;
    ok = ok && !in.read_big_endian<std::uint8_t>() && in.offset() == packet.size();
    ok = ok && in.take(0).has_value() && !in.take(1) && !in.skip(1);

    // A failed read consumes nothing, including the length of a prefixed field.
    lorica::byte_reader short_read{std::span<const std::byte>(packet).first(3)};
    ok = ok && !short_read.read_big_endian<std::uint32_t>() && short_read.offset() == 0;
    lorica::byte_reader overlong{std::span<const std::byte>(packet).subspan(4)};
    ok = ok && !overlong.read_prefixed<std::uint8_t, std::endian::big>() && overlong.offset() == 0;
    lorica::byte_reader too_far{std::span<const std::byte>(packet).subspan(4, 3)};
    ok = ok && !too_far.read_prefixed<std::uint16_t, std::endian::little>() && too_far.offset() == 0;
    // A negative length is rejected, not converted to a huge size.
    lorica::byte_reader negative{std::span<const std::byte>(packet).subspan(4, 1)};
    ok = ok && !negative.read_prefixed<std::int8_t, std::endian::big>() && negative.offset() == 0;
    lorica::byte_reader zero{std::span<const std::byte>(packet).subspan(5, 1)};
    const auto empty = zero.read_prefixed<std::uint8_t, std::endian::big>();
    ok = ok && empty && empty->empty() && zero.remaining() == 0;
    lorica::byte_reader nothing;
    ok = ok && nothing.size() == 0 && !nothing.read_little_endian<std::uint8_t>();

    // Wide integers in both orders: the C++23 std::byteswap path and the C++20
    // byte-by-byte path must agree, so both standards run the same expectations.
    constexpr std::array<std::byte, 8> wide{
        std::byte{0x01}, std::byte{0x23}, std::byte{0x45}, std::byte{0x67},
        std::byte{0x89}, std::byte{0xAB}, std::byte{0xCD}, std::byte{0xEF}};
    const auto bytes = std::span<const std::byte>(wide);
    ok = ok && lorica::byte_reader{bytes}.read_big_endian<std::uint64_t>().value() == 0x0123456789ABCDEFULL;
    ok = ok && lorica::byte_reader{bytes}.read_little_endian<std::uint64_t>().value() == 0xEFCDAB8967452301ULL;
    ok = ok && lorica::byte_reader{bytes}.read_big_endian<std::uint32_t>().value() == 0x01234567U;
    ok = ok && lorica::byte_reader{bytes}.read_little_endian<std::uint32_t>().value() == 0x67452301U;
    ok = ok && lorica::byte_reader{bytes.subspan(4)}.read_big_endian<std::int32_t>().value() ==
                   static_cast<std::int32_t>(0x89ABCDEFU);
    ok = ok && lorica::byte_reader{bytes}.read_little_endian<std::int64_t>().value() ==
                   static_cast<std::int64_t>(0xEFCDAB8967452301ULL);
    return ok;
}
static_assert(reader());

constexpr std::array<std::byte, 8> wide_bytes{std::byte{0x80}, std::byte{0x01}, std::byte{0x02}, std::byte{0x03},
    std::byte{0x04}, std::byte{0x05}, std::byte{0x06}, std::byte{0x07}};

// Four- and eight-byte integers in both orders, and a skip that really advances.
// @implements SPEC-LR-VERIFY
constexpr bool reader_wide() {
    bool ok = true;
    lorica::byte_reader a{std::span<const std::byte>(wide_bytes)};
    ok = ok && a.read_big_endian<std::uint32_t>().value() == 0x80010203u;
    ok = ok && a.read_little_endian<std::uint32_t>().value() == 0x07060504u;
    lorica::byte_reader b{std::span<const std::byte>(wide_bytes)};
    ok = ok && b.read_big_endian<std::int32_t>().value() == limits<std::int32_t>::min() + 0x10203;
    lorica::byte_reader c{std::span<const std::byte>(wide_bytes)};
    ok = ok && c.read_big_endian<std::uint64_t>().value() == 0x8001020304050607ull;
    lorica::byte_reader d{std::span<const std::byte>(wide_bytes)};
    ok = ok && d.read_little_endian<std::int64_t>().value() == 0x0706050403020180ll;
    lorica::byte_reader s{std::span<const std::byte>(packet)};
    ok = ok && s.skip(4) && s.offset() == 4 && s.remaining() == 7 && s.read_big_endian<std::int8_t>().value() == -1;
    // A const-qualified type reads like the unqualified one.
    lorica::byte_reader e{std::span<const std::byte>(packet)};
    ok = ok && e.read_big_endian<const std::uint16_t>().value() == 0x1234;
    return ok;
}
static_assert(reader_wide());

// Every pair of 8-bit operands against the exact result computed in a wider type.
// @implements SPEC-LR-VERIFY
template<class T>
bool exhaustive() {
    using wide = long long;
    constexpr wide low = limits<T>::min(), high = limits<T>::max();
    const auto clamp = [](wide value) { return static_cast<T>(value < low ? low : value > high ? high : value); };
    const auto fits = [](wide value) { return value >= low && value <= high; };
    for (wide a = low; a <= high; ++a) {
        for (wide b = low; b <= high; ++b) {
            const T x = static_cast<T>(a), y = static_cast<T>(b);
            const wide sum = a + b, difference = a - b, product = a * b;
            if (lorica::checked_add(x, y) != (fits(sum) ? std::optional<T>(static_cast<T>(sum)) : std::nullopt)) return false;
            if (lorica::checked_subtract(x, y) != (fits(difference) ? std::optional<T>(static_cast<T>(difference)) : std::nullopt)) return false;
            if (lorica::checked_multiply(x, y) != (fits(product) ? std::optional<T>(static_cast<T>(product)) : std::nullopt)) return false;
            const bool divides = b != 0 && fits(a / (b == 0 ? 1 : b));
            if (lorica::checked_divide(x, y) != (divides ? std::optional<T>(static_cast<T>(a / b)) : std::nullopt)) return false;
            if (lorica::saturating_add(x, y) != clamp(sum) || lorica::saturating_subtract(x, y) != clamp(difference) ||
                lorica::saturating_multiply(x, y) != clamp(product)) return false;
        }
        if (lorica::narrow<T>(a) != std::optional<T>(static_cast<T>(a))) return false;
    }
    for (wide value : {low - 1, high + 1, -1LL, 300LL}) {
        if (lorica::narrow<T>(value) != (fits(value) ? std::optional<T>(static_cast<T>(value)) : std::nullopt)) return false;
        if (lorica::saturate_cast<T>(value) != clamp(value)) return false;
    }
    return true;
}
} // namespace

// @implements SPEC-LR-VERIFY
int main([[maybe_unused]] int argc, char**) {
#if !defined(__cpp_lib_format)
    // lorica.checked.format.* passes an argument: without <format> it is reported
    // as skipped (77), not as passed.
    if (argc > 1) return 77;
#endif
    // Every constant check also runs at run time, with the extended profile's
    // hardened standard library and zero-initialized automatic variables.
    require(integers() && text() && reader() && reader_wide());
    require(exhaustive<std::int8_t>() && exhaustive<std::uint8_t>());

    std::vector<char> heap(8, 'x');
    require(lorica::copy_string(heap, std::string(7, 'a')).value() == 7 && heap[7] == '\0');
    require(!lorica::copy_string(heap, std::string(8, 'a')) && heap[0] == '\0');
#if defined(__cpp_lib_format)
    std::array<char, 8> formatted{};
    require(lorica::format_into(formatted, "{}-{}", 12, "ab").value() == 5);
    require(std::string_view(formatted.data()) == "12-ab");
    require(!lorica::format_into(formatted, "{:>8}", 1) && formatted[0] == '\0');
    require(lorica::format_into(formatted, "{:>7}", 1).value() == 7 && formatted[7] == '\0');
    std::array<char, 1> tiny{'x'};
    require(lorica::format_into(tiny, "").value() == 0 && tiny[0] == '\0');
    require(!lorica::format_into(tiny, "{}", 0) && tiny[0] == '\0');
    std::array<char, 0> none{};
    require(!lorica::format_into(none, "{}", 0));
    // Output holding a terminator would be a shortened C string.
    require(!lorica::format_into(formatted, "{}.txt", std::string("a\0", 2)) && formatted[0] == '\0');
#if defined(__cpp_exceptions) || defined(_CPPUNWIND)
    // A formatter that throws leaves an empty string behind, not partial output.
    std::array<char, 16> partial{};
    bool thrown = false;
    try {
        (void)lorica::format_into(partial, "abcdef{:{}}", 1, -1);
    } catch (const std::format_error&) {
        thrown = true;
    }
    require(thrown && partial[0] == '\0');
#endif
#endif
    return 0;
}
