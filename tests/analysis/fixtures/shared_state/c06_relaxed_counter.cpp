// C6 (f07): a relaxed counter is correct: no finding.
#include <atomic>
std::atomic<long> hits{0};
void hit() { hits.fetch_add(1, std::memory_order_relaxed); }
long total() { return hits.load(); }
// expect: datum hits atomic:relaxed,seq_cst
// expect: sharing hit self-synchronized(unverified)
// expect: sharing total self-synchronized(unverified)
// tsan: clean | hit() | sink(total())
