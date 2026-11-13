#include <atomic>
CX int f(){ std::atomic<int> a{1}; return a.load(); }
#ifdef WITNESS
static_assert(f()==1,"");
#endif
