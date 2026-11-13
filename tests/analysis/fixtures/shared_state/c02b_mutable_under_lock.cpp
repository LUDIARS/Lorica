// C2 (f02): the same cache under a mutable mutex.
#include <mutex>
struct Cache {
    int v = 3;
    mutable std::mutex m;
    mutable int cache = 0;
    int get() const { std::lock_guard<std::mutex> g(m); if (!cache) cache = v * 2; return cache; }
};
// expect: datum Cache::v lock:m
// expect: datum Cache::cache lock:m
// expect: sharing Cache::get self-synchronized(unverified)
// setup: Cache c;
// tsan: clean | sink(c.get()) | sink(c.get())
