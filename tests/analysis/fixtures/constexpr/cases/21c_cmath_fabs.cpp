#include <cmath>
CX double f(double x){ return std::fabs(x); }
#ifdef WITNESS
static_assert(f(-4.0)==4.0,"");
#endif
