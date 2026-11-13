// Lambdas (f24): a body written inside a lock scope and run by std::thread has an
// empty lockset.
#include <mutex>
#include <thread>
std::mutex m;
int shared = 0;
void spawn_and_add() {
    std::thread t;
    {
        std::lock_guard<std::mutex> g(m);
        t = std::thread([&] { ++shared; });
    }
    { std::lock_guard<std::mutex> g(m); ++shared; }
    t.join();
}
// expect: datum shared inconsistent
// expect: finding inconsistent-locking shared
// tsan: race | spawn_and_add() | spawn_and_add()
