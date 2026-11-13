#include <string_view>
CX bool f(std::string_view s){ return s.find('\0')!=s.npos; }
#ifdef WITNESS
static_assert(!f("abc"),"");
#endif
