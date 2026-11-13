#include "constexpr_sample.hpp"

// Excluded: external linkage in a source file (an exported symbol).
int parse_level(const char* text) { return text[0] == 'h' ? 2 : 1; }

int main() { return scaled(parse_level("high"), 2) + checked_divide(4, 2) > 0 ? 0 : 1; }
