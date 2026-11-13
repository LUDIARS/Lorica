// Source-file shapes: external linkage is excluded, internal linkage is tried.
#include "shapes.hpp"

int parse(int x) { return x; }
static int helper(int x) { return x + 1; }
namespace {
int hidden_helper(int x) { return x; }
struct local {
    int get() const { return 3; }
};
}  // namespace
TEST(suite, name) { }
int main() { return helper(1); }
