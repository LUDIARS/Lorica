// C9 (f11): double-checked locking on a plain pointer: the unlocked first check
// reads the datum written under the lock.
#include <mutex>
struct W { int v = 7; };
W* inst = nullptr;
std::mutex m;
W* get() { if (!inst) { std::lock_guard<std::mutex> g(m); if (!inst) inst = new W; } return inst; }
// expect: datum W::v not-needed
// expect: datum inst inconsistent
// expect: finding inconsistent-locking inst
// expect: sharing get thread-hostile
// tsan: race | sink(get()->v) | sink(get()->v)
