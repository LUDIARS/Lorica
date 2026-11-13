// C10 (f14): both writers lock, different mutexes.
#include <mutex>
std::mutex a, b;
int shared = 0;
void inc_a() { std::lock_guard<std::mutex> g(a); ++shared; }
void inc_b() { std::lock_guard<std::mutex> g(b); ++shared; }
// expect: datum shared inconsistent
// expect: finding inconsistent-locking shared
// expect: sharing inc_a thread-hostile
// tsan: race | inc_a() | inc_b()
