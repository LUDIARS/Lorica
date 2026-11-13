// C10 (f29): after unlock() the lockset is unknown, never "held"; likewise a manual
// lock()/unlock() with a return between.
#include <mutex>
std::mutex m;
int shared = 0, other = 0;
void inc() { std::unique_lock<std::mutex> g(m); g.unlock(); ++shared; }
int early(bool stop) { m.lock(); if (stop) return 0; ++other; m.unlock(); return 1; }
// expect: datum shared unknown
// expect: datum other unknown
// expect: finding unknown shared
// expect: finding unknown other
// expect: finding unknown inc
// expect: finding unknown early
// expect: sharing inc unknown
// tsan: race | inc() | inc()
