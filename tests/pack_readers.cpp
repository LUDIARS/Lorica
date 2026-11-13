// SPEC-LR-PACK and SPEC-LR-SEALED: many threads read one sealed pack and one
// sealed_value without synchronisation. Only meaningful under ThreadSanitizer,
// which reports any write that races with the reads; CMake registers it only there.
#include <lorica/sealed_pack.hpp>
#include <lorica/sealed_value.hpp>
#include <atomic>
#include <cstdint>
#include <cstdlib>
#include <thread>
#include <utility>
#include <vector>

namespace {
// @implements SPEC-LR-VERIFY
void require(bool condition) { if (!condition) std::abort(); }
}

// @implements SPEC-LR-VERIFY
int main() {
    std::uint32_t table[256];
    for (std::uint32_t index = 0; index < 256; ++index) table[index] = index * 7;
    lorica::pack_builder builder(sizeof(table) + 16);
    const auto limit = builder.add(std::uint64_t{4096});
    const auto entries = builder.add_array(table, 256);
    require(limit && entries);
    const lorica::sealed_pack pack(std::move(builder));
    const lorica::sealed_value<int> setting(42);

    std::atomic<bool> correct{true};
    std::vector<std::thread> readers;
    for (unsigned reader = 0; reader < 8; ++reader)
        readers.emplace_back([&, reader] {
            for (std::uint32_t round = 0; round < 20000; ++round) {
                const std::uint32_t index = (round + reader) % 256;
                if (pack.load(*limit) != 4096 || pack.at(*entries, index) != index * 7 || setting.load() != 42)
                    correct = false;
            }
        });
    for (auto& reader : readers) reader.join();
    require(correct);
}
