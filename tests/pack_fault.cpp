// SPEC-LR-PACK violations, each committed in a disposable child and judged from
// outside by tests/pack_fault.py: the OS must refuse a write to a sealed byte,
// and a read whose slot lies outside the pack's used bytes must terminate.
// "control" takes every step but the violation.
#include <lorica/sealed_pack.hpp>
#include <cstdint>
#include <cstring>
#include <string_view>
#include <type_traits>
#include <utility>
#ifdef _WIN32
#define WIN32_LEAN_AND_MEAN
#define NOMINMAX
#include <windows.h>
#include <stdlib.h>
#else
#include <sys/resource.h>
#endif

// @implements SPEC-LR-VERIFY
int main(int argc, char** argv) {
#ifdef _WIN32
    _set_abort_behavior(0, _WRITE_ABORT_MSG | _CALL_REPORTFAULT); // abort() exits with 3.
    SetErrorMode(SEM_FAILCRITICALERRORS | SEM_NOGPFAULTERRORBOX);
#else
    const rlimit limit{0, 0};
    if (setrlimit(RLIMIT_CORE, &limit) != 0) return 4;
#endif
    if (argc != 2) return 2;
    const std::string_view mode(argv[1]);
    constexpr std::uint32_t first_marker = 0x5EA1ED;
    constexpr std::uint8_t last_marker = 0xA5;
    // Several pages, so the last used byte is not on the first one.
    static const std::uint8_t filler[3 * 4096] = {};
    lorica::pack_builder builder(sizeof(filler) + 64);
    const auto first = builder.add(first_marker);
    const auto middle = builder.add_array(filler, sizeof(filler));
    const auto last = builder.add(last_marker);
    lorica::pack_builder small_builder(sizeof(std::uint32_t));
    if (!first || !middle || !last || !small_builder.add(first_marker)) return 4;
    const std::size_t last_offset = builder.used() - 1;
    const lorica::sealed_pack pack(std::move(builder));
    const lorica::sealed_pack small(std::move(small_builder));

    // White box: the mapping's address is the first member of the first member.
    static_assert(std::is_standard_layout_v<lorica::sealed_pack>);
    const void* base = nullptr;
    std::memcpy(&base, &pack, sizeof(base));
    // Integer arithmetic and volatile accesses keep the compiler from reasoning
    // about the deliberate writes.
    const auto byte_at = [base](std::size_t offset) {
        return reinterpret_cast<volatile unsigned char*>(reinterpret_cast<std::uintptr_t>(base) + offset);
    };
    // The address must really be the pack's, or the faults below would prove nothing.
    unsigned char expected[sizeof(first_marker)];
    std::memcpy(expected, &first_marker, sizeof(expected));
    for (std::size_t index = 0; index < sizeof(expected); ++index)
        if (*byte_at(index) != expected[index]) return 4;
    if (*byte_at(last_offset) != last_marker) return 4;

    if (mode == "control")
        return pack.load(*first) == first_marker && pack.load(*last) == last_marker &&
               small.load(*first) == first_marker && pack.at(*middle, 0) == 0 ? 0 : 5;
    if (mode == "write_first") *byte_at(0) = 1;
    else if (mode == "write_last") *byte_at(last_offset) = 1;
    else if (mode == "load_outside") static_cast<void>(small.load(*last));
    else if (mode == "at_outside") static_cast<void>(small.at(*middle, 0));
    else return 2;
    return 3; // Reaching here means nothing stopped the violation.
}
