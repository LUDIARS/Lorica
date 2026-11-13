// A service's immutable start-up data in one sealed pack, then N integers held
// three ways: one sealed_value each, one sealed pack, one heap allocation each.
// Usage: lorica_packing_demo [N]   (default 1000)
#include <lorica/checked_size.hpp>
#include <lorica/sealed_pack.hpp>
#include <lorica/sealed_value.hpp>
#include <algorithm>
#include <array>
#include <charconv>
#include <chrono>
#include <cstdint>
#include <cstdio>
#include <cstring>
#include <deque>
#include <exception>
#include <fstream>
#include <memory>
#include <optional>
#include <random>
#include <string>
#include <utility>
#include <vector>

namespace {
struct service_limits {
    std::uint32_t max_connections;
    std::uint32_t max_request_bytes;
    std::uint16_t idle_timeout_seconds;
    bool require_tls;
};

// @implements SPEC-LR-PACK
// Limits, a hexadecimal digit table and role names as one string table, sealed together.
bool show_configuration() {
    std::array<std::int8_t, 256> hex{};
    hex.fill(-1);
    for (int digit = 0; digit < 16; ++digit) {
        hex[static_cast<unsigned char>("0123456789abcdef"[digit])] = static_cast<std::int8_t>(digit);
        hex[static_cast<unsigned char>("0123456789ABCDEF"[digit])] = static_cast<std::int8_t>(digit);
    }
    constexpr char names[] = "reader\0writer\0admin";
    constexpr std::array<std::uint16_t, 3> starts{0, 7, 14};

    lorica::pack_builder builder(512);
    const auto limits = builder.add(service_limits{512, 1u << 20, 30, true});
    const auto digits = builder.add_array(hex.data(), hex.size());
    const auto text = builder.add_array(names, sizeof(names));
    const auto offsets = builder.add_array(starts.data(), starts.size());
    if (!limits || !digits || !text || !offsets) return false; // The capacity was too small.
    std::printf("sealed configuration: %zu of %zu bytes used, one read-only mapping\n",
                builder.used(), builder.capacity());
    const lorica::sealed_pack pack(std::move(builder));

    const service_limits sealed = pack.load(*limits);
    std::printf("  limits: %u connections, %u request bytes, %u s idle, TLS %s\n",
                static_cast<unsigned>(sealed.max_connections), static_cast<unsigned>(sealed.max_request_bytes),
                static_cast<unsigned>(sealed.idle_timeout_seconds), sealed.require_tls ? "required" : "optional");
    const auto high = pack.at(*digits, '7');
    const auto low = pack.at(*digits, 'f');
    if (!high || !low || pack.at(*digits, 256)) return false; // 256 is outside the table: a value, not a fault.
    std::printf("  lookup table: \"7f\" is %d\n", *high * 16 + *low);
    std::printf("  string table:");
    for (std::size_t name = 0; name < offsets->size(); ++name) {
        std::string role;
        for (auto index = *pack.at(*offsets, name); const auto c = pack.at(*text, index); ++index) {
            if (*c == '\0') break;
            role += *c;
        }
        std::printf(" %s", role.c_str());
    }
    std::printf("\n");
    return sealed.max_connections == 512 && *high == 7 && *low == 15;
}

// @implements SPEC-LR-PACK
// Resident memory in KiB, where the system reports it.
std::optional<long> resident_kib() {
    std::ifstream status("/proc/self/status");
    for (std::string line; std::getline(status, line);)
        if (line.compare(0, 6, "VmRSS:") == 0) return std::stol(line.substr(6));
    return std::nullopt;
}

using clock_type = std::chrono::steady_clock;

struct result {
    std::size_t held = 0;                  // Values actually created.
    double build_ns = 0, read_ns = 0, destroy_ns = 0; // Per value, median of the repetitions.
    std::optional<long> resident_kib;      // Growth while held, first repetition.
    bool checksums_match = true;
};

// @implements SPEC-LR-PACK
double nanoseconds(clock_type::duration time, std::size_t values) {
    return static_cast<double>(std::chrono::duration_cast<std::chrono::nanoseconds>(time).count()) /
           static_cast<double>(values == 0 ? 1 : values);
}

// @implements SPEC-LR-PACK
// build() returns a holder and how many values it holds; read(holder, i) returns value i.
// Values are 0..held-1, read once each in the shared shuffled order.
template<class Build, class Read>
result measure(Build build, Read read, const std::vector<std::uint32_t>& order) {
    constexpr int repetitions = 5;
    std::array<double, repetitions> builds{}, reads{}, destroys{};
    result outcome;
    for (int repetition = 0; repetition < repetitions; ++repetition) {
        const auto resident_before = resident_kib();
        const auto started = clock_type::now();
        auto [holder, held] = build();
        const auto built = clock_type::now();
        std::uint64_t sum = 0;
        for (const std::uint32_t index : order)
            if (index < held) sum += read(*holder, index);
        const auto finished = clock_type::now();
        const auto resident_after = resident_kib();
        holder.reset();
        const auto destroyed = clock_type::now();
        outcome.held = held;
        builds[repetition] = nanoseconds(built - started, held);
        reads[repetition] = nanoseconds(finished - built, held);
        destroys[repetition] = nanoseconds(destroyed - finished, held);
        if (repetition == 0 && resident_before && resident_after) outcome.resident_kib = *resident_after - *resident_before;
        outcome.checksums_match = outcome.checksums_match && sum == std::uint64_t{held} * (held - (held != 0)) / 2;
    }
    const auto median = [](std::array<double, repetitions> values) {
        std::sort(values.begin(), values.end());
        return values[repetitions / 2];
    };
    outcome.build_ns = median(builds);
    outcome.read_ns = median(reads);
    outcome.destroy_ns = median(destroys);
    return outcome;
}

// @implements SPEC-LR-PACK
void report(const char* name, const result& outcome) {
    std::printf("  %-22s %8zu held  build %9.1f  random read %7.2f  destroy %9.1f ns/value  resident ",
                name, outcome.held, outcome.build_ns, outcome.read_ns, outcome.destroy_ns);
    if (outcome.resident_kib) std::printf("%+ld KiB\n", *outcome.resident_kib);
    else std::printf("not measured on this platform\n");
}
} // namespace

// @implements SPEC-LR-PACK
int main(int argc, char** argv) try {
    std::size_t count = 1000;
    if (argc > 1) {
        const char* const end = argv[1] + std::strlen(argv[1]);
        const auto parsed = std::from_chars(argv[1], end, count);
        if (argc > 2 || parsed.ec != std::errc() || parsed.ptr != end || count == 0 || count > UINT32_MAX ||
            !lorica::checked_multiply(count, sizeof(int))) {
            std::fprintf(stderr, "usage: %s [N > 0]\n", argv[0]);
            return 2;
        }
    }
    if (!show_configuration()) return 1;

    std::vector<std::uint32_t> order(count);
    for (std::size_t index = 0; index < count; ++index) order[index] = static_cast<std::uint32_t>(index);
    std::shuffle(order.begin(), order.end(), std::mt19937(12345));

    const auto individually = measure(
        [count] {
            // The OS may refuse a mapping: then the values created so far are measured.
            auto values = std::make_unique<std::deque<lorica::sealed_value<int>>>();
            try {
                for (std::size_t index = 0; index < count; ++index) values->emplace_back(static_cast<int>(index));
            } catch (const std::exception& error) {
                std::printf("  the OS refused sealed_value %zu of %zu: %s\n", values->size() + 1, count, error.what());
            }
            const std::size_t held = values->size();
            return std::pair(std::move(values), held);
        },
        [](const std::deque<lorica::sealed_value<int>>& values, std::uint32_t index) {
            return static_cast<std::uint64_t>(values[index].load());
        },
        order);
    const auto packed = measure(
        [count] {
            std::vector<int> staged(count);
            for (std::size_t index = 0; index < count; ++index) staged[index] = static_cast<int>(index);
            lorica::pack_builder builder(count * sizeof(int));
            const auto slot = builder.add_array(staged.data(), count);
            if (!slot) std::terminate(); // The capacity is exactly the array's size.
            struct holder { lorica::sealed_pack pack; lorica::pack_array_slot<int> slot; };
            return std::pair(std::unique_ptr<holder>(new holder{lorica::sealed_pack(std::move(builder)), *slot}), count);
        },
        [](const auto& values, std::uint32_t index) {
            return static_cast<std::uint64_t>(*values.pack.at(values.slot, index));
        },
        order);
    const auto unprotected = measure(
        [count] {
            auto values = std::make_unique<std::vector<std::unique_ptr<int>>>();
            values->reserve(count);
            for (std::size_t index = 0; index < count; ++index)
                values->push_back(std::make_unique<int>(static_cast<int>(index)));
            return std::pair(std::move(values), count);
        },
        [](const std::vector<std::unique_ptr<int>>& values, std::uint32_t index) {
            return static_cast<std::uint64_t>(*values[index]);
        },
        order);

    std::printf("%zu integers, median of 5 runs:\n", count);
    report("sealed_value each", individually);
    report("one sealed_pack", packed);
    report("new int each", unprotected);
    std::printf("Measured on this host in this run only; the numbers differ by host and load and promise nothing.\n");
    const bool correct = individually.checksums_match && packed.checksums_match && unprotected.checksums_match &&
                         packed.held == count && unprotected.held == count;
    std::printf("checksums %s\n", correct ? "match" : "DO NOT MATCH");
    return correct ? 0 : 1;
} catch (const std::exception& error) {
    // The OS refused the pack's mapping or its sealing; there is no unsealed fallback.
    std::fprintf(stderr, "sealed pack unavailable: %s\n", error.what());
    return 1;
}
