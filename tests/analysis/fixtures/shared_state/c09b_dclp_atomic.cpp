// C9 (f12): correct double-checked locking: acquire outside, any order inside the
// lock, release store.
#include <atomic>
#include <mutex>
struct W { int v = 7; };
std::atomic<W*> inst{nullptr};
std::mutex m;
W* get() {
    W* p = inst.load(std::memory_order_acquire);
    if (!p) {
        std::lock_guard<std::mutex> g(m);
        p = inst.load(std::memory_order_relaxed);
        if (!p) { p = new W; inst.store(p, std::memory_order_release); }
    }
    return p;
}
// expect: datum W::v not-needed
// expect: datum inst atomic:acquire,relaxed,release
// expect: sharing get self-synchronized(unverified)
// tsan: clean | sink(get()->v) | if (i == 0) pause(); sink(get()->v)
