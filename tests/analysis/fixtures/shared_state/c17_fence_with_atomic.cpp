// Fences (f10): a fence pair with a relaxed atomic is correct publication
// ([atomics.fences]); never a finding, always manual review.
#include <atomic>
#include <thread>
int payload = 0;
std::atomic<bool> ready{false};
void publish() { payload = 42; std::atomic_thread_fence(std::memory_order_release); ready.store(true, std::memory_order_relaxed); }
int consume() {
    while (!ready.load(std::memory_order_relaxed)) std::this_thread::yield();
    std::atomic_thread_fence(std::memory_order_acquire);
    return payload;
}
// expect: datum payload atomic:ready
// expect: datum ready atomic:relaxed
// expect: flag publish fence: manual review
// expect: flag consume fence: manual review
// tsan: not-observable(GCC: atomic_thread_fence is not supported with -fsanitize=thread)
