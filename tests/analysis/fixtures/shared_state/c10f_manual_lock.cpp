// C10: manual lock()/unlock() in one block with no jump between holds the lock;
// a condition-variable wait keeps the guard, and its predicate runs under it.
#include <condition_variable>
#include <mutex>
std::mutex m;
std::condition_variable cv;
int shared = 0;
bool ready = false;
void inc() { m.lock(); ++shared; m.unlock(); }
void set() { std::lock_guard<std::mutex> g(m); ready = true; cv.notify_all(); }
int wait_ready() { std::unique_lock<std::mutex> l(m); cv.wait(l, [] { return ready; }); return shared; }
// expect: datum shared lock:m
// expect: datum ready lock:m
// expect: sharing inc self-synchronized(unverified)
// expect: sharing wait_ready self-synchronized(unverified)
// tsan: clean | inc() | inc()
// tsan: clean | set() | sink(wait_ready())
