// C12 (f18, f18b, f18d): copies of distinct shared_ptr objects are safe; one
// shared_ptr object assigned and copied is a datum; the pointee is the caller's.
#include <memory>
int read_copy(std::shared_ptr<const int> sp) { auto c = sp; return *c; }
std::shared_ptr<int> g = std::make_shared<int>(1);
int read_g() { auto c = g; return *c; }
void reset_g(int i) { g = std::make_shared<int>(i); }
void bump(const std::shared_ptr<int>& sp) { ++*sp; }
// expect: datum g missing
// expect: finding unsynchronized g
// expect: sharing read_copy no-shared-state
// expect: sharing read_g thread-hostile
// expect: sharing bump caller-synchronized:write
// setup: auto sp = std::make_shared<const int>(5);
// setup: auto counter = std::make_shared<int>(0);
// tsan: clean | sink(read_copy(sp)) | sink(read_copy(sp))
// tsan: race | sink(read_g()) | reset_g(i)
// tsan: race | bump(counter) | bump(counter)
