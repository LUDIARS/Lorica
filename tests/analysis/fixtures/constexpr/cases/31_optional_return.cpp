#include <optional>
CX std::optional<int> f(int a){ if(a<0) return std::nullopt; return a; }
#ifdef WITNESS
static_assert(*f(1)==1,"");
#endif
