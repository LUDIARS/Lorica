#include <array>
CX int f(){ std::array<int,3> a{}; for(std::size_t i=0;i<3;++i) a[i]=int(i); return a[2]; }
#ifdef WITNESS
static_assert(f()==2,"");
#endif
