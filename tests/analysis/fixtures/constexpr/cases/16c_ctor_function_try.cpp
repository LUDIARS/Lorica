struct R{int x; CX R(int a) try : x(a) {} catch(...) {} };
#ifdef WITNESS
constexpr R r{1};
static_assert(r.x==1,"");
#endif
