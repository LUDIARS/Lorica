#include <vector>
CX std::size_t f(){ std::vector<int> v{1,2,3}; return v.size(); }
#ifdef WITNESS
static_assert(f()==3,"");
#endif
