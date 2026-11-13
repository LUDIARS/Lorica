// C9 (f12b): the same with relaxed everywhere: the unlocked load and the store.
#include <atomic>
#include <mutex>
struct W { int v = 7; };
std::atomic<W*> inst{nullptr};
std::mutex m;
W* get() {
    W* p = inst.load(std::memory_order_relaxed);
    if (!p) {
        std::lock_guard<std::mutex> g(m);
        p = inst.load(std::memory_order_relaxed);
        if (!p) { p = new W; inst.store(p, std::memory_order_relaxed); }
    }
    return p;
}
// expect: datum W::v not-needed
// expect: datum inst atomic:relaxed
// expect: finding relaxed-publication get
// tsan: race | sink(get()->v) | if (i == 0) pause(); sink(get()->v)
