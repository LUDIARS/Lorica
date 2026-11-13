// C6 (f08): a relaxed flag that publishes plain data: a finding on both sides.
#include <atomic>
#include <thread>
int payload = 0;
std::atomic<bool> ready{false};
void publish() { payload = 42; ready.store(true, std::memory_order_relaxed); }
int consume() { while (!ready.load(std::memory_order_relaxed)) std::this_thread::yield(); return payload; }
// expect: datum payload atomic:ready
// expect: datum ready atomic:relaxed
// expect: finding relaxed-publication publish
// expect: finding relaxed-publication consume
// expect: sharing publish thread-hostile
// tsan: race | if (i == 0) publish() | sink(consume())
