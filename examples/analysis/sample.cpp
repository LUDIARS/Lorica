// A small consumer source for the complexity gate; parse_flags is deliberately
// over the limit. The analyser reads this file and never compiles or edits it.
#include <cstddef>
#include <string_view>

int clamp_percent(int value) {
    if (value < 0) return 0;
    return value > 100 ? 100 : value;
}

unsigned parse_flags(std::string_view text) {
    unsigned flags = 0;
    for (std::size_t i = 0; i < text.size(); ++i) {
        if (text[i] == '-') {
            if (i + 1 < text.size() && text[i + 1] == '-') {
                continue;
            }
        } else if (text[i] == 'v' || text[i] == 'V') {
            flags |= 1u;
        } else if (text[i] == 'q') {
            flags |= 2u;
        } else {
            return 0;
        }
    }
    return flags;
}

unsigned checksum(std::string_view text) {
    unsigned sum = 0;
    for (char c : text) sum = sum * 31 + static_cast<unsigned char>(c);
    return sum;
}
