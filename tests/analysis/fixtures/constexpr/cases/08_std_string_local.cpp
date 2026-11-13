#include <string>
CX std::size_t f(){ std::string s("abc"); return s.size(); }
#ifdef WITNESS
static_assert(f()==3,"");
#endif
