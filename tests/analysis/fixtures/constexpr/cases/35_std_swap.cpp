#include <utility>
CX int f(int a,int b){ std::swap(a,b); return a; }
#ifdef WITNESS
static_assert(f(1,2)==2,"");
#endif
