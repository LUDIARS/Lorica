#include <algorithm>
CX int f(int a,int b){ return std::min(a,b); }
#ifdef WITNESS
static_assert(f(1,2)==1,"");
#endif
