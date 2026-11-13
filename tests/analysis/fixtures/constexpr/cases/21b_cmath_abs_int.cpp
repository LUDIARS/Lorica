#include <cstdlib>
CX int f(int x){ return std::abs(x); }
#ifdef WITNESS
static_assert(f(-4)==4,"");
#endif
