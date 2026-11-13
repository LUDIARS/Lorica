// C6 (f09): the same publication with release/acquire: no finding.
#include <atomic>
#include <thread>
int payload = 0;
std::atomic<bool> ready{false};
void publish() { payload = 42; ready.store(true, std::memory_order_release); }
int consume() { while (!ready.load(std::memory_order_acquire)) std::this_thread::yield(); return payload; }
// expect: datum payload atomic:ready
// expect: datum ready atomic:acquire,release
// expect: sharing publish self-synchronized(unverified)
// expect: sharing consume self-synchronized(unverified)
// tsan: clean | if (i == 0) publish() | sink(consume())
