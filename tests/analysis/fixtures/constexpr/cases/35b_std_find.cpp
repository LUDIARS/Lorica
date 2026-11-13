#include <algorithm>
CX bool f(const int* b,const int* e,int v){ return std::find(b,e,v)!=e; }
#ifdef WITNESS
constexpr int a[]={1,2,3};
static_assert(f(a,a+3,2),"");
#endif
