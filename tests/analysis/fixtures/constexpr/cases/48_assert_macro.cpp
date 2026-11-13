#include <cassert>
CX int f(int a){ assert(a>=0); return a; }
#ifdef WITNESS
static_assert(f(1)==1,"");
#endif
