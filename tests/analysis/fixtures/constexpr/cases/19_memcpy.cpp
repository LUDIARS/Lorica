#include <cstring>
CX int f(int a){ int b=0; std::memcpy(&b,&a,sizeof b); return b;}
#ifdef WITNESS
static_assert(f(5)==5,"");
#endif
