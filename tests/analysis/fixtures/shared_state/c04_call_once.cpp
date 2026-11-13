// C4 (f05): writes in the std::call_once callable are initialisation; reads after
// the call in the same block are synchronised by it.
#include <mutex>
std::once_flag once;
int* table = nullptr;
int get(int i) { std::call_once(once, [] { table = new int[4]{1, 2, 3, 4}; }); return table[i]; }
// expect: datum table lock:call_once(once)
// expect: sharing get self-synchronized(unverified)
// tsan: clean | sink(get(i % 4)) | sink(get(i % 4))
