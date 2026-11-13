// C10 (f13, f13b, f13c): statements that look like guards and hold nothing.
#include <mutex>
std::mutex m;
int one = 0, two = 0, three = 0, four = 0;
void declares() { std::unique_lock<std::mutex>(m); ++one; }      // a new unique_lock named m
void temporary() { std::lock_guard<std::mutex>{m}; ++two; }      // unlocked at the semicolon
void empty() { std::scoped_lock lock; ++three; }                 // scoped_lock<>: no mutex
void deferred() { std::unique_lock<std::mutex> l(m, std::defer_lock); ++four; }
// expect: datum one missing
// expect: datum two missing
// expect: datum three missing
// expect: datum four missing
// expect: finding unsynchronized one
// expect: finding unsynchronized two
// expect: finding unsynchronized three
// expect: finding unsynchronized four
// expect: finding lock-not-held declares
// expect: finding lock-not-held temporary
// expect: finding lock-not-held empty
// expect: finding lock-not-held deferred
// tsan: race | declares() | declares()
// tsan: race | temporary() | temporary()
// tsan: race | empty() | empty()
// tsan: race | deferred() | deferred()
