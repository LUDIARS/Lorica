// Locks held at every call site propagate into private members and functions in an
// unnamed namespace; not into public ones.
#include <mutex>
namespace {
std::mutex m;
int total = 0;
void add_locked(int v) { total += v; }
}
void add(int v) { std::lock_guard<std::mutex> g(m); add_locked(v); }
class Counter {
    std::mutex m_;
    int n_ = 0;
    void bump_locked() { ++n_; }
public:
    void bump() { std::lock_guard<std::mutex> g(m_); bump_locked(); }
    void reset_unlocked() { n_ = 0; }
};
// expect: datum total lock:m
// expect: datum Counter::n_ inconsistent
// expect: finding inconsistent-locking Counter::n_
// expect: sharing add self-synchronized(unverified)
// setup: Counter c;
// tsan: clean | add(i) | add(i)
// tsan: clean | c.bump() | c.bump()
// tsan: race | c.bump() | c.reset_unlocked()
