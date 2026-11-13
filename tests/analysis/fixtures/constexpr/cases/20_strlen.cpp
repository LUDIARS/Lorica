#include <cstring>
CX std::size_t f(const char*s){return std::strlen(s);}
#ifdef WITNESS
static_assert(f("abc")==3,"");
#endif
