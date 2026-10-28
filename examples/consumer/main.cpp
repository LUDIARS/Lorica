#include <lorica/byte_view.hpp>
#include <lorica/input_budget.hpp>
#include <lorica/sealed_value.hpp>
#include <array>

// @implements SPEC-LR-CONSUMER
int main() {
    const lorica::sealed_value<unsigned> input_limit(1024);
    const std::array<std::byte, 2> input{std::byte{1}, std::byte{2}};
    lorica::input_budget request({1024, 16, 2, 4});
    const auto bytes = lorica::checked_multiply(input.size(), sizeof(std::byte));
    if (!bytes || !request.consume(*bytes, input.size(), 0)) return 1;
    const auto view = lorica::byte_view::make(input.data(), *bytes, input_limit.load());
    if (!view || !view->at(1)) return 1;
    return 0;
}
