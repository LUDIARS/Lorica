// C7 (invalid_orders): orders the standard forbids; a failure order stronger than
// the success order is legal since C++17.
#include <atomic>
std::atomic<int> a{0};
int bad_load() { return a.load(std::memory_order_release); }
void bad_store() { a.store(1, std::memory_order_acquire); }
bool bad_cas() { int e = 0; return a.compare_exchange_strong(e, 1, std::memory_order_relaxed, std::memory_order_release); }
bool stronger_failure() { int e = 0; return a.compare_exchange_strong(e, 1, std::memory_order_relaxed, std::memory_order_seq_cst); }
// expect: datum a atomic:acquire,relaxed,release,seq_cst
// expect: finding invalid-order bad_load
// expect: finding invalid-order bad_store
// expect: finding invalid-order bad_cas
// expect: sharing stronger_failure self-synchronized(unverified)
// tsan: not-observable(precondition violations of the memory order, not data races)
