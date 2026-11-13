#include <cstdint>
CX std::uintptr_t f(const int* p){ return reinterpret_cast<std::uintptr_t>(p);}
#ifdef WITNESS
constexpr int g=0;
static_assert(f(&g)!=0,"");
#endif
