// C10 (f25): a write under std::shared_lock.
#include <shared_mutex>
std::shared_mutex m;
int shared = 0;
void inc() { std::shared_lock<std::shared_mutex> g(m); ++shared; }
int get() { std::shared_lock<std::shared_mutex> g(m); return shared; }
// expect: datum shared lock:m
// expect: finding write-under-shared-lock shared
// expect: sharing inc thread-hostile
// expect: sharing get self-synchronized(unverified)
// tsan: race | inc() | inc()
