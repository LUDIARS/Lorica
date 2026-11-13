// A lock in an inner block does not cover a later access.
#include <mutex>
std::mutex m;
int shared = 0;
void twice() { { std::lock_guard<std::mutex> g(m); ++shared; } ++shared; }
// expect: datum shared inconsistent
// expect: finding inconsistent-locking shared
// tsan: race | twice() | twice()
