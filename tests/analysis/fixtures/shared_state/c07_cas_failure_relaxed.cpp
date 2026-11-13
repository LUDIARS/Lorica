// C7 (f26): the failure order of compare_exchange is a load; relaxed, then the
// failed `expected` is dereferenced.
#include <atomic>
#include <thread>
struct N { int v; };
std::atomic<N*> head{nullptr};
void publish() { N* n = new N{42}; head.store(n, std::memory_order_release); }
int peek() {
    for (;;) {
        N* expected = nullptr;
        if (!head.compare_exchange_strong(expected, nullptr, std::memory_order_acq_rel, std::memory_order_relaxed))
            return expected->v;
        std::this_thread::yield();
    }
}
// expect: datum N::v not-needed
// expect: datum head atomic:acq_rel,relaxed,release
// expect: finding relaxed-publication peek
// tsan: race | publish() | sink(peek())
