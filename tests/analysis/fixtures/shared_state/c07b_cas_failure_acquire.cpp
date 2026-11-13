// C7 (f26b): failure order acquire: no finding.
#include <atomic>
#include <thread>
struct N { int v; };
std::atomic<N*> head{nullptr};
void publish() { N* n = new N{42}; head.store(n, std::memory_order_release); }
int peek() {
    for (;;) {
        N* expected = nullptr;
        if (!head.compare_exchange_strong(expected, nullptr, std::memory_order_acq_rel, std::memory_order_acquire))
            return expected->v;
        std::this_thread::yield();
    }
}
// expect: datum N::v not-needed
// expect: datum head atomic:acq_rel,acquire,release
// expect: sharing peek self-synchronized(unverified)
// tsan: clean | publish() | sink(peek())
