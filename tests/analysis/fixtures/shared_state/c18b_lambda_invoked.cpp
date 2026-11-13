// Lambdas: an immediately invoked body, and one passed to an algorithm, run under
// the lock; one stored for later does not.
#include <algorithm>
#include <functional>
#include <mutex>
#include <vector>
std::mutex m;
int shared = 0;
std::vector<int> items{1, 2, 3};
std::function<void()> later;
void add() { std::lock_guard<std::mutex> g(m); [&] { ++shared; }(); }
void add_all() { std::lock_guard<std::mutex> g(m); std::for_each(items.begin(), items.end(), [](int v) { shared += v; }); }
void store_for_later() { std::lock_guard<std::mutex> g(m); later = [] { ++shared; }; }
// expect: datum shared inconsistent
// expect: datum items lock:m
// expect: datum later lock:m
// expect: finding inconsistent-locking shared
// expect: sharing add self-synchronized(unverified)
// expect: sharing add_all self-synchronized(unverified)
// expect: sharing store_for_later thread-hostile
// tsan: clean | add() | add_all()
