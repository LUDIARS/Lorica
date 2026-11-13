// C6 (f09b): release store, relaxed load: the finding is on the load only.
#include <atomic>
#include <thread>
int payload = 0;
std::atomic<bool> ready{false};
void publish() { payload = 42; ready.store(true, std::memory_order_release); }
int consume() { while (!ready.load(std::memory_order_relaxed)) std::this_thread::yield(); return payload; }
// expect: datum payload atomic:ready
// expect: datum ready atomic:relaxed,release
// expect: finding relaxed-publication consume
// expect: sharing publish self-synchronized(unverified)
// tsan: race | if (i == 0) publish() | sink(consume())
