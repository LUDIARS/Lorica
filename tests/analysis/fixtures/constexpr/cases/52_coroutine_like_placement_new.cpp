#include <new>
CX int f(int a){ int x=0; ::new (&x) int(a); return x; }
#ifdef WITNESS
static_assert(f(2)==2,"");
#endif
