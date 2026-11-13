// Fences (f10b): a fence with no atomic object orders nothing.
#include <atomic>
#include <thread>
int payload = 0;
bool ready = false;
void publish() { payload = 42; std::atomic_thread_fence(std::memory_order_seq_cst); ready = true; }
int consume() {
    for (int i = 0; i < 100000 && !ready; ++i) std::this_thread::yield();
    std::atomic_thread_fence(std::memory_order_seq_cst);
    return payload;
}
// expect: datum payload missing
// expect: datum ready missing
// expect: finding unsynchronized payload
// expect: finding unsynchronized ready
// expect: finding fence-without-atomic publish
// expect: finding fence-without-atomic consume
// tsan: race | publish() | sink(consume())
