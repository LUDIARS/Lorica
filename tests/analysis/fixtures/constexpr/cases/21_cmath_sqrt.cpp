#include <cmath>
CX double f(double x){ return std::sqrt(x); }
#ifdef WITNESS
static_assert(f(4.0)==2.0,"");
#endif
